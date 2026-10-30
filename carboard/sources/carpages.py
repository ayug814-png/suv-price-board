"""Carpages.ca. Each results page carries its listings as schema.org JSON-LD offers (50 per page).

The site sits behind a bot shield that sometimes challenges bursts of requests, so it is paced slowly.
"""
import json
import re

from ..http import FetchError, Fetcher
from ..models import Listing, SourceResult
from ..util import province_code, tidy_city, to_int

NAME = "Carpages.ca"
SHORT = "CP"
SEARCHES = [("Hyundai", "Tucson", 2025), ("Honda", "CR-V", 2025), ("Kia", "Sportage", 2025), ("Hyundai", "Kona", 2026)]
URL = "https://www.carpages.ca/used-cars/search/?make_name={make}&model_name={model}&year_start={year}&year_end={year}&page={page}"
PAGE_SIZE = 50
MAX_PAGES = 10
LISTING_URL = re.compile(r"carpages\.ca/(used|new)-cars/([^/]+)/([^/]+)/(\d{4})-[^/]*?-(\d+)/?$")
CARD_LINK = re.compile(r'href="/(?:used|new)-cars/[^"]*?-(\d+)/"')
KM = re.compile(r'((?:<span class="number">[\d,]</span>)+)\s*<span>K</span>\s*<span>M</span>')


def fetch(log):
    http = Fetcher(min_gap=5.0, jitter=3.0)
    found, errors = {}, []
    for make, model, year in SEARCHES:
        page = 1
        while page <= MAX_PAGES:
            try:
                html = http.get(URL.format(make=make, model=model, year=year, page=page))
                if "bunny-shield" in html[:3000]:
                    raise FetchError(f"bot check on {year} {make} {model} page {page}")
            except FetchError as e:
                errors.append(str(e))
                break
            total = to_int((re.search(r"([\d,]+)\s+results", html) or [None, "0"])[1]) or 0
            km_by_id = _mileages(html)
            new = 0
            for offer in _offers(html):
                listing = _listing(offer, km_by_id, make, model)
                if listing and listing.source_id not in found:
                    found[listing.source_id] = listing
                    new += 1
            if not new or page * PAGE_SIZE >= total:
                break
            page += 1
        log.info("carpages %d %s %s: %d pages", year, make, model, page)
    return SourceResult(list(found.values()), errors, http.requests)


def _offers(html):
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        offers = data.get("offers") if isinstance(data, dict) else None
        if isinstance(offers, list):
            return offers
    return []


def _mileages(html):
    """Listing id -> km. Each card shows its odometer as one <span> per digit."""
    links = [(m.start(), m.group(1)) for m in CARD_LINK.finditer(html)]
    mileages = {}
    for i, (start, listing_id) in enumerate(links):
        if listing_id in mileages:
            continue
        end = next((s for s, other in links[i + 1:] if other != listing_id), len(html))
        m = KM.search(html, start, end)
        if m:
            mileages[listing_id] = to_int(re.sub(r"<[^>]+>", "", m.group(1)))
    return mileages


def _listing(offer, km_by_id, make, model):
    url = offer.get("url") or ""
    m = LISTING_URL.search(url)
    if not m:
        return None
    condition, province_slug, city_slug, year, listing_id = m.groups()
    title = offer.get("itemOffered") or ""
    return Listing(
        source="carpages",
        source_id=listing_id,
        url=url,
        title=title,
        make=make,
        model=f"{model} Hybrid" if "-hybrid-" in url else model,
        year=to_int(year),
        trim=title,
        price=to_int(offer.get("price")),
        km=km_by_id.get(listing_id),
        city=tidy_city(city_slug.replace("-", " ")),
        province=province_code(province_slug),
        condition=condition,
    )
