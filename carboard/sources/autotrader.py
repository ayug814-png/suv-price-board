"""AutoTrader.ca (AutoHebdo.net shows the same inventory). Search pages embed their results as Next.js JSON."""
import json
import re

from ..http import FetchError, Fetcher
from ..models import Listing, SourceResult
from ..util import strip_html, tidy_city, to_int

NAME = "AutoTrader.ca"
SHORT = "AT"
SEARCHES = [("hyundai", "tucson"), ("honda", "cr-v"), ("kia", "sportage")]
URL = "https://www.autotrader.ca/cars/{make}/{model}/my_2025?size=100&page={page}&{order}"
# The default order reshuffles promoted ads between page loads, so a few can slip past a crawl. Crawl newest
# first, and if that still comes up short of the site's own total, make a second pass in price order.
ORDERS = ["sort=age&desc=1", "sort=price&desc=0"]
MAX_PAGES = 20
# AutoTrader's trim ids (from each listing's "modelTaxonomy"), used when the seller's own trim text is blank.
TRIMS = {
    "11402": "Preferred", "11404": "Ultimate", "5576": "N Line", "11400": "N Line", "481135": "XRT",
    "11739": "LX", "13120": "Sport", "13122": "Touring", "11828": "EX-L",
}
FUELS = {"Gasoline": "gas", "Gas/Electric Hybrid": "hybrid", "Electric": "electric"}
CONDITIONS = {"U": "used", "N": "new", "D": "demo", "J": "used", "S": "new"}


def fetch(log):
    http = Fetcher(min_gap=2.0)
    found, errors = {}, []
    for make, model in SEARCHES:
        seen, total, failures = set(), 0, len(errors)
        for order in ORDERS:
            page, pages = 1, 1
            while page <= min(pages, MAX_PAGES):
                try:
                    items, pages, total = _search_page(http, make, model, page, order)
                except FetchError as e:
                    errors.append(str(e))
                    break
                for listing in filter(None, map(_listing, items)):
                    found[listing.source_id] = listing
                    seen.add(listing.source_id)
                page += 1
            if len(errors) > failures or len(seen) >= total:
                break
        log.info("autotrader %s %s: %d of %d ads", make, model, len(seen), total)
    return SourceResult(list(found.values()), errors, http.requests)


def _search_page(http, make, model, page, order):
    html = http.get(URL.format(make=make, model=model, page=page, order=order))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise FetchError(f"no results data on {make} {model} page {page} (layout change or bot check)")
    props = json.loads(m.group(1))["props"]["pageProps"]
    return props.get("listings") or [], props.get("numberOfPages") or 1, props.get("numberOfResults") or 0


def _listing(item):
    vehicle = item.get("vehicle") or {}
    location = item.get("location") or {}
    seller = item.get("seller") or {}
    if not item.get("id") or not item.get("url"):
        return None
    trim_id = re.search(r"trim_id:(\d+)", (item.get("tracking") or {}).get("modelTaxonomy") or "")
    variant = vehicle.get("variant") or vehicle.get("model") or ""
    fuel = FUELS.get(vehicle.get("fuel"), "")
    if fuel == "hybrid" and "plug" in variant.lower():
        fuel = "phev"
    version = (vehicle.get("modelVersionInput") or "").strip()
    return Listing(
        source="autotrader",
        source_id=item["id"],
        url=item["url"],
        title=f"{vehicle.get('modelYear') or ''} {vehicle.get('make') or ''} {variant} {version}".strip(),
        make=vehicle.get("make") or "",
        model=variant,
        year=to_int(vehicle.get("modelYear")),
        trim=version,
        site_trim=TRIMS.get(trim_id.group(1), "") if trim_id else "",
        fuel=fuel,
        price=to_int((item.get("price") or {}).get("priceRaw")),
        km=to_int(vehicle.get("mileageInKm")),
        city=tidy_city(location.get("city")),
        province=(location.get("provinceCode") or "").upper(),
        postal=location.get("zip") or "",
        dealer=seller.get("companyName") or "",
        seller_type="private" if (seller.get("type") or "").lower().startswith("priv") else "dealer",
        condition=CONDITIONS.get(vehicle.get("offerType"), "used"),
        text=strip_html(item.get("description"))[:6000],
    )
