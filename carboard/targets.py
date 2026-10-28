"""The four cars on the board and the rules that decide which listings belong in each column."""
import re

from .util import norm

TARGETS = [
    {
        "key": "tucson_pref_pano",
        "name": "Tucson Preferred",
        "detail": "w/ Panoramic Sunroof · Gas",
        "label": "2025 Hyundai Tucson Preferred w/ Panoramic Sunroof",
        "rule": "Gas Tucson in Preferred trim with proof of the panoramic sunroof: the Trend package, "
                "'panoramic'/'sunroof' in the title, a Trend or SEL Convenience trim code, or a VIN in the "
                "Preferred-with-Trend series (5NMJC…, 3KMJC…). The 2025 Tucson's only sunroof is the panoramic one.",
    },
    {
        "key": "tucson_hev_nline",
        "name": "Tucson Hybrid N Line",
        "detail": "Panoramic sunroof standard",
        "label": "2025 Hyundai Tucson Hybrid N Line",
        "rule": "Tucson Hybrid (not plug-in) in N Line trim, the lowest 2025 hybrid trim in Canada; the panoramic "
                "sunroof is standard on it. Hybrids that a US-based VIN decoder calls 'SEL Convenience' share the "
                "N Line's VIN series (so do some Ultimates), so they're shown as likely matches (?).",
    },
    {
        "key": "crv_exl_hybrid",
        "name": "CR-V EX-L Hybrid",
        "detail": "2025",
        "label": "2025 Honda CR-V EX-L Hybrid",
        "rule": "CR-V in EX-L trim that is a hybrid, or doesn't state its fuel (the 2025 EX-L is hybrid-only in "
                "Canada). Gas EX-Ls (US imports) are left out.",
    },
    {
        "key": "crv_sport_gas",
        "name": "CR-V Sport",
        "detail": "Gas",
        "label": "2025 Honda CR-V Sport (Gas)",
        "rule": "CR-V in Sport trim with a gas engine. Sport Hybrid, Sport-L and Sport Touring are left out.",
    },
]

# (pattern, trim). A longer match swallows shorter ones inside it, so 'Sport Touring' isn't also 'Sport'
# and 'EX-L' isn't also 'EX'; the first trim named in the title is the car's trim (later ones are usually
# sales talk like "the ultimate deal"). Only 2025 trim names are listed, so words like "limited" stay neutral.
TUCSON_TRIMS = [
    (r"\bsel convenience\b", "sel convenience"),
    (r"\bpreferred\b|\bprivilegie\b", "preferred"),
    (r"\bessential\b|\bessentiel\b", "essential"),
    (r"\bn[ -]?line", "n line"),
    (r"\bultimate\b", "ultimate"),
    (r"\bxrt\b", "xrt"),
    (r"\bnight edition\b", "night edition"),
    (r"\bsel\b", "sel"),
]
CRV_TRIMS = [
    (r"\bsport[ -]?touring\b", "sport touring"),
    (r"\bsport[ -]l\b", "sport-l"),
    (r"\btrail ?sport\b", "trailsport"),
    (r"\bsport\b", "sport"),
    (r"\bex[ -]?l\b", "ex-l"),
    (r"\btouring\b", "touring"),
    (r"\blx\b", "lx"),
    (r"\bex\b", "ex"),
    (r"\bse\b", "se"),
    (r"\bblack edition\b", "black edition"),
]

# 'Trend' package, its French name, or Hyundai Canada's model code for it (TUCWDK2EPRTR vs. base TUCWDK2EPR00).
TREND = re.compile(r"\btrend\b|\btendance\b|\btuc[a-z0-9]{5,}prtr\b")
# In a title any roof wording counts: every 2025 Tucson sunroof is the panoramic one.
ROOF_IN_TITLE = re.compile(r"\bpano\w*|\bsun ?roof|\bmoon ?roof|\btoit\b")
# Descriptions need the explicit phrase; checklists of generic features are weaker evidence.
PANO_IN_TEXT = re.compile(r"\bpano(?:ramic|ramique|rama)?[ -]*(?:glass[ -]*)?(?:sun|moon)?[ -]*roof|\bpanoroof|\btoit (?:ouvrant )?pano")
ROOF_IN_TEXT = re.compile(r"\bsun ?roof|\bmoon ?roof|\btoit ouvrant")
PLUG_IN = re.compile(r"plug[ -]?in|\bphev\b|rechargeable")
HYBRID = re.compile(r"\bhybrid\b|\bhybride\b|\bhev\b")


def _trims(text, patterns):
    """Every trim named in the text, in order of appearance."""
    found = sorted((m.start(), -len(m.group(0)), m.end(), name) for pattern, name in patterns for m in re.finditer(pattern, text))
    names, covered_to = [], -1
    for start, _, end, name in found:
        if start >= covered_to:
            names.append(name)
            covered_to = end
    return names


def _powertrain(listing, ident):
    text = norm(listing.model) + " " + ident
    if listing.fuel == "phev" or PLUG_IN.search(text):
        return "phev"
    if listing.fuel == "hybrid" or HYBRID.search(text):
        return "hybrid"
    return listing.fuel  # gas, electric, or '' when the listing doesn't say


def _tucson_vin_series(vin):
    """Character 5 of a Tucson VIN is the trim series. On gas Tucsons B = Preferred and C = Preferred w/ Trend
    (US decoders call it SEL Convenience); on hybrids C covers N Line and Ultimate, so it means nothing there."""
    vin = (vin or "").upper()
    if len(vin) == 17 and vin[:3] in ("5NM", "KM8", "3KM") and vin[3] == "J":
        return vin[4]
    return ""


def classify(listing):
    """Return (target key, 'confirmed' | 'likely', evidence) or None if the listing isn't one of the four cars."""
    if listing.year != 2025:
        return None
    ident = norm(f"{listing.title} {listing.trim}")
    family = norm(f"{listing.make} {listing.model} {listing.title}")
    if "hyundai" in family and "tucson" in family:
        return _tucson(listing, ident)
    if "honda" in family and re.search(r"\bcr[ -]?v\b", family):
        return _crv(listing, ident)
    return None


def _tucson(listing, ident):
    power = _powertrain(listing, ident)
    if power in ("phev", "electric"):
        return None
    site_trim = norm(listing.site_trim)
    trims = _trims(ident, TUCSON_TRIMS) or _trims(site_trim, TUCSON_TRIMS)
    if power == "hybrid":
        return _tucson_hybrid_n_line(listing, trims)
    return _tucson_preferred_pano(listing, ident, site_trim, trims)


def _tucson_hybrid_n_line(listing, trims):
    trim = trims[0] if trims else ""
    if trim == "n line" or (trim in ("sel convenience", "sel") and "n line" in trims):
        return "tucson_hev_nline", "confirmed", "N Line hybrid (panoramic sunroof is standard)"
    if trim == "sel convenience" and _tucson_vin_series(listing.vin) in ("C", ""):
        return "tucson_hev_nline", "likely", "listed as SEL Convenience, the US name for this VIN series, which covers Canadian N Line and some Ultimate hybrids"
    return None


def _tucson_preferred_pano(listing, ident, site_trim, trims):
    trim = trims[0] if trims else ""
    vin_trend = _tucson_vin_series(listing.vin) == "C"
    trend_named = bool(TREND.search(ident) or TREND.search(site_trim))
    if not (trim in ("preferred", "sel convenience") or (trim in ("", "sel") and (vin_trend or trend_named))):
        return None
    target = "tucson_pref_pano"

    strong = []
    if TREND.search(site_trim) or "sel convenience" in site_trim:
        strong.append(f"trim listed as {listing.site_trim}")
    elif "sel convenience" in ident:
        strong.append("listed as SEL Convenience (same equipment as Preferred w/ Trend)")
    if vin_trend:
        strong.append("VIN is in the Preferred-w/-Trend series")
    for pattern in (TREND, ROOF_IN_TITLE):
        m = pattern.search(ident)
        if m:
            strong.append(f"'{m.group(0)}' in title")
    text = norm(listing.text)
    m = TREND.search(text) or PANO_IN_TEXT.search(text)
    if m:
        strong.append(f"'{m.group(0)}' in description")
    if strong:
        return target, "confirmed", "; ".join(dict.fromkeys(strong))

    weak = []
    m = ROOF_IN_TEXT.search(text)
    if m:
        weak.append(f"'{m.group(0)}' in description")
    if "sunroof" in listing.features:
        weak.append("sunroof ticked in the listing's feature list")
    if weak:
        return target, "likely", "; ".join(weak)
    return None


def _crv(listing, ident):
    trims = _trims(ident, CRV_TRIMS) or _trims(norm(listing.site_trim), CRV_TRIMS)
    trim = trims[0] if trims else ""
    power = _powertrain(listing, ident)
    if power == "electric":
        power = ""  # there's no electric 2025 CR-V in Canada; that's a mis-set fuel field
    if trim == "ex-l":
        if power == "hybrid":
            return "crv_exl_hybrid", "confirmed", "EX-L hybrid"
        if power == "":
            return "crv_exl_hybrid", "confirmed", "EX-L (hybrid-only trim for 2025 in Canada; fuel not stated)"
        return None
    if trim == "sport" and power in ("gas", ""):
        return "crv_sport_gas", "confirmed", "Sport, gas" if power else "Sport (gas-only trim for 2025 in Canada)"
    return None
