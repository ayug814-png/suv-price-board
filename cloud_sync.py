"""Moves the scanner's files to and from the site's Cloudflare KV storage. The GitHub workflows run it:

    python cloud_sync.py pull             # fetch the listing history the last run left behind
    python cloud_sync.py push             # store the new history and the rebuilt board
    python cloud_sync.py configure-site   # point site/wrangler.toml at the storage and BOARD_DOMAIN, before deploying

Needs CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment (and BOARD_DOMAIN for configure-site).
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
SEED = ROOT / "seed"
HASHES = DATA / ".pulled.json"
NAMESPACE = "suv-price-board"
API = os.environ.get("CLOUDFLARE_API_BASE", "https://api.cloudflare.com/client/v4")
# Order matters on push: history first, so the board never shows data the next run can't build on.
FILES = {"geocache.json": DATA / "geocache.json", "state.json": DATA / "state.json", "board.html": ROOT / "board.html"}
PULLED = ("state.json", "geocache.json")


def api(method, path, body=None, content_type="application/json"):
    req = urllib.request.Request(
        f"{API}/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID'].strip()}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN'].strip()}", "Content-Type": content_type},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 and method == "GET":
                return None
            if e.code < 500 or attempt == 3:
                raise SystemExit(f"Cloudflare API {method} {path} failed: HTTP {e.code} {e.read()[:300]!r}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise SystemExit(f"Cloudflare API {method} {path} failed: {e}")
        time.sleep(5 * (attempt + 1))


def namespace_id():
    """The board's KV namespace, created the first time it's needed."""
    page = 1
    while True:
        listing = json.loads(api("GET", f"/storage/kv/namespaces?per_page=100&page={page}"))
        for namespace in listing["result"]:
            if namespace["title"] == NAMESPACE:
                return namespace["id"]
        if page >= (listing.get("result_info") or {}).get("total_pages", 1):
            break
        page += 1
    created = json.loads(api("POST", "/storage/kv/namespaces", json.dumps({"title": NAMESPACE}).encode()))
    print(f"created KV namespace {NAMESPACE}")
    return created["result"]["id"]


def value_path(namespace, name):
    return f"/storage/kv/namespaces/{namespace}/values/{urllib.parse.quote(name, safe='')}"


def pull():
    DATA.mkdir(exist_ok=True)
    namespace = namespace_id()
    hashes = {}
    for name in PULLED:
        body = api("GET", value_path(namespace, name))
        if body is None:
            if (SEED / name).exists():  # first run: start from the city coordinates already looked up
                shutil.copyfile(SEED / name, FILES[name])
                print(f"{name}: started from seed/{name}")
            else:
                print(f"{name}: none stored yet (first run)")
            continue
        FILES[name].write_bytes(body)
        hashes[name] = hashlib.sha256(body).hexdigest()
        print(f"{name}: {len(body):,} bytes")
    HASHES.write_text(json.dumps(hashes), encoding="utf-8")


def push():
    namespace = namespace_id()
    pulled = json.loads(HASHES.read_text(encoding="utf-8")) if HASHES.exists() else {}
    for name, path in FILES.items():
        if not path.exists():
            continue
        body = path.read_bytes()
        if pulled.get(name) == hashlib.sha256(body).hexdigest():
            print(f"{name}: unchanged")  # saves one of KV's 1,000 free daily writes
            continue
        api("PUT", value_path(namespace, name), body, "application/octet-stream")
        print(f"{name}: stored {len(body):,} bytes")
    HASHES.unlink(missing_ok=True)  # the comparison only holds for the run that did the pull


def configure_site():
    """Fill the storage id and your domain into site/wrangler.toml (in the workflow's copy; never committed)."""
    domain = re.sub(r"^https?://|/.*$", "", os.environ["BOARD_DOMAIN"].strip().lower())
    domain = domain.removeprefix("www.")
    path = ROOT / "site" / "wrangler.toml"
    toml = path.read_text(encoding="utf-8").replace("REPLACE_WITH_KV_ID", namespace_id())
    routes = (f'routes = [\n  {{ pattern = "{domain}", custom_domain = true }},\n'
              f'  {{ pattern = "www.{domain}", custom_domain = true }},\n]')
    toml = re.sub(r"(?ms)^#? ?routes = \[.*?^#? ?\]", lambda _: routes, toml)
    path.write_text(toml, encoding="utf-8")
    print(f"site will serve https://{domain} (and www.{domain})")


if __name__ == "__main__":
    actions = {"pull": pull, "push": push, "configure-site": configure_site}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(__doc__)
    actions[sys.argv[1]]()
