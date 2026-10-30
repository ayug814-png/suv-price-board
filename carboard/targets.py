"""The cars on the board and the rules that decide which listings belong in each column."""
import dataclasses
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
    {
        "key": "sportage_ex_gas",
        "name": "Sportage EX",
        "detail": "w/ Panoramic Sunroof · Gas",
        "label": "2025 Kia Sportage EX w/ Panoramic Sunroof (Gas)",
        "rule": "Gas Sportage in EX trim with proof of the panoramic sunroof: any roof wording in the title, or "
                "'panoramic sunroof' in the description. A plain 'sunroof' in the description or a ticked sunroof "
                "box makes it a likely match (?). The 2025 Sportage's only sunroof is the panoramic one. EX Premium, "
                "X-Line and the hybrids are left out; an EX whose ad doesn't state the fuel counts as gas unless it "
                "mentions a hybrid (every site lists the Sportage Hybrid as its own model).",
    },
    {
        "key": "sportage_ex_hybrid",
        "name": "Sportage EX Hybrid",
        "detail": "w/ Panoramic Sunroof",
        "label": "2025 Kia Sportage EX Hybrid w/ Panoramic Sunroof",
        "rule": "Sportage Hybrid (not plug-in) in EX trim with proof of the panoramic sunroof, judged the same way as "
                "the gas EX. EX Premium and SX hybrids are left out.",
    },
    {
        "key": "kona_pref_sunroof",
        "name": "Kona Preferred",
        "detail": "2026 · w/ Sunroof (Trend)",
        "label": "2026 Hyundai Kona Preferred w/ Sunroof",
        "rule": "2026 Kona (gas) in Preferred trim with proof of the sunroof, which on the Preferred only comes with the "
                "Trend package: 'Trend' in the title or description, sunroof wording in the title, or a VIN in the "
                "Preferred-with-Trend series (KM8HC…). A plain 'sunroof' in the description or a ticked sunroof box makes "
                "it a likely match (?). 'Panoramic' alone doesn't count: Hyundai also calls the Kona's screens a panoramic "
                "display. Kona Electric is left out.",
    },
    {
        "key": "kona_nline",
        "name": "Kona N Line",
        "detail": "2026 · Sunroof standard",
        "label": "2026 Hyundai Kona N Line",
        "rule": "2026 Kona N Line without the Ultimate package (those have their own column), named in the title or trim "
                "or shown by a VIN in the N Line series (KM8HA… with the 1.6L turbo); the sunroof is standard on it.",
    },
    {
        "key": "kona_nline_ult",
        "name": "Kona N Line Ultimate",
        "detail": "2026 · Sunroof standard",
        "label": "2026 Hyundai Kona N Line Ultimate w/ Sunroof",
        "rule": "2026 Kona N Line with the Ultimate package, named in the title or trim or shown by a VIN in the N Line "
                "Ultimate series (KM8HE…); the sunroof is standard on it. A plain N Line goes in the Kona N Line column.",
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
# Canadian names (EX Premium, X-Line Limited) and US ones (X-Pro, SX Prestige), so a US import's trim isn't read as EX.
SPORTAGE_TRIMS = [
    (r"\bex[ _-]?prem(?:ium)?\b", "ex premium"),
    (r"\bx[ -]?line\b", "x-line"),
    (r"\bx[ -]?pro\b", "x-pro"),
    (r"\bsx\b", "sx"),
    (r"\blx\b", "lx"),
    (r"\bex\b", "ex"),
]

# Canada's 2026 Kona trims; the Ultimate package is checked separately, so 'N Line Ultimate' reads as the N Line.
KONA_TRIMS = [
    (r"\bpreferred\b|\bprivilegie\b", "preferred"),
    (r"\bessential\b|\bessentiel\b", "essential"),
    (r"\bn[ -]?line", "n line"),
]
ULTIMATE = re.compile(r"\bultimate\b|\bult\b")


def _kona_vin_trim(vin):
    """The trim a 2026 Kona's VIN encodes (checked against 112 dealer ads that name their trim): character 5 is the
    trim series (A = Essential or N Line, B = Preferred, C = Preferred with Trend, E = N Line with Ultimate) and
    character 8 the engine (3 = the N Line's 1.6L turbo)."""
    vin = (vin or "").upper()
    if len(vin) != 17 or not vin.startswith("KM8H"):
        return ""
    if vin[4] == "A":
        return "n line" if vin[7] == "3" else "essential"
    return {"B": "preferred", "C": "preferred trend", "E": "n line ultimate"}.get(vin[4], "")

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
    """Return (target key, 'confirmed' | 'likely', evidence) or None if the listing isn't one of the board's cars."""
    ident = norm(f"{listing.title} {listing.trim}")
    family = norm(f"{listing.make} {listing.model} {listing.title}")
    if "hyundai" in family and re.search(r"\bkona\b", family):
        return _kona(listing, ident) if listing.year == 2026 else None
    if listing.year != 2025:
        return None
    if "hyundai" in family and "tucson" in family:
        return _tucson(listing, ident)
    if "honda" in family and re.search(r"\bcr[ -]?v\b", family):
        return _crv(listing, ident)
    if "kia" in family and "sportage" in family:
        return _sportage(listing, ident)
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


def _sportage(listing, ident):
    trims = _trims(ident, SPORTAGE_TRIMS) or _trims(norm(listing.site_trim), SPORTAGE_TRIMS)
    if (trims[0] if trims else "") != "ex":
        return None
    power = _powertrain(listing, ident)
    if power == "hybrid":
        target, trim = "sportage_ex_hybrid", "EX hybrid"
    elif power == "gas":
        target, trim = "sportage_ex_gas", "EX, gas"
    elif power == "":
        target, trim = "sportage_ex_gas", "EX (fuel not stated and no hybrid mentioned, so gas)"
    else:
        return None  # plug-in hybrid, or an electric fuel setting that could be either column

    # The panoramic roof is the 2025 Sportage's only sunroof, so any roof wording in the title proves it. A bare
    # 'panoramic' doesn't: Kia also calls the dashboard screens the "panoramic curved display".
    text = norm(listing.text)
    strong = []
    m = PANO_IN_TEXT.search(ident) or ROOF_IN_TEXT.search(ident)
    if m:
        strong.append(f"'{m.group(0)}' in title")
    m = PANO_IN_TEXT.search(text)
    if m:
        strong.append(f"'{m.group(0)}' in description")
    if strong:
        return target, "confirmed", "; ".join([trim] + strong)

    weak = []
    m = ROOF_IN_TEXT.search(text)
    if m:
        weak.append(f"'{m.group(0)}' in description")
    if "sunroof" in listing.features:
        weak.append("sunroof ticked in the listing's feature list")
    if weak:
        return target, "likely", "; ".join([trim] + weak)
    return None


def _kona(listing, ident):
    electric = re.search(r"\belectri(?:c|que)\b|\bev\b", f"{norm(listing.model)} {ident}")
    if electric or _powertrain(listing, ident) not in ("gas", ""):
        return None  # Kona Electric, even when the ad doesn't set its fuel
    site_trim = norm(listing.site_trim)
    trims = _trims(ident, KONA_TRIMS) or _trims(site_trim, KONA_TRIMS)
    trim = trims[0] if trims else ""
    vin_trim = _kona_vin_trim(listing.vin)
    if trim == "n line" or (trim == "" and vin_trim.startswith("n line")):
        if ULTIMATE.search(ident) or ULTIMATE.search(site_trim):
            return "kona_nline_ult", "confirmed", "N Line with the Ultimate package (sunroof standard)"
        if vin_trim == "n line ultimate":
            return "kona_nline_ult", "confirmed", "VIN is in the N Line Ultimate series (sunroof standard)"
        return "kona_nline", "confirmed", "N Line (sunroof standard)" if trim else "VIN is in the N Line series (sunroof standard)"
    if trim != "preferred" and not (trim == "" and vin_trim == "preferred trend"):
        return None

    # Only the Trend package brings a sunroof to the Preferred, so naming either is proof.
    text = norm(listing.text)
    strong = []
    for where, haystack in (("title", ident), ("trim", site_trim), ("description", text)):
        m = TREND.search(haystack)
        if m:
            strong.append(f"'{m.group(0)}' in {where}")
    m = ROOF_IN_TEXT.search(ident)
    if m:
        strong.append(f"'{m.group(0)}' in title")
    if vin_trim == "preferred trend":
        strong.append("VIN is in the Preferred-with-Trend series")
    if strong:
        return "kona_pref_sunroof", "confirmed", "; ".join(dict.fromkeys(strong))

    weak = []
    m = ROOF_IN_TEXT.search(text)
    if m:
        weak.append(f"'{m.group(0)}' in description")
    if "sunroof" in listing.features:
        weak.append("sunroof ticked in the listing's feature list")
    if weak:
        return "kona_pref_sunroof", "likely", "; ".join(weak)
    return None


def wants_description(listing):
    """Whether a description could still change this listing's match: it would match with proof of the sunroof but
    its title doesn't prove it. Lets a source fetch only the vehicle pages it needs."""
    hit = classify(listing)
    if hit and hit[1] == "confirmed":
        return False
    return classify(dataclasses.replace(listing, text="panoramic sunroof")) is not None
