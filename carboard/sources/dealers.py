"""Ontario car dealers' own websites, where a car is sometimes priced below its listing-site ads.

dealers.json lists the dealers of every brand with the website platform each site ran on when the list was made. Each
platform has its own inventory feed, read by an adapter below. Hyundai, Honda and Kia dealers are searched for new and
used cars, the rest for used ones. A site that wasn't readable is looked at again every few hours, so a dealer that
moves platform or drops its bot check gets picked up; sites behind a bot check (Cloudflare, Incapsula) are left alone.
"""
import base64
import collections
import concurrent.futures
import json
import re
import time
import urllib.parse
import zlib
from pathlib import Path

from .. import targets
from ..http import FetchError, Fetcher
from ..models import Listing, SourceResult
from ..util import norm, strip_html, tidy_city, to_int

NAME = "Dealer websites"
SHORT = "DLR"
DEALERS = Path(__file__).resolve().parent.parent / "dealers.json"
YEAR = 2025
# The models each brand's inventory is searched for, by the names D2C's year/make/model pages use.
MODELS = {"Hyundai": ["Tucson", "Tucson Hybrid"], "Honda": ["CR-V", "CR-V Hybrid"], "Kia": ["Sportage", "Sportage Hybrid", "Sportage HEV"]}
WANTED = re.compile(r"\b(?:tucson|cr[ -]?v|sportage)\b")
NEW_CAR_BRANDS = {"Hyundai", "Honda", "Kia"}  # only their dealers have the six cars new
BOT_CHECK = re.compile(r"<title>just a moment|attention required! \| cloudflare|_incapsula_resource|cf-chl-", re.I)
RECHECK_GROUPS = 6  # sites that weren't readable are retried in turn, one group per hourly dealer scan
WORKERS = 16


def fetch(log):
    dealers = json.loads(DEALERS.read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as pool:
        scans = list(pool.map(_scan, dealers))
    found, problems, incomplete, requests = {}, [], set(), 0
    outcome = collections.Counter()
    for dealer, (listings, platform, problem, n) in zip(dealers, scans):
        requests += n
        for listing in listings:
            found[listing.source_id] = listing
        if problem:
            problems.append(f"{dealer['name']} ({problem})")
        outcome["read" if platform in ADAPTERS and not problem else "failed" if problem else platform] += 1
        if dealer["website"] and (problem or platform not in ADAPTERS):
            incomplete.add(_key(dealer))
    log.info("dealers: %s, %d listings", dict(outcome), len(found))

    notes = [f"Read {outcome['read']} of {len(dealers)} Ontario dealer sites"]
    skipped = [f"{outcome[k]} {why}" for k, why in (("blocked", "block automated visits"), ("other", "run website software this board can't read yet"),
                                                    ("down", "didn't load"), ("unknown", "have no known website")) if outcome[k]]
    if skipped:
        notes.append("Not read: " + ", ".join(skipped))
    if problems:
        notes.append("Failed this time: " + "; ".join(problems[:8]) + (f" and {len(problems) - 8} more" if len(problems) > 8 else ""))
    # One failing dealer site isn't a problem with the source; most of them failing is.
    errors = [] if outcome["read"] > len(problems) else problems[:3] or ["no dealer site could be read"]
    return SourceResult(list(found.values()), errors, requests, incomplete, notes)


def _scan(dealer):
    """One dealer site: (listings, the platform it was read as or why it wasn't read, problem, requests made)."""
    if not dealer["website"]:
        return [], "unknown", None, 0
    if dealer["platform"] not in ADAPTERS and not _recheck_now(dealer):
        return [], dealer["platform"] or "unknown", None, 0
    http = Fetcher(min_gap=1.0, jitter=1.0, retries=0)
    platform = dealer["platform"] if dealer["platform"] in ADAPTERS else _detect(http, dealer)
    if platform not in ADAPTERS:
        return [], platform, None, http.requests
    try:
        return ADAPTERS[platform](http, dealer), platform, None, http.requests
    except (FetchError, ValueError, KeyError, TypeError) as e:
        problem = str(e) if isinstance(e, FetchError) else f"{type(e).__name__}: {e}"
    moved = _detect(http, dealer)  # the site may have moved platform, or put up a bot check
    if moved == "blocked":
        return [], moved, None, http.requests
    if moved != platform and moved in ADAPTERS:
        try:
            return ADAPTERS[moved](http, dealer), moved, None, http.requests
        except (FetchError, ValueError, KeyError, TypeError) as e:
            problem = str(e) if isinstance(e, FetchError) else f"{type(e).__name__}: {e}"
    return [], platform, problem[:140], http.requests


def _recheck_now(dealer):
    """Whether this hour's dealer scan should look at a site that wasn't readable before."""
    return zlib.crc32(dealer["website"].encode()) % RECHECK_GROUPS == time.gmtime().tm_hour % RECHECK_GROUPS


def _sells_new(dealer):
    return bool(NEW_CAR_BRANDS & set(dealer["brands"]))


def _detect(http, dealer):
    try:
        html = http.get(_base(dealer) + "/")
    except FetchError as e:
        return "blocked" if re.search(r"HTTP (?:403|429|503)", str(e)) else "down"
    if BOT_CHECK.search(html[:20000]):
        return "blocked"
    if '"vmsID"' in html:
        return "convertus"
    if "cdn.sm360.ca" in html:
        return "sm360"
    if "d2cmedia.ca" in html:
        return "d2c"
    return "other"


def _base(dealer):
    return "https://" + urllib.parse.urlsplit(dealer["website"]).netloc


def _key(dealer):
    return urllib.parse.urlsplit(dealer["website"]).netloc.removeprefix("www.")


def _wanted(year, make, model):
    return year == YEAR and make.lower() in ("hyundai", "honda", "kia") and WANTED.search(norm(model))


def _fuel(*texts):
    text = norm(" ".join(t or "" for t in texts))
    if re.search(r"plug|phev|rechargeable", text):
        return "phev"
    if re.search(r"hybrid|hybride|\bhev\b", text):
        return "hybrid"
    if re.search(r"electri", text):
        return "electric"
    if re.search(r"\bgas|essence|petrol", text):
        return "gas"
    return ""


def _listing(site, vin, **fields):
    """A Listing from a dealer's site; the vehicle's own fields can override the dealer's name and location."""
    listing = Listing(source="dealers", source_id=f"{_key(site)}:{vin}", vin=vin.upper(), make="", model="", year=None,
                      title="", url="", city=tidy_city(site["city"]), province="ON", postal=site["postal"],
                      lat=site["lat"], lon=site["lon"], dealer=site["name"], seller_type="dealer")
    for name, value in fields.items():
        setattr(listing, name, value)
    listing.title = f"{listing.year} {listing.make} {listing.model} {listing.trim}".strip()
    return listing


def _with_descriptions(listings, describe):
    """Fill in descriptions only where one could still change the match (the sunroof proof). A vehicle page that
    doesn't load just leaves that car without one."""
    for listing in listings:
        if targets.wants_description(listing):
            try:
                listing.text = describe(listing)
            except (FetchError, ValueError):
                pass
    return listings


# ---- D2C Media: server-rendered results, 36 vehicles a page ----

D2C_STATE = re.compile(r'id="filterState" value="([^"]+)"')


def _d2c(http, dealer):
    base = _base(dealer)
    cards = {}
    for root in ("/used", "/new/inventory") if _sells_new(dealer) else ("/used",):
        for card in _d2c_cards(http, base, root):
            cards[card["vin"]] = card
    listings = [_listing(dealer, c["vin"], **{k: v for k, v in c.items() if k != "vin"}) for c in cards.values()]
    return _with_descriptions(listings, lambda listing: _d2c_description(http, listing.url))


def _d2c_cards(http, base, root):
    """Every 2025 vehicle under /used (used and demo) or /new/inventory. A results page holds 36, so a full one is
    split by make, then by model."""
    cards, count = _d2c_page(http, f"{base}{root}/search.html?year={YEAR}", base)
    if count <= len(cards):
        return cards
    cards = []
    for make, models in MODELS.items():
        page, count = _d2c_page(http, f"{base}{root}/{YEAR}-{make}.html", base)
        if count > len(page):
            page = [card for model in models
                    for card in _d2c_page(http, f"{base}{root}/{YEAR}-{make}-{re.sub(r'[ -]', '_', model)}.html", base)[0]]
        cards += page
    return cards


def _d2c_page(http, url, base):
    html = http.get(url)
    state = D2C_STATE.search(html)
    if not state:
        raise FetchError(f"no D2C results on {url}")
    count = json.loads(base64.b64decode(state.group(1) + "==")).get("countSearchResults") or 0
    cards = [card for chunk in html.split('<div class="carBoxOuter')[1:] if (card := _d2c_card(chunk, base))]
    return cards, count


def _d2c_card(chunk, base):
    data = re.search(r'<input name="vehicledata"[^>]*>', chunk)
    link = re.search(r'<a href="([^"]+)"[^>]*class="carTitle', chunk)
    if not data or not link:
        return None
    attrs = dict(re.findall(r'data-([a-z-]+)="([^"]*)"', data.group(0)))
    year, make, model = to_int(attrs.get("year")), attrs.get("make", ""), attrs.get("model", "")
    if not attrs.get("vin") or not _wanted(year, make, model):
        return None

    def span(cls):
        m = re.search(rf"<span class='{cls}'>(.*?)</span>", chunk, re.S)
        return strip_html(m.group(1)) if m else ""

    trim = span("divTrim")
    fuel = re.search(r"Fuel:\s*</span>\s*<span[^>]*>([^<]*)<", chunk)
    url = urllib.parse.urljoin(base, link.group(1))
    return {
        "vin": attrs["vin"], "url": url, "year": year, "make": make, "model": model, "trim": trim,
        "price": to_int((re.search(r"format-price[^>]*>([^<]*)<", chunk) or [None, None])[1]),
        "km": to_int((re.search(r"<span class='s-km'>([^<]*)<", chunk) or [None, None])[1]),
        "fuel": _fuel(model, fuel.group(1) if fuel else ""),
        "condition": "new" if "/new/" in url else "demo" if re.search(r"\bdemo\b", trim, re.I) else "used",
    }


def _d2c_description(http, url):
    html = http.get(url)
    start = html.find('class="InnerBoxLayer divDescriptionBlock')
    if start < 0:
        return ""
    end = html.find('class="InnerBoxLayer', start + 40)
    block = html[start: end if end > 0 else start + 20000]
    return strip_html(re.sub(r"<(script|style)\b.*?</\1>", " ", block, flags=re.S | re.I))[:6000]


# ---- SM360: a JSON listing API on the dealer's own domain ----

def _sm360(http, dealer):
    base = _base(dealer)
    inventory = "all-inventory" if _sells_new(dealer) else "used-inventory"
    listings, page, pages = [], 1, 1
    while page <= pages:
        data = json.loads(http.get(f"{base}/en/{inventory}/api/listing?year={YEAR}&limit=100&page={page}", accept="application/json"))
        pages = (data.get("pagination") or {}).get("numberOfPages") or 1
        listings += filter(None, (_sm360_listing(dealer, base, v) for v in data.get("vehicles") or []))
        page += 1
    return listings  # SM360's listing already carries each vehicle's description


def _sm360_listing(dealer, base, v):
    make, model = (v.get("make") or {}), (v.get("model") or {})
    if not v.get("serialNo") or not _wanted(v.get("year"), make.get("name", ""), model.get("name", "")):
        return None
    options = v.get("extraOptions") or ""
    kind = "new" if v.get("newVehicle") else "used"
    fields = {
        "url": f"{base}/en/{kind}-inventory/{make.get('slug')}/{model.get('slug')}/{v['year']}-{make.get('slug')}-{model.get('slug')}-id{v.get('vehicleId')}",
        "year": v["year"], "make": make.get("name", ""), "model": model.get("name", ""),
        "trim": f"{(v.get('trim') or {}).get('name') or ''} {v.get('tagline') or ''}".strip(),
        "price": min((p for p in (to_int(v.get("salePrice")), to_int(v.get("listPrice"))) if p), default=None),
        "km": to_int(v.get("odometer")),
        "fuel": _fuel(model.get("name"), (v.get("fuel") or {}).get("name")),
        "condition": "demo" if v.get("demo") else kind,
        "text": f"{strip_html(v.get('description'))} {options}"[:6000],
        "features": ["sunroof"] if re.search(r"sun ?roof|moon ?roof|toit ouvrant", options, re.I) else [],
    }
    unit = v.get("primaryOrganizationUnit") or {}
    if unit.get("name") and norm(unit["name"]) != norm(dealer["name"]):  # a group site listing a sister dealer's car
        fields.update(dealer=unit["name"], city=tidy_city(unit.get("city")), postal="", lat=None, lon=None)
    return _listing(dealer, v["serialNo"], **fields)


# ---- Convertus (Trader's WordPress sites): its inventory service, relayed by the dealer's own site ----

def _convertus(http, dealer):
    base = _base(dealer)
    home = http.get(base + "/")
    settings = {k: re.search(rf'"{k}":"([^"]+)"', home) for k in ("vmsID", "vmsApiUrl", "pluginsUrl")}
    if not all(settings.values()):
        raise FetchError("no Convertus inventory settings on the homepage")
    vms_id, api, plugins = (settings[k].group(1).replace("\\/", "/") for k in ("vmsID", "vmsApiUrl", "pluginsUrl"))
    relay = f"{plugins}/convertus-vms/include/php/ajax-vehicles.php"
    results, page = [], 1
    while True:
        endpoint = f"{api}filtering/?cp={vms_id}&ln=en&yr={YEAR},{YEAR}&pc=100&pg={page}" + ("" if _sells_new(dealer) else "&sc=used")
        data = json.loads(http.get(f"{relay}?endpoint={urllib.parse.quote(endpoint, safe='')}&action=vms_data", accept="application/json, */*"))
        batch = data.get("results") or []
        results += batch
        if not batch or len(results) >= ((data.get("summary") or {}).get("total_vehicles") or 0):
            break
        page += 1
    listings = [listing for r in results if (listing := _convertus_listing(dealer, r))]
    return _with_descriptions(listings, lambda listing: _convertus_description(http, listing.url))


def _convertus_listing(dealer, r):
    if not r.get("vin") or not _wanted(r.get("year"), r.get("make") or "", r.get("model") or ""):
        return None
    sale_class = (r.get("sale_class") or "").lower()
    prices = [to_int(r.get(k)) for k in ("final_price", "sale_price", "internet_price", "asking_price")]
    # vdp_url is built on the dealer's address as entered in Convertus, sometimes plain http or with tracking tags
    path = re.search(r"/vehicles/.*", r.get("vdp_url") or "")
    url = f"{_base(dealer)}{path.group(0)}" if path else r.get("vdp_url") or ""
    return _listing(dealer, r["vin"], url=url, year=r["year"], make=r["make"], model=r["model"],
                    trim=r.get("trim") or "", price=prices[0] or min((p for p in prices if p), default=None),
                    km=to_int(r.get("odometer")), fuel=_fuel(r.get("model"), r.get("fuel_type")),
                    condition="demo" if r.get("demo") else "new" if sale_class == "new" else "used")


def _convertus_description(http, url):
    m = re.search(r"var vmsData\s*=\s*(\{.*?\});\s*\n", http.get(url), re.S)
    try:
        vehicle = (json.loads(m.group(1)).get("vehicle") or {}) if m else {}
    except ValueError:
        return ""
    return strip_html(f"{vehicle.get('description') or ''} {vehicle.get('package_description') or ''}")[:6000]


ADAPTERS = {"d2c": _d2c, "sm360": _sm360, "convertus": _convertus}
