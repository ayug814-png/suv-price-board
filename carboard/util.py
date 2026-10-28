"""Text and location normalisation shared by the sources, the matching rules and the board."""
import html
import re
import unicodedata

PROVINCES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador", "NS": "Nova Scotia", "NT": "Northwest Territories",
    "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}


def strip_accents(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_PROVINCE_ALIASES = {strip_accents(name).lower(): code for code, name in PROVINCES.items()}
_PROVINCE_ALIASES.update({"newfoundland": "NL", "pei": "PE", "yukon territory": "YT"})


def norm(text):
    """Lower-case, accent-free, single-spaced text for keyword matching."""
    text = strip_accents(html.unescape(text or "")).lower()
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text):
    text = re.sub(r"<br\s*/?>|</p>|</li>", " ", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def province_code(value):
    """'ON', 'Ontario' or 'british-columbia' -> two-letter code; '' when unknown."""
    if not value:
        return ""
    value = value.strip()
    if value.upper() in PROVINCES:
        return value.upper()
    return _PROVINCE_ALIASES.get(strip_accents(value.replace("-", " ")).lower().strip(" ."), "")


_POSTAL_PROVINCES = {
    "A": "NL", "B": "NS", "C": "PE", "E": "NB", "G": "QC", "H": "QC", "J": "QC", "K": "ON", "L": "ON",
    "M": "ON", "N": "ON", "P": "ON", "R": "MB", "S": "SK", "T": "AB", "V": "BC", "Y": "YT",
}


def province_from_postal(postal):
    """The first letter of a Canadian postal code fixes the province: 'P1B 7M2' -> 'ON'."""
    return _POSTAL_PROVINCES.get((postal or "").strip()[:1].upper(), "")


def tidy_city(city):
    """Fix ALL-CAPS or lower-case city names from dealer feeds: 'SAINT-HUBERT' -> 'Saint-Hubert'."""
    city = re.sub(r"\s+", " ", (city or "").strip(" ,"))
    city = re.sub(r"^(city of|ville de)\s+", "", city, flags=re.I)
    if city and (city.isupper() or city.islower()):
        city = " ".join("-".join(p[:1].upper() + p[1:].lower() for p in word.split("-")) for word in city.split(" "))
    return city


def city_key(city):
    """Grouping key, so 'St. Catharines', 'ST CATHARINES' and 'Saint Catharines' share one row."""
    key = norm(city).replace(".", " ").replace("'", "").replace("-", " ")
    key = re.sub(r"\bsainte\b", "ste", key)
    key = re.sub(r"\bsaint\b", "st", key)
    key = re.sub(r"^(greater|city of)\s+", "", key.strip())  # 'Greater Sudbury' is Sudbury
    return re.sub(r"\s+", " ", key).strip()


def to_int(value):
    """'22,591 km' -> 22591; None or '' -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value))
    return int(digits) if digits else None
