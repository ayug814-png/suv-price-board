"""Scan every listing site once, update the price history and rebuild board.html.

Run it by hand with `python run.py`, or let the scheduled task from install_schedule.ps1 run it every 15 minutes.
"""
import argparse
import collections
import concurrent.futures
import contextlib
import datetime
import json
import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from carboard import render, targets  # noqa: E402
from carboard.geo import Geo  # noqa: E402
from carboard.models import SourceResult  # noqa: E402
from carboard.sources import SOURCES  # noqa: E402
from carboard.store import Store, utc_now  # noqa: E402
from carboard.util import city_key, province_from_postal  # noqa: E402

DATA = ROOT / "data"
log = logging.getLogger("carboard")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", help="only scan these sites this time, e.g. kijiji,carpages")
    parser.add_argument("--geocode-all", action="store_true", help="look up every unknown city now instead of a few per run")
    parser.add_argument("--dump", action="store_true", help="write data/last_scan.json with every scanned ad and its match result")
    parser.add_argument("--render-only", action="store_true", help="rebuild board.html from saved history without scanning")
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    _setup_logging()
    config = _load_config()
    with _single_instance(DATA / "run.lock") as acquired:
        if not acquired:
            log.info("previous run still going; skipping this one")
            return 0
        try:
            run(config, args)
        except Exception:
            log.exception("run failed")
            return 1
    return 0


def run(config, args):
    if args.render_only:
        store, geo = Store(DATA / "state.json"), Geo(DATA / "geocache.json")
        _locate(store, geo, config, unlimited=args.geocode_all)
        store.save()
        geo.save()
        render.write(ROOT / "board.html", store, geo, config, store.data["last_run"])
        log.info("board rebuilt from saved history")
        return
    started = time.monotonic()
    now = utc_now()
    store = Store(DATA / "state.json")
    enabled = [name for name, on in config["sources"].items() if on and name in SOURCES]
    if args.sources:
        enabled = [name for name in args.sources.split(",") if name in enabled]
    else:
        enabled = [name for name in enabled if _due(store.sources.get(name, {}), config.get("scan_every_minutes", {}).get(name), now)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(enabled) or 1) as pool:
        futures = {name: pool.submit(_scan, name) for name in enabled}
        results = {name: future.result() for name, future in futures.items()}

    geo = Geo(DATA / "geocache.json")
    floor, ceiling = config["price_floor"], config["price_ceiling"]
    dump = []
    for name, result in results.items():
        matched = {}
        for listing in result.listings:
            hit = targets.classify(listing)
            if args.dump:
                dump.append({**listing.record(), "text": listing.text[:400], "match": hit})
            if not hit:
                continue
            listing.target, listing.confidence, listing.evidence = hit
            if listing.price is not None and not floor <= listing.price <= ceiling:
                listing.price = None  # "$1", "call for price" placeholders and payment-only ads
            matched[listing.key] = listing
        store.merge(name, result, list(matched.values()), now, config["remove_after_missed_runs"],
                    [t["key"] for t in targets.TARGETS])
        log.info("%s: %d ads scanned, %d matched, %d requests%s", name, len(result.listings), len(matched),
                 result.requests, f", problems: {result.errors}" if result.errors else "")

    active = {name for name, on in config["sources"].items() if on}
    for key in [k for k, record in store.listings.items() if record["source"] not in active]:
        del store.listings[key]

    _locate(store, geo, config, unlimited=args.geocode_all)
    run_info = {
        "started": now,
        "next": (datetime.datetime.fromisoformat(now.replace("Z", "+00:00"))
                 + datetime.timedelta(minutes=config["refresh_minutes"])).isoformat().replace("+00:00", "Z"),
        "seconds": round(time.monotonic() - started, 1),
        "requests": sum(r.requests for r in results.values()) + geo.lookups,
    }
    store.data["last_run"] = run_info
    store.save()
    geo.save()
    render.write(ROOT / "board.html", store, geo, config, run_info)
    if args.dump:
        (DATA / "last_scan.json").write_text(json.dumps(dump, indent=1, ensure_ascii=False), encoding="utf-8")
    counts = {t["key"]: sum(1 for r in store.listings.values() if r["target"] == t["key"]) for t in targets.TARGETS}
    log.info("board updated in %.0fs: %s (%d new city lookups)", run_info["seconds"], counts, geo.lookups)


def _load_config():
    """config.json, plus personal settings kept out of the public repo: config.local.json on a PC, or the
    BOARD_HOME variable ("City, PR") that the GitHub workflow passes in."""
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    local = ROOT / "config.local.json"
    if local.exists():
        config.update(json.loads(local.read_text(encoding="utf-8")))
    if os.environ.get("BOARD_HOME"):
        city, _, province = os.environ["BOARD_HOME"].rpartition(",")
        config["home"] = {"city": city.strip(), "province": province.strip(), "label": os.environ["BOARD_HOME"].strip()}
    return config


def _due(status, every, now):
    """A source with its own interval in scan_every_minutes (the dealer websites) is only scanned once that has
    passed since its last scan, give or take a few minutes of scheduling delay."""
    if not every or "last_run" not in status:
        return True
    elapsed = datetime.datetime.fromisoformat(now.replace("Z", "+00:00")) - datetime.datetime.fromisoformat(status["last_run"].replace("Z", "+00:00"))
    return elapsed >= datetime.timedelta(minutes=every - 5)


def _scan(name):
    try:
        return SOURCES[name].fetch(log)
    except Exception as e:  # one broken site must not take the whole board down
        log.exception("%s failed", name)
        return SourceResult([], [f"{type(e).__name__}: {e}"], 0)


def _locate(store, geo, config, unlimited):
    """Fill in missing provinces, then coordinates for the distance-from-home sort."""
    records = list(store.listings.values())
    for r in records:
        if not r["province"]:
            r["province"] = province_from_postal(r["postal"])
        if r.get("lat") is not None and r["province"]:
            geo.learn(r["city"], r["province"], r["lat"], r["lon"])
    provinces_by_city = collections.defaultdict(set)
    for r in records:
        if r["province"]:
            provinces_by_city[city_key(r["city"])].add(r["province"])
    for r in records:
        if not r["province"] and r.get("lat") is not None:
            r["province"] = geo.nearest_province(r["lat"], r["lon"])
        if not r["province"] and len(provinces_by_city.get(city_key(r["city"]), ())) == 1:
            r["province"] = next(iter(provinces_by_city[city_key(r["city"])]))
    home = config.get("home") or {}
    places = [(home.get("city"), home.get("province", ""))] + sorted({(r["city"], r["province"]) for r in records if r["city"]})
    for city, province in places:
        if not city or geo.coords(city, province):
            continue
        if not unlimited and geo.lookups >= config["geocode_per_run"]:
            break
        geo.lookup(city, province)


def _setup_logging():
    handlers = [logging.handlers.RotatingFileHandler(ROOT / "logs" / "run.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")]
    if sys.stderr:  # pythonw (the scheduled task) has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers)


@contextlib.contextmanager
def _single_instance(path, stale_after=1800):
    with contextlib.suppress(OSError):
        if time.time() - path.stat().st_mtime > stale_after:
            path.unlink()
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        yield False
        return
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield True
    finally:
        with contextlib.suppress(OSError):
            path.unlink()


if __name__ == "__main__":
    sys.exit(main())
