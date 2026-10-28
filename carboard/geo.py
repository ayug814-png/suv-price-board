"""City coordinates for the distance-from-home column, cached on disk.

Kijiji listings carry exact coordinates, which seed the cache for free. Any other city is looked up once on
OpenStreetMap's Nominatim service (at most one request a second) and kept.
"""
import json
import math
import time
import urllib.parse
from pathlib import Path

from .http import FetchError, Fetcher
from .util import PROVINCES, city_key

NOMINATIM = "https://nominatim.openstreetmap.org/search?"
RETRY_MISSES_AFTER = 7 * 86400


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


class Geo:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}
        self.http = Fetcher(min_gap=1.1, jitter=0.3, retries=1, user_agent="CarPriceBoard/1.0 (personal price tracker)")
        self.lookups = 0

    @staticmethod
    def _key(city, province):
        return f"{city_key(city)}|{province}"

    def coords(self, city, province):
        hit = self.cache.get(self._key(city, province))
        return (hit["lat"], hit["lon"]) if hit and hit.get("lat") is not None else None

    def learn(self, city, province, lat, lon):
        """Seed the cache with coordinates that came with a listing."""
        if city and province and lat is not None and lon is not None and not self.coords(city, province):
            self.cache[self._key(city, province)] = {"lat": round(lat, 4), "lon": round(lon, 4), "via": "listing"}

    def lookup(self, city, province):
        """Geocode one city unless it's cached. Returns (lat, lon) or None."""
        found = self.coords(city, province)
        if found:
            return found
        key = self._key(city, province)
        if time.time() - self.cache.get(key, {}).get("missed_at", 0) < RETRY_MISSES_AFTER:
            return None
        self.lookups += 1
        region = PROVINCES.get(province, "")
        queries = [
            {"city": city, "state": region, "country": "Canada"} if region else {"city": city, "country": "Canada"},
            {"q": f"{city}, {region}" if region else city, "countrycodes": "ca"},
        ]
        for query in queries:
            try:
                rows = json.loads(self.http.get(NOMINATIM + urllib.parse.urlencode({"format": "jsonv2", "limit": 1, **query}),
                                                accept="application/json"))
            except (FetchError, ValueError):
                return None  # network trouble: try again next run
            if rows:
                lat, lon = float(rows[0]["lat"]), float(rows[0]["lon"])
                self.cache[key] = {"lat": round(lat, 4), "lon": round(lon, 4), "via": "nominatim"}
                return lat, lon
        self.cache[key] = {"lat": None, "lon": None, "missed_at": time.time()}
        return None

    def nearest_province(self, lat, lon, max_km=150):
        """Province of the closest known city, for Kijiji private sellers who only give a map pin."""
        best = None
        for key, hit in self.cache.items():
            province = key.rsplit("|", 1)[1]
            if hit.get("lat") is None or not province:
                continue
            d = distance_km((lat, lon), (hit["lat"], hit["lon"]))
            if d <= max_km and (best is None or d < best[0]):
                best = (d, province)
        return best[1] if best else ""

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.cache, indent=0, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
