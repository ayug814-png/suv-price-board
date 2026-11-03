"""The cars on the board and the rules that decide which listings belong in each column."""
import dataclasses
import re

from .util import norm

TARGETS = [
    {
        "key": "tucson_pref_pano",
        "name": "Tucson Preferred",
        "detail": "2025 · w/ Panoramic Sunroof · Gas",
        "label": "2025 Hyundai Tucson Preferred w/ Panoramic Sunroof",
        "rule": "Gas Tucson in Preferred trim with proof of the panoramic sunroof: the Trend package, "
                "'panoramic'/'sunroof' in the title, a Trend or SEL Convenience trim code, or a VIN in the "
                "Preferred-with-Trend series (5NMJC…, 3KMJC…). The 2025 Tucson's only sunroof is the panoramic one.",
    },
    {
        "key": "tucson_hev_nline",
        "name": "Tucson Hybrid N Line",
        "detail": "2025 · Panoramic sunroof standard",
        "label": "2025 Hyundai Tucson Hybrid N Line",
        "rule": "Tucson Hybrid (not plug-in) in N Line trim, the lowest 2025 hybrid trim in Canada; the panoramic "
                "sunroof is standard on it. Hybrids that a US-based VIN decoder calls 'SEL Convenience' share the "
                "N Line's VIN series (so do some Ultimates), so they're shown as likely matches (?).",
    },
    {
        "key": "tucson_hev_ultimate_2026",
        "name": "Tucson Hybrid Ultimate",
        "detail": "2026 · Not plug-in",
        "label": "2026 Hyundai Tucson Hybrid Ultimate (not plug-in)",
        "rule": "2026 Tucson in Ultimate trim that is a regular hybrid. The plug-in hybrid, which Canada only gets "
                "as an Ultimate, is left out. There's no gas Ultimate for 2026, so an Ultimate whose ad doesn't say "
                "hybrid or plug-in is a likely match (?).",
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
        "detail": "2025 · Gas",
        "label": "2025 Honda CR-V Sport (Gas)",
        "rule": "CR-V in Sport trim with a gas engine. Sport Hybrid, Sport-L and Sport Touring are left out.",
    },
    {
        "key": "crv_exl_hybrid_2026",
        "name": "CR-V EX-L Hybrid",
        "detail": "2026",
        "label": "2026 Honda CR-V EX-L Hybrid",
        "rule": "2026 CR-V in EX-L trim that is a hybrid, or doesn't state its fuel (the 2026 EX-L is hybrid-only in "
                "Canada too). Gas EX-Ls (US imports) are left out.",
    },
    {
        "key": "crv_sport_gas_2026",
        "name": "CR-V Sport",
        "detail": "2026 · Gas",
        "label": "2026 Honda CR-V Sport (Gas)",
        "rule": "2026 CR-V in Sport trim with a gas engine. Sport Hybrid, TrailSport Hybrid, Sport-L and Sport "
                "Touring are left out.",
    },
    {
        "key": "crv_touring_hybrid_2026",
        "name": "CR-V Touring Hybrid",
        "detail": "2026",
        "label": "2026 Honda CR-V Touring Hybrid",
        "rule": "2026 CR-V in Touring trim that is a hybrid, or doesn't state its fuel (the Touring is hybrid-only in "
                "Canada). Sport Touring (a US trim) is left out.",
    },
    {
        "key": "cx5_gt",
        "name": "CX-5 GT",
        "detail": "2025 · Sunroof standard",
        "label": "2025 Mazda CX-5 GT",
        "rule": "CX-5 in GT trim. Every 2025 GT has the power glass moonroof (the GT builds on the GS with Comfort "
                "Package). Kuro, Sport Design, Suna and Signature are left out.",
    },
    {
        "key": "cx5_gt_pano_2026",
        "name": "CX-5 GT",
        "detail": "2026 · w/ Panoramic Sunroof",
        "label": "2026 Mazda CX-5 GT w/ Panoramic Sunroof",
        "rule": "2026 CX-5 in GT trim with proof of the panoramic roof, a $2,000 GT option and the 2026 CX-5's "
                "only sunroof: roof wording or the Premium Package (which requires the roof) in the title, either one "
                "named in the description, or the Premium Package ticked in the listing's options. A plain 'sunroof' in "
                "the description or a ticked sunroof box makes it a likely match (?).",
    },
]

# (pattern, trim). A longer match swallows shorter ones inside it, so 'Sport Touring' isn't also 'Sport'
# and 'EX-L' isn't also 'EX'; the first trim named in the title is the car's trim (later ones are usually
# sales talk like "the ultimate deal"). Only Canadian trim names are listed, so words like "limited" stay neutral;
# dealer sites shorten Ultimate to "Ult" ("Hev Ult").
TUCSON_TRIMS = [
    (r"\bsel convenience\b", "sel convenience"),
    (r"\bpreferred\b|\bprivilegie\b", "preferred"),
    (r"\bessential\b|\bessentiel\b", "essential"),
    (r"\bn[ -]?line", "n line"),
    (r"\bultimate\b|\bult\b", "ultimate"),
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
CX5_TRIMS = [
    (r"\bsport design\b", "sport design"),
    (r"\bsignature\b", "signature"),
    (r"\bsuna\b", "suna"),
    (r"\bkuro\b", "kuro"),
    (r"\bgt\b", "gt"),
    (r"\bgs\b", "gs"),
    (r"\bgx\b", "gx"),
]

# 'Trend' package, its French name, or Hyundai Canada's model code for it (TUCWDK2EPRTR vs. base TUCWDK2EPR00).
TREND = re.compile(r"\btrend\b|\btendance\b|\btuc[a-z0-9]{5,}prtr\b")
# In a title any roof wording counts: every 2025 Tucson sunroof is the panoramic one.
ROOF_IN_TITLE = re.compile(r"\bpano\w*|\bsun ?roof|\bmoon ?roof|\btoit\b")
# Descriptions need the explicit phrase; checklists of generic features are weaker evidence.
PANO_IN_TEXT = re.compile(r"\bpano(?:ramic|ramique|rama)?[ -]*(?:glass[ -]*)?(?:sun|moon)?[ -]*roof|\bpanoroof|\btoit (?:ouvrant )?pano")
ROOF_IN_TEXT = re.compile(r"\bsun ?roof|\bmoon ?roof|\btoit ouvrant")
# The 2026 CX-5 GT's Premium Package requires its panoramic roof. "Premium" alone isn't proof: the GT's Bose
# stereo is a "Bose Premium sound system".
PREMIUM_IN_TITLE = re.compile(r"(?:\bgt[ -]+|\bw/ ?|\bwith |\bavec |\b(?:ensemble|groupe) )premium\b"
                              r"(?! (?:audio|sound|stereo|speakers?|bose|leather|cuir)\b)"
                              r"|\bpremium (?:package|pkg|pack)\b")
PREMIUM_IN_TEXT = re.compile(r"\bpremium (?:package|pkg|pack)\b|\b(?:ensemble|groupe) premium\b")
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
    if listing.year not in (2025, 2026):
        return None
    ident = norm(f"{listing.title} {listing.trim}")
    family = norm(f"{listing.make} {listing.model} {listing.title}")
    if "hyundai" in family and "tucson" in family:
        return _tucson(listing, ident) if listing.year == 2025 else _tucson_hybrid_ultimate(listing, ident)
    if "honda" in family and re.search(r"\bcr[ -]?v\b", family):
        return _crv(listing, ident)
    if "mazda" in family and re.search(r"\bcx[ -]?5\b", family):
        return _cx5(listing, ident)
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


def _tucson_hybrid_ultimate(listing, ident):
    """2026: Canada's Ultimate comes as the hybrid or the plug-in hybrid, with no gas one."""
    trims = _trims(ident, TUCSON_TRIMS) or _trims(norm(listing.site_trim), TUCSON_TRIMS)
    if not trims or trims[0] != "ultimate":
        return None
    power = _powertrain(listing, ident)
    if power == "hybrid":
        return "tucson_hev_ultimate_2026", "confirmed", "Ultimate hybrid"
    if power in ("gas", ""):
        return "tucson_hev_ultimate_2026", "likely", "Ultimate; the ad doesn't say hybrid or plug-in"
    return None  # the plug-in hybrid, or a plug-in listed as electric


def _tucson_preferred_pano(listing, ident, site_trim, trims):
    trim = trims[0] if trims else ""
    vin_trend = _tucson_vin_series(listing.vin) == "C"
    trend_named = bool(TREND.search(ident) or TREND.search(site_trim))
    if not (trim in ("preferred", "sel convenience") or (trim in ("", "sel") and (vin_trend or trend_named))):
        return None

    strong = []
    if TREND.search(site_trim) or "sel convenience" in site_trim:
        strong.append(f"trim listed as {listing.site_trim}")
    elif "sel convenience" in ident:
        strong.append("listed as SEL Convenience (same equipment as Preferred w/ Trend)")
    if vin_trend:
        strong.append("VIN is in the Preferred-w/-Trend series")
    proof = _roof_proof(listing, ident, (TREND, ROOF_IN_TITLE), (TREND, PANO_IN_TEXT), strong)
    return ("tucson_pref_pano", *proof) if proof else None


def _roof_proof(listing, ident, in_title, in_text, strong=()):
    """('confirmed' | 'likely', evidence) for a car that only belongs on the board with its sunroof, or None. Proof in
    the title or the description (or passed in as `strong`) confirms it; a plain 'sunroof' in the description or a
    sunroof ticked in the listing's feature list makes it likely."""
    strong = list(strong)
    for pattern in in_title:
        m = pattern.search(ident)
        if m:
            strong.append(f"'{m.group(0)}' in title")
    text = norm(listing.text)
    m = next(filter(None, (pattern.search(text) for pattern in in_text)), None)
    if m:
        strong.append(f"'{m.group(0)}' in description")
    if strong:
        return "confirmed", "; ".join(dict.fromkeys(strong))

    weak = []
    m = ROOF_IN_TEXT.search(text)
    if m:
        weak.append(f"'{m.group(0)}' in description")
    if "sunroof" in listing.features:
        weak.append("sunroof ticked in the listing's feature list")
    return ("likely", "; ".join(weak)) if weak else None


def _crv(listing, ident):
    # The 2026 columns carry the year in their key; Canada's EX-L is hybrid-only and its Sport gas-only both years.
    year = "" if listing.year == 2025 else f"_{listing.year}"
    trims = _trims(ident, CRV_TRIMS) or _trims(norm(listing.site_trim), CRV_TRIMS)
    trim = trims[0] if trims else ""
    power = _powertrain(listing, ident)
    if power == "electric":
        power = ""  # there's no electric CR-V in Canada; that's a mis-set fuel field
    if trim == "ex-l":
        if power == "hybrid":
            return f"crv_exl_hybrid{year}", "confirmed", "EX-L hybrid"
        if power == "":
            return f"crv_exl_hybrid{year}", "confirmed", "EX-L (hybrid-only trim in Canada; fuel not stated)"
        return None
    if trim == "sport" and power in ("gas", ""):
        return f"crv_sport_gas{year}", "confirmed", "Sport, gas" if power else "Sport (gas-only trim in Canada)"
    if trim == "touring" and listing.year == 2026 and power in ("hybrid", ""):
        return "crv_touring_hybrid_2026", "confirmed", "Touring hybrid" if power else "Touring (hybrid-only trim in Canada; fuel not stated)"
    return None


def _cx5(listing, ident):
    trims = _trims(ident, CX5_TRIMS) or _trims(norm(listing.site_trim), CX5_TRIMS)
    if not trims or trims[0] != "gt":
        return None
    if listing.year == 2025:
        return "cx5_gt", "confirmed", "GT (power moonroof is standard)"
    # The 2026 CX-5's only sunroof is the GT's optional panoramic roof, so roof wording in a title means that one.
    strong = ["Premium Package ticked in the listing's feature list"] if "premium package" in listing.features else []
    proof = _roof_proof(listing, ident, (ROOF_IN_TITLE, PREMIUM_IN_TITLE), (PANO_IN_TEXT, PREMIUM_IN_TEXT), strong)
    return ("cx5_gt_pano_2026", *proof) if proof else None


def wants_description(listing):
    """Whether a description could still change this listing's match: it would match with proof of the sunroof but
    its title doesn't prove it. Lets a source fetch only the vehicle pages it needs."""
    hit = classify(listing)
    if hit and hit[1] == "confirmed":
        return False
    return classify(dataclasses.replace(listing, text="panoramic sunroof")) is not None
