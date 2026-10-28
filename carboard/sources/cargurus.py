"""CarGurus.ca. Search pages are a Remix app; adding _data=<route> returns the page's results as JSON.

CarGurus decodes each car's trim from its VIN, so for each model we read the trim filter list and only page
through the trims that can belong on the board. Detail pages block scripts, but links open fine in a browser.
"""
import json
import re
import urllib.parse

from ..http import FetchError, Fetcher
from ..models import Listing, SourceResult
from ..util import tidy_city, to_int

NAME = "CarGurus.ca"
SHORT = "CG"
BASE = "https://www.cargurus.ca/Cars/l-Used-{slug}?distance=50000&startYear=2025&endYear=2025"
ROUTE = "_data=" + urllib.parse.quote("routes/($intl).Cars.$seoPath", safe="")
SEARCHES = [  # (model slug, which of CarGurus' trim names to page through)
    ("Hyundai-Tucson-d98", r"preferred|trend|sel convenience"),
    ("Hyundai-Tucson-Hybrid-d3141", r"n line|sel convenience"),
    ("Honda-CR-V-d589", r"^sport\b(?!.*touring)"),
    ("Honda-CR-V-Hybrid-d3002", r"\bex-?l\b"),
    ("Kia-Sportage-d164", r"^ex\b(?!.*prem)"),
    ("Kia-Sportage-Hybrid-d3239", r"^ex\b(?!.*prem)"),
]
MAX_PAGES = 20
PAGE_SIZE = 24
FUELS = {"Gasoline": "gas", "Hybrid": "hybrid", "Plug-In Hybrid": "phev", "Electric": "electric"}


def fetch(log):
    http = Fetcher(min_gap=3.0, jitter=2.0)
    found, errors = {}, []
    for slug, trim_filter in SEARCHES:
        base = BASE.format(slug=slug)
        try:
            first = _search(http, base)
        except FetchError as e:
            errors.append(str(e))
            continue
        trim_paths = [
            trim["value"]
            for group in (first.get("filters", {}).get("MODEL_TRIM") or {}).get("filters", [])
            for trim in group.get("filters", [])
            if trim.get("count", 0) > 0 and re.search(trim_filter, trim.get("label", ""), re.I)
        ]
        for path in trim_paths:
            page, pages = 1, 1
            while page <= min(pages, MAX_PAGES):
                try:
                    search = _search(http, f"{base}&makeModelTrimPaths={urllib.parse.quote(path, safe='')}&page={page}")
                except FetchError as e:
                    errors.append(str(e))
                    break
                # pageCount runs one past the real last page, which then fails; count pages from the total instead.
                pages = min(search.get("pageCount") or 1, -(-(search.get("totalListings") or 0) // PAGE_SIZE))
                for listing in filter(None, map(_listing, search.get("tiles") or [])):
                    found[listing.source_id] = listing
                page += 1
        log.info("cargurus %s: trims %s", slug, trim_paths)
    return SourceResult(list(found.values()), errors, http.requests)


def _search(http, url):
    body = http.get(f"{url}&{ROUTE}", accept="*/*")
    try:
        data, _ = json.JSONDecoder().raw_decode(body, 0)
        return data["search"]
    except (ValueError, KeyError, TypeError):
        raise FetchError(f"unexpected response (layout change or bot check) for {url}")


def _listing(tile):
    data = tile.get("data") or {}
    ontology = data.get("ontologyDto")
    if not ontology or not data.get("id"):
        return None
    seller = data.get("sellerDto") or {}
    mileage = data.get("mileage") or {}
    km = mileage.get("value")
    if km is not None and mileage.get("unit") == "MILES":
        km = km * 1.609
    options = data.get("options") or []
    dealer = seller.get("serviceProviderName") or ""
    city = seller.get("city") or ""
    if not city and " - " in dealer:  # online retailers such as "Clutch - Halifax" list no address
        city = dealer.rsplit(" - ", 1)[1]
    return Listing(
        source="cargurus",
        source_id=str(data["id"]),
        url=f"https://www.cargurus.ca/details/{data['id']}",
        title=f"{ontology.get('carYear')} {ontology.get('makeName')} {ontology.get('modelName')} {ontology.get('trimName') or ''}".strip(),
        make=ontology.get("makeName") or "",
        model=ontology.get("modelName") or "",
        year=to_int(ontology.get("carYear")),
        trim=ontology.get("trimName") or "",
        site_trim=ontology.get("trimName") or "",
        fuel=FUELS.get((data.get("fuelDto") or {}).get("type"), ""),
        price=to_int((data.get("priceDto") or {}).get("current")),
        km=to_int(km),
        city=tidy_city(city),
        province=(seller.get("region") or "").upper(),
        postal=seller.get("postalCode") or "",
        dealer=dealer,
        seller_type="private" if seller.get("sellerType") == "PRIVATE" else "dealer",
        condition="used",
        vin=(data.get("vin") or "").upper(),
        features=["sunroof"] if any(re.search(r"sunroof|moonroof", o, re.I) for o in options) else [],
    )
