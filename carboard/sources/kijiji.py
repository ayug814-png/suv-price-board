"""Kijiji (Kijiji Autos was folded into kijiji.ca). Results sit in the page's Apollo cache inside __NEXT_DATA__."""
import json
import re

from ..http import FetchError, Fetcher
from ..models import Listing, SourceResult
from ..util import strip_html, tidy_city, to_int

NAME = "Kijiji"
SHORT = "KJ"
SEARCHES = [
    "carmake=hyundai&carmodel=tucson__tucson_hybrid&caryear=2025__2025",
    "carmake=honda&carmodel=crv&caryear=2025__2026",
]
URL = "https://www.kijiji.ca/b-cars-trucks/canada/{page}c174l0?{query}"
PAGE_SIZE = 40
MAX_PAGES = 15
FUELS = {"gas": "gas", "hybrid": "hybrid", "electric": "electric"}
SKIP_TYPES = {"lease", "damaged", "salvage"}
ADDRESS = re.compile(r"([^,]+),\s*(AB|BC|MB|NB|NL|NS|NT|NU|ON|PE|QC|SK|YT)\b")


def fetch(log):
    http = Fetcher(min_gap=2.0)
    found, errors = {}, []
    for query in SEARCHES:
        page, pages = 1, 1
        while page <= min(pages, MAX_PAGES):
            try:
                items, total = _search_page(http, query, page)
            except FetchError as e:
                errors.append(str(e))
                break
            pages = -(-total // PAGE_SIZE)
            for listing in filter(None, map(_listing, items)):
                found[listing.source_id] = listing
            page += 1
        log.info("kijiji %s: %d pages", query, page - 1)
    return SourceResult(list(found.values()), errors, http.requests)


def _search_page(http, query, page):
    html = http.get(URL.format(page="" if page == 1 else f"page-{page}/", query=query))
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        raise FetchError(f"no results data on page {page} of {query} (layout change or bot check)")
    apollo = json.loads(m.group(1))["props"]["pageProps"]["__APOLLO_STATE__"]
    search = next(v for k, v in apollo["ROOT_QUERY"].items() if k.startswith("searchResultsPageByUrl"))
    items = [v for k, v in apollo.items() if k.startswith("AutosListing:")]
    return items, (search.get("pagination") or {}).get("totalCount") or 0


def _listing(item):
    attrs = {a["canonicalName"]: a.get("canonicalValues") or [] for a in (item.get("attributes") or {}).get("all", [])}

    def attr(name):
        return (attrs.get(name) or [""])[0]

    if attr("vehicletype") in SKIP_TYPES or not item.get("url"):
        return None
    location = item.get("location") or {}
    address = ADDRESS.search(location.get("address") or "")
    coords = location.get("coordinates") or {}
    amount = (item.get("price") or {}).get("amount")
    return Listing(
        source="kijiji",
        source_id=str(item["id"]),
        url=item["url"],
        title=item.get("title") or "",
        make=attr("carmake"),
        model=attr("carmodel").replace("_", " "),
        year=to_int(attr("caryear")),
        trim=" | ".join(attrs.get("cartrim") or []),
        fuel=FUELS.get(attr("carfueltype"), ""),
        price=round(amount / 100) if isinstance(amount, (int, float)) else None,
        km=to_int(attr("carmileageinkms")),
        city=tidy_city(address.group(1) if address else location.get("name")),
        province=address.group(2) if address else "",
        lat=coords.get("latitude"),
        lon=coords.get("longitude"),
        seller_type="private" if attr("forsaleby") == "ownr" else "dealer",
        condition="new" if attr("vehicletype") == "new" else "used",
        vin=attr("vin").upper(),
        text=strip_html(item.get("description")),
        features=["sunroof"] if attr("sunroof") == "true" else [],
    )
