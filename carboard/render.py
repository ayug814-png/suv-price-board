"""Turns the listing history into board.html: one row per city, one column per car, prices linked to the ads."""
import collections
import datetime
import json
from pathlib import Path

from .geo import distance_km
from .sources import SOURCES
from .targets import TARGETS
from .util import city_key

TEMPLATE = Path(__file__).with_name("board_template.html")
SHOW_PRICE_CHANGE_FOR = datetime.timedelta(days=7)


def _when(stamp):
    return datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _same_car(a, b):
    """The same car posted on two sites: same VIN, or the same price and (nearly) the same odometer in the same
    province. Sites disagree on the town ('Nepean' vs 'Ottawa'), so the city isn't compared."""
    if a["vin"] and b["vin"]:
        return a["vin"] == b["vin"]
    if a["source"] == b["source"] or a["price"] is None or a["price"] != b["price"]:
        return False
    if a["km"] is None or b["km"] is None or (a["province"] and b["province"] and a["province"] != b["province"]):
        return False
    return abs(a["km"] - b["km"]) <= max(300, 0.015 * max(a["km"], b["km"]))


def _group_same_cars(records):
    cars = []
    for record in sorted(records, key=lambda r: (r["price"] is None, r["price"] or 0)):
        for car in cars:
            if any(_same_car(record, other) for other in car):
                car.append(record)
                break
        else:
            cars.append([record])
    return cars


def _vehicle(members, now, new_hours):
    members.sort(key=lambda r: (r["price"] is None, r["price"] or 0, r["source"]))
    lead = members[0]
    priced = [(stamp, price) for stamp, price in lead["price_history"] if price is not None]
    change, changed_at = 0, None
    if len(priced) >= 2 and now - _when(priced[-1][0]) <= SHOW_PRICE_CHANGE_FOR:
        change, changed_at = priced[-1][1] - priced[-2][1], priced[-1][0]
    first_seen = min(m["first_seen"] for m in members)
    is_new = not any(m.get("baseline") for m in members) and now - _when(first_seen) <= datetime.timedelta(hours=new_hours)
    return {
        "p": lead["price"],
        "km": lead["km"],
        "c": lead["condition"],
        "l": all(m["confidence"] == "likely" for m in members),
        "ev": lead["evidence"],
        "t": lead["title"],
        "d": next((m["dealer"] for m in members if m["dealer"]), ""),
        "pv": lead["seller_type"] == "private",
        "n": is_new,
        "ch": change,
        "ca": changed_at,
        "fs": first_seen,
        "links": [_link(m) for m in members],
    }


def _link(record):
    """[tag, url, where it opens]. Every dealer website shares the DLR tag; its tooltip names the dealer."""
    module = SOURCES[record["source"]]
    where = f"{record['dealer']}'s website" if record["source"] == "dealers" and record["dealer"] else module.NAME
    return [module.SHORT, record["url"], where]


def build(store, geo, config, run):
    now = datetime.datetime.now(datetime.timezone.utc)
    target_keys = {t["key"] for t in TARGETS}
    home = config.get("home") or {}
    home_xy = geo.coords(home.get("city", ""), home.get("province", ""))

    by_target = collections.defaultdict(list)
    for record in store.listings.values():
        if record.get("target") in target_keys:
            by_target[record["target"]].append(record)

    # Each car goes in the row its postings agree on most; the cheapest posting breaks ties.
    groups = collections.defaultdict(lambda: {"names": collections.Counter(), "cars": collections.defaultdict(list)})
    for key, records in by_target.items():
        for car in _group_same_cars(records):
            places = collections.Counter((r["province"] or "", city_key(r["city"]) or "?") for r in car)
            place = max(places, key=lambda p: (places[p], p == (car[0]["province"] or "", city_key(car[0]["city"]) or "?")))
            group = groups[place]
            group["names"].update(r["city"] or "Unknown" for r in car if (r["province"] or "", city_key(r["city"]) or "?") == place)
            group["cars"][key].append(_vehicle(car, now, config["new_badge_hours"]))

    rows = []
    for (province, _), group in groups.items():
        city = group["names"].most_common(1)[0][0]
        xy = geo.coords(city, province)
        rows.append({
            "c": city,
            "p": province,
            "d": round(distance_km(home_xy, xy)) if home_xy and xy else None,
            "v": {key: sorted(cars, key=lambda v: (v["p"] is None, v["p"] or 0)) for key, cars in group["cars"].items()},
        })

    sources = []
    for key, module in SOURCES.items():
        if not config["sources"].get(key):
            continue
        status = store.sources.get(key, {})
        sources.append({
            "key": key, "name": module.NAME, "short": module.SHORT,
            "ok": bool(status) and not status.get("errors"),
            "matched": status.get("matched", 0), "scanned": status.get("scanned", 0),
            "lastOk": status.get("last_ok"), "errors": status.get("errors", []), "notes": status.get("notes", []),
        })

    return {
        "generated": run["started"],  # when the prices were scanned
        "next": run["next"],
        "refresh": config["refresh_minutes"],
        "newHours": config["new_badge_hours"],
        "removeAfter": config["remove_after_missed_runs"],
        "home": {"label": home.get("label") or home.get("city", ""), "known": bool(home_xy)},
        "targets": TARGETS,
        "sources": sources,
        "rows": rows,
        "run": run,
    }


def write(path, store, geo, config, run):
    payload = json.dumps(build(store, geo, config, run), separators=(",", ":"), ensure_ascii=False)
    page = TEMPLATE.read_text(encoding="utf-8").replace("/*__BOARD_DATA__*/null", payload.replace("<", "\\u003c"))
    path = Path(path)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(page, encoding="utf-8")
    tmp.replace(path)
