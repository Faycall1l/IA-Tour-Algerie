#!/usr/bin/env python3
"""Scrape all SNTF station coordinates from OSM Nominatim and map to wilayas."""

import json
import time
import urllib.request
import urllib.parse
import random
import re
import sys
from pathlib import Path

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
SLEEP = 1.0  # rate limit: 1 req/s
OUTPUT = Path(__file__).resolve().parent.parent / "app" / "data" / "sntf_stations_raw.json"
TMP_OUTPUT = Path("/tmp/sntf_stations_progress.json")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) GeoScraper/1.0",
    "Mozilla/5.0 (X11; Linux x86_64) StationBot/2.0",
    "OpenTrainProject/1.0 (algeria-transit)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSMNomScraper/1.0",
]

# ── Wilaya lookup (id -> English name, used for reverse-geocode matching) ──
WILAYA_BY_ID: dict[int, dict[str, str | float | None]] = {
    1: {"name_en": "Adrar", "name_fr": "Adrar", "lat": 27.87, "lng": -0.29},
    2: {"name_en": "Chlef", "name_fr": "Chlef", "lat": 36.16, "lng": 1.33},
    3: {"name_en": "Laghouat", "name_fr": "Laghouat", "lat": 33.80, "lng": 2.88},
    4: {"name_en": "Oum El Bouaghi", "name_fr": "Oum El Bouaghi", "lat": 35.87, "lng": 7.12},
    5: {"name_en": "Batna", "name_fr": "Batna", "lat": 35.55, "lng": 6.17},
    6: {"name_en": "Bejaia", "name_fr": "Béjaïa", "lat": 36.75, "lng": 5.06},
    7: {"name_en": "Biskra", "name_fr": "Biskra", "lat": 34.85, "lng": 5.73},
    8: {"name_en": "Bechar", "name_fr": "Béchar", "lat": 31.62, "lng": -2.22},
    9: {"name_en": "Blida", "name_fr": "Blida", "lat": 36.47, "lng": 2.83},
    10: {"name_en": "Bouira", "name_fr": "Bouira", "lat": 36.37, "lng": 3.90},
    11: {"name_en": "Tamanrasset", "name_fr": "Tamanrasset", "lat": 22.79, "lng": 5.52},
    12: {"name_en": "Tebessa", "name_fr": "Tébessa", "lat": 35.40, "lng": 8.12},
    13: {"name_en": "Tlemcen", "name_fr": "Tlemcen", "lat": 34.88, "lng": -1.32},
    14: {"name_en": "Tiaret", "name_fr": "Tiaret", "lat": 35.37, "lng": 1.32},
    15: {"name_en": "Tizi Ouzou", "name_fr": "Tizi Ouzou", "lat": 36.72, "lng": 4.05},
    16: {"name_en": "Algiers", "name_fr": "Alger", "lat": 36.75, "lng": 3.04},
    17: {"name_en": "Djelfa", "name_fr": "Djelfa", "lat": 34.67, "lng": 3.25},
    18: {"name_en": "Jijel", "name_fr": "Jijel", "lat": 36.82, "lng": 5.77},
    19: {"name_en": "Setif", "name_fr": "Sétif", "lat": 36.19, "lng": 5.41},
    20: {"name_en": "Saida", "name_fr": "Saïda", "lat": 34.83, "lng": 0.15},
    21: {"name_en": "Skikda", "name_fr": "Skikda", "lat": 36.87, "lng": 6.91},
    22: {"name_en": "Sidi Bel Abbes", "name_fr": "Sidi Bel Abbès", "lat": 35.19, "lng": -0.63},
    23: {"name_en": "Annaba", "name_fr": "Annaba", "lat": 36.90, "lng": 7.77},
    24: {"name_en": "Guelma", "name_fr": "Guelma", "lat": 36.46, "lng": 7.43},
    25: {"name_en": "Constantine", "name_fr": "Constantine", "lat": 36.37, "lng": 6.61},
    26: {"name_en": "Medea", "name_fr": "Médéa", "lat": 36.27, "lng": 2.75},
    27: {"name_en": "Mostaganem", "name_fr": "Mostaganem", "lat": 35.93, "lng": 0.09},
    28: {"name_en": "Msila", "name_fr": "M'Sila", "lat": 35.70, "lng": 4.55},
    29: {"name_en": "Mascara", "name_fr": "Mascara", "lat": 35.40, "lng": 0.14},
    30: {"name_en": "Ouargla", "name_fr": "Ouargla", "lat": 31.96, "lng": 5.33},
    31: {"name_en": "Oran", "name_fr": "Oran", "lat": 35.70, "lng": -0.65},
    32: {"name_en": "El Bayadh", "name_fr": "El Bayadh", "lat": 32.76, "lng": 1.02},
    33: {"name_en": "Illizi", "name_fr": "Illizi", "lat": 26.51, "lng": 8.48},
    34: {"name_en": "Bordj Bou Arreridj", "name_fr": "Bordj Bou Arréridj", "lat": 36.07, "lng": 4.76},
    35: {"name_en": "Boumerdes", "name_fr": "Boumerdès", "lat": 36.76, "lng": 3.48},
    36: {"name_en": "El Tarf", "name_fr": "El Tarf", "lat": 36.77, "lng": 8.31},
    37: {"name_en": "Tindouf", "name_fr": "Tindouf", "lat": 27.67, "lng": -8.13},
    38: {"name_en": "Tissemsilt", "name_fr": "Tissemsilt", "lat": 35.61, "lng": 1.81},
    39: {"name_en": "El Oued", "name_fr": "El Oued", "lat": 33.37, "lng": 6.86},
    40: {"name_en": "Khenchela", "name_fr": "Khenchela", "lat": 35.43, "lng": 7.14},
    41: {"name_en": "Souk Ahras", "name_fr": "Souk Ahras", "lat": 36.29, "lng": 7.95},
    42: {"name_en": "Tipaza", "name_fr": "Tipaza", "lat": 36.59, "lng": 2.45},
    43: {"name_en": "Mila", "name_fr": "Mila", "lat": 36.45, "lng": 6.26},
    44: {"name_en": "Ain Defla", "name_fr": "Aïn Defla", "lat": 36.26, "lng": 1.97},
    45: {"name_en": "Naama", "name_fr": "Naâma", "lat": 33.27, "lng": -0.31},
    46: {"name_en": "Ain Temouchent", "name_fr": "Aïn Témouchent", "lat": 35.30, "lng": -1.14},
    47: {"name_en": "Ghardaia", "name_fr": "Ghardaïa", "lat": 32.49, "lng": 3.67},
    48: {"name_en": "Relizane", "name_fr": "Relizane", "lat": 35.74, "lng": 0.56},
    49: {"name_en": "Timimoun", "name_fr": "Timimoun", "lat": 29.26, "lng": 0.23},
    50: {"name_en": "Beni Abbes", "name_fr": "Béni Abbès", "lat": 30.08, "lng": -2.16},
    51: {"name_en": "Ain Salah", "name_fr": "Aïn Salah", "lat": 27.19, "lng": 2.46},
    52: {"name_en": "Ain Guezzam", "name_fr": "Aïn Guezzam", "lat": 19.57, "lng": 5.77},
    53: {"name_en": "Touggourt", "name_fr": "Touggourt", "lat": 33.11, "lng": 6.06},
    54: {"name_en": "Djanet", "name_fr": "Djanet", "lat": 24.55, "lng": 9.48},
    55: {"name_en": "El M'Ghair", "name_fr": "El M'Ghair", "lat": 33.95, "lng": 5.92},
    56: {"name_en": "El Menia", "name_fr": "El Menia", "lat": 30.58, "lng": 2.88},
    57: {"name_en": "Ouled Djellal", "name_fr": "Ouled Djellal", "lat": 34.43, "lng": 5.07},
    58: {"name_en": "Bordj Badji Mokhtar", "name_fr": "Bordj Badji Mokhtar", "lat": 21.33, "lng": 0.95},
    59: {"name_en": "Aflou", "name_fr": "Aflou", "lat": 34.11, "lng": 2.10},
    60: {"name_en": "El Abiodh Sidi Cheikh", "name_fr": "El Abiodh Sidi Cheikh", "lat": 32.90, "lng": 0.54},
    61: {"name_en": "El Aricha", "name_fr": "El Aricha", "lat": 34.22, "lng": -1.26},
    62: {"name_en": "El Kantara", "name_fr": "El Kantara", "lat": 35.19, "lng": 5.67},
    63: {"name_en": "Barika", "name_fr": "Barika", "lat": 35.40, "lng": 5.37},
    64: {"name_en": "Bou Saada", "name_fr": "Bou Saâda", "lat": 35.22, "lng": 4.18},
    65: {"name_en": "Bir El Ater", "name_fr": "Bir El Ater", "lat": 34.75, "lng": 8.06},
    66: {"name_en": "Ksar El Boukhari", "name_fr": "Ksar El Boukhari", "lat": 35.89, "lng": 2.75},
    67: {"name_en": "Ksar Chellala", "name_fr": "Ksar Chellala", "lat": 35.22, "lng": 2.32},
    68: {"name_en": "Ain Oussera", "name_fr": "Aïn Oussera", "lat": 35.45, "lng": 2.90},
    69: {"name_en": "Messaad", "name_fr": "Messaad", "lat": 34.17, "lng": 3.50},
}

# Build reverse mappings: lowercase variants of names -> wilaya_id
_WILAYA_BY_NAME: dict[str, int] = {}
for wid, w in WILAYA_BY_ID.items():
    for key in (w["name_en"], w["name_fr"]):
        _WILAYA_BY_NAME[key.lower().replace("-", " ").replace("'", " ")] = wid
    # Also add with common variations
    en = str(w["name_en"]).lower()
    _WILAYA_BY_NAME[en] = wid
    # Algiers special
    if wid == 16:
        _WILAYA_BY_NAME["alger"] = 16
        _WILAYA_BY_NAME["alger centre"] = 16
        _WILAYA_BY_NAME["alger centre-ville"] = 16


# ── Station names (extracted from SNTF dropdown raw text + additions) ──────
def _build_station_names() -> list[str]:
    raw = (
        "AIN BOUZIANE AIN DEFLA AIN DOUZ AIN EL BERD AIN FEZZA AIN HADJEL AIN KECHRA "
        "AIN KERMES AIN M LILA AIN NOUISSY AIN OUESSARA AIN ROUIBAH AIN SEFRA AIN SENNOUR "
        "AIN TAHMIMINE AIN TELLOUT AIN TEMOUCHENT AIN TORKI AIN TOUTA AIN YAGOUT AIN_FEKROUN "
        "AKBOU AKID ABBAS ALGER ALGER (AGHA) ALLAGHAN AMMAL ANNABA ARBAL ARIB ARZEW "
        "ATELIERS ATH-MANSOUR AZIB-BEN-ALI-CHERIF AZZABA AZZAGAR BABA ALI BAGHAI BAJA BAKIRA "
        "BARIKA BAZOUL BECHAR BERRHAL BERRAHAL BIBAN EL HADID BIR AISSA AYADA BIR SAF SAF "
        "BIRINE BIRTOUTA BISKRA BLIDA BORDJ BOU ARRERIDJ BORDJ BOUNAAMA BOUCHEGOUF "
        "BOUDAROUA BOUDOUAOU BOUFARIK BOUGHEZOUL BOUGURRA BOUHENNI BOUIRA BOUKADIR "
        "BOUKANEFIS BOUKHADRA BOUKHALFA BOUKHAMOUZA BOUMAHRA BOUMERDES BOUTI SAYEH "
        "BOUTLELIS BOUZEGZA CHEBLI CHIFFA CHLEF CONSTANTINE CORSO DAR EL BEIDA "
        "DIDOUCH MOURAD DJAMA DJAMAA DJELFA DJENIEN BOUREIZG DJENIENE MESKINE DJERMA "
        "DRA EL MIZAN DRAA BENKHEDDA DREA DREAN EL ADJIBA EL AFFROUN EL AMRA EL AMRIA "
        "EL AOUINET EL ARROUCHE EL ATTAF EL CHALI EL ESNAM EL GOURZI EL HADJAR EL HAMRI "
        "EL HARRACH EL HARROUCH EL KANTARA EL KHARMA EL KHROUB EL KSEUR EL KSEUR-O-AMIZOUR "
        "EL MALEH EL MEGHAIER EL MILIA EL OUTAYA EL-ANCER EL-ANNASSER EL-EULMA "
        "EL-KANTARA-GORGES EMDJEZ EDCHICHE ES SENIA F'KIRINA FAC HADJ LAKHDER FESDIS "
        "FORNAKA FRENDA GARA DJEBILET GARITA GDYEL GHARDIMAOU GHAZAOUET GUE DE CONSTANTINE "
        "HAI EL KASAB HAI EL SABAH HAMMA MARCH HAMMA BOUZIANE HAMMAGUIR HAMOUDI KROUMA "
        "HANIF HASSI AMEUR HASSI BAHBAH HASSI BEN OKBA HASSI BOUNIF HASSI EL GHELLA "
        "HASSI FEDOUL HASSI KHABI HASSI MAFSOUKH HASSI MAMECHE HOCEINIA HUSSEIN DEY "
        "IGHZER AMOUKRAN IMAMA ISSERS JENDOUBA JIJEL KADIRIA KEF NAAJA KEF SALAH KHEDARA "
        "KHEMIS MILLIANA KHENCHELA LA MACTA LAGHOUAT LAKHDARIA LOTTA M'DAOUROUCH M'DJEZ "
        "M'SILA M'TOUSSA M'ZITA EL-MCHIR MADROUMA MAGHNIA MANBAA EL GHAZEL MANSOURAH "
        "MAZAGRAN MECHERIA MECHROHA MEDJEZ SFA MELIANA MERS EL HADJADJ (GRANDE PLAGE) "
        "MERS EL HADJADJ (TERMINUS) MESKIANA MESLOUG MISSERGHINE MOGHRAR MOHAMMADIA "
        "MOHGOUN MORSOTT MOSTAGANEM MOULEY SLISSEN MOUZAIA NAAMA NACIRIA OAIC KHROUB "
        "OGGAZ ORAN OUED AISSI OUED AISSI UNIVERSITE OUED ALI OUED CHOUK OUED DAMOUS "
        "OUED DJEMAA OUED DJER OUED FARAH OUED FODDA OUED GHIR OUED HAMIMINE OUED KEBRIT "
        "OUED MOUGRAS OUED RHIOU OUED SLY OUED SMAR OUED TINN OUED TLELAT OUED ZIED "
        "OUED ZITOUN OULED AMMAR OULED BENZIANE OULED CHOULY OULED MIMOUN OULED RACHED "
        "OULED YOUB OUMASTEUR R DEMOUCHE RAMDANE DJAMEL RAS EL MA RAS EL OUED REGHAIA "
        "REGHAIA INDUSTRIEL REGOUCHE RELIZANE ROUIBA ROUIBA INDUSTRIEL ROUINA SABRA SAFSAF "
        "SAHKI AHMED SAHOURIA SAIDA SALAH BOUCHAOUR SETIF SETTARA SI MUSTAPHA SIDI ABD ALLAH "
        "SIDI ABD ALLAH UNIVERSITE SIDI ABEDMOUMEN SIDI ABID SIDI ACHOUR SIDI ALI BONGUEN"
    )

    # Multi-word station prefixes for greedy parsing
    # Ordered longest-first for greedy match
    prefixes = sorted([
        "AIN EL BERD", "AIN M LILA", "AIN TEMOUCHENT", "AIN OUESSARA", "AIN BOUZIANE",
        "AIN FEZZA", "AIN HADJEL", "AIN KECHRA", "AIN KERMES", "AIN NOUISSY",
        "AIN ROUIBAH", "AIN SEFRA", "AIN SENNOUR", "AIN TAHMIMINE", "AIN TELLOUT",
        "AIN TORKI", "AIN TOUTA", "AIN YAGOUT", "AIN DEFLA", "AIN DOUZ", "AIN_FEKROUN",
        "AKID ABBAS", "ALGER (AGHA)", "AZIB-BEN-ALI-CHERIF", "BABA ALI",
        "BIBAN EL HADID", "BIR AISSA AYADA", "BIR SAF SAF", "BORDJ BOU ARRERIDJ",
        "BORDJ BOUNAAMA", "BOUTI SAYEH", "DAR EL BEIDA", "DIDOUCH MOURAD",
        "DJENIEN BOUREIZG", "DJENIENE MESKINE", "DRA EL MIZAN", "DRAA BENKHEDDA",
        "EL ADJIBA", "EL AFFROUN", "EL AMRA", "EL AMRIA", "EL AOUINET",
        "EL ARROUCHE", "EL ATTAF", "EL CHALI", "EL ESNAM", "EL GOURZI",
        "EL HADJAR", "EL HAMRI", "EL HARRACH", "EL HARROUCH", "EL KANTARA",
        "EL KHARMA", "EL KHROUB", "EL KSEUR", "EL KSEUR-O-AMIZOUR", "EL MALEH",
        "EL MEGHAIER", "EL MILIA", "EL OUTAYA", "EL-ANCER", "EL-ANNASSER",
        "EL-EULMA", "EL-KANTARA-GORGES", "EMDJEZ EDCHICHE", "ES SENIA",
        "FAC HADJ LAKHDER", "GARA DJEBILET", "GUE DE CONSTANTINE",
        "HAI EL KASAB", "HAI EL SABAH", "HAMMA MARCH", "HAMMA BOUZIANE",
        "HAMOUDI KROUMA", "HASSI AMEUR", "HASSI BAHBAH", "HASSI BEN OKBA",
        "HASSI BOUNIF", "HASSI EL GHELLA", "HASSI FEDOUL", "HASSI KHABI",
        "HASSI MAFSOUKH", "HASSI MAMECHE", "HUSSEIN DEY",
        "IGHZER AMOUKRAN", "KEF NAAJA", "KEF SALAH", "KHEMIS MILLIANA",
        "LA MACTA", "MANBAA EL GHAZEL", "MEDJEZ SFA",
        "MERS EL HADJADJ (GRANDE PLAGE)", "MERS EL HADJADJ (TERMINUS)",
        "MOULEY SLISSEN", "M'ZITA EL-MCHIR",
        "OAIC KHROUB", "OUED AISSI UNIVERSITE", "OUED AISSI",
        "OUED ALI", "OUED CHOUK", "OUED DAMOUS", "OUED DJEMAA", "OUED DJER",
        "OUED FARAH", "OUED FODDA", "OUED GHIR", "OUED HAMIMINE", "OUED KEBRIT",
        "OUED MOUGRAS", "OUED RHIOU", "OUED SLY", "OUED SMAR", "OUED TINN",
        "OUED TLELAT", "OUED ZIED", "OUED ZITOUN", "OULED AMMAR",
        "OULED BENZIANE", "OULED CHOULY", "OULED MIMOUN", "OULED RACHED",
        "OULED YOUB", "R DEMOUCHE", "RAMDANE DJAMEL", "RAS EL MA",
        "RAS EL OUED", "REGHAIA INDUSTRIEL", "ROUIBA INDUSTRIEL",
        "SAHKI AHMED", "SALAH BOUCHAOUR", "SI MUSTAPHA",
        "SIDI ABD ALLAH UNIVERSITE", "SIDI ABD ALLAH", "SIDI ABEDMOUMEN",
        "SIDI ABID", "SIDI ACHOUR", "SIDI ALI BONGUEN",
        "ATH-MANSOUR", "BOUGHEZOUL", "BOUKHAMOUZA", "M'DAOUROUCH",
        "M'DJEZ", "M'SILA", "M'TOUSSA", "BOUDAROUA", "BOUDOUAOU",
        "BOUKANEFIS", "BOUKHADRA", "BOUKHALFA", "BOUTLELIS",
        "CHIFFA", "GDYEL", "HOCEINIA", "KADIRIA", "KHEDARA",
        "MESKIANA", "MESLOUG", "MISSERGHINE", "MOGHRAR",
        "MOHAMMADIA", "MOHGOUN", "MORSOTT", "NACIRIA",
        "OUMASTEUR", "SAFSAF", "SAHOURIA", "SETTARA",
        "ALLAGHAN", "AMMAL", "ARBAL", "ARIB", "AZZAGAR",
        "BAGHAI", "BAJA", "BAKIRA", "BAZOUL", "BERRHAL",
        "BERRAHAL", "BIRINE", "BIRTOUTA", "BOUCHEGOUF",
        "BOUGURRA", "BOUHENNI", "BOUKADIR", "BOUMAHRA",
        "BOUZEGZA", "CHEBLI", "CORSO", "DJAMA", "DJAMAA",
        "DJERMA", "DREA", "DREAN", "F'KIRINA", "FAC",
        "FESDIS", "FORNAKA", "FRENDA", "GARITA",
        "GHARDIMAOU", "GHAZAOUET", "HAMMAGUIR", "HANIF",
        "IMAMA", "ISSERS", "JENDOUBA", "LOTTA", "MADROUMA",
        "MAGHNIA", "MANSOURAH", "MAZAGRAN", "MECHERIA",
        "MECHROHA", "MELIANA", "MOUZAIA", "OGGAZ",
        "REGOUCHE", "ROUINA", "SABRA",
        "AIN", "AKBOU", "ALGER", "ANNABA", "ARZEW",
        "ATELIERS", "AZZABA", "BARIKA", "BECHAR",
        "BISKRA", "BLIDA", "BOUMERDES", "CHLEF",
        "CONSTANTINE", "DJELFA", "JIJEL", "KHENCHELA",
        "LAGHOUAT", "LAKHDARIA", "MOSTAGANEM", "NAAMA",
        "ORAN", "REGHAIA", "RELIZANE", "ROUIBA",
        "SAIDA", "SETIF", "SIDI",
    ], key=len, reverse=True)

    # Greedy parse: match longest prefix first
    names: list[str] = []
    i = 0
    tokens = raw.split()
    while i < len(tokens):
        matched = False
        for p in prefixes:
            pts = p.split()
            if i + len(pts) <= len(tokens) and tokens[i:i + len(pts)] == pts:
                names.append(p)
                i += len(pts)
                matched = True
                break
        if not matched:
            names.append(tokens[i])
            i += 1

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for n in names:
        key = n.strip().upper()
        if key not in seen:
            seen.add(key)
            deduped.append(n.strip())
    return deduped


def _add_stations(base: list[str]) -> list[str]:
    """Append stations possibly missing from the dropdown."""
    extras = [
        "TLEMCEN",
        "TABIA",
        "BEJAIA",
        "AIN BEIDA",
        "TEBESSA",
        "KOUIF",
        # Alger-Béjaïa line additions
        "BOUMERDES",
        "EL AKHDARIYA",
        "AGHNIF",
        "BENI MANSOUR",
        "TAZMA LT",
        "LAAGANE",
        "TIFRETS",
        "SIDI AICH",
    ]
    seen = {s.upper() for s in base}
    for e in extras:
        if e.upper() not in seen:
            base.append(e)
    return base


# ── Helpers ─────────────────────────────────────────────────────────────────

def _ua() -> str:
    return random.choice(USER_AGENTS)


def _req(url: str) -> dict | list | None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _ua(), "Accept-Language": "fr,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _wilaya_from_reverse(lat: float, lng: float) -> tuple[int, str] | None:
    """Reverse-geocode a coordinate to find the wilaya."""
    params = urllib.parse.urlencode({
        "lat": lat,
        "lon": lng,
        "format": "json",
        "addressdetails": 1,
        "accept-language": "fr",
    })
    url = f"{NOMINATIM_REVERSE}?{params}"
    data = _req(url)
    if not data or not isinstance(data, dict):
        return None
    addr = data.get("address") or {}
    state = (addr.get("state") or addr.get("region") or "").lower().strip()
    county = (addr.get("county") or "").lower().strip()
    city = (addr.get("city") or addr.get("town") or addr.get("village") or "").lower().strip()

    # Direct match on state
    if state in _WILAYA_BY_NAME:
        wid = _WILAYA_BY_NAME[state]
        return wid, str(WILAYA_BY_ID[wid]["name_en"])

    # Try county
    if county in _WILAYA_BY_NAME:
        wid = _WILAYA_BY_NAME[county]
        return wid, str(WILAYA_BY_ID[wid]["name_en"])

    # Try fuzzy: state might be like "Wilaya d'Alger" or "Alger Province"
    m = re.search(r"(\w[\w\s'-]+)", state)
    if m:
        cand = m.group(1).strip()
        if cand in _WILAYA_BY_NAME:
            wid = _WILAYA_BY_NAME[cand]
            return wid, str(WILAYA_BY_ID[wid]["name_en"])

    # Fallback: if city matches a wilaya capital name
    for wid, w in WILAYA_BY_ID.items():
        if city == str(w["name_en"]).lower():
            return wid, str(w["name_en"])

    return None


def _wilaya_from_station_name(name: str) -> tuple[int, str] | None:
    """Heuristic: if station name contains a wilaya name, assign it."""
    up = name.upper()
    # Common mappings
    known: dict[str, int] = {
        "AIN DEFLA": 44, "AIN TEMOUCHENT": 46, "AIN TOUTA": 5,
        "AIN M LILA": 4, "AIN BEIDA": 4, "AIN BOUZIANE": 44,
        "AIN OUESSARA": 68, "AIN KERMES": 12, "AIN FEZZA": 12,
        "AIN TAHMIMINE": 43, "AIN KECHRA": 43, "AIN SENNOUR": 26,
        "AIN EL BERD": 22, "AIN NOUISSY": 31, "AIN ROUIBAH": 46,
        "AIN TORKI": 31, "AIN DOUZ": 12, "AIN SEFRA": 45,
        "AIN YAGOUT": 5, "AIN HADJEL": 28, "AIN_FEKROUN": 4,
        "AIN TELLOUT": 29, "AIN M'LILA": 4,
        "EL HARRACH": 16, "EL HARROUCH": 43, "EL KANTARA": 7,
        "EL KHROUB": 25, "EL KSEUR": 6, "EL MILIA": 18,
        "EL AFFROUN": 9, "EL ATTAF": 44, "EL AMRA": 27,
        "EL AMRIA": 46, "EL KHARMA": 31, "EL HADJAR": 23,
        "EL HAMRI": 46, "EL AOUINET": 30, "EL MEGHAIER": 55,
        "EL MALEH": 46, "EL OUTAYA": 53, "EL ESNAM": 9,
        "EL ADJIBA": 48, "EL GOURZI": 48, "EL ARROUCHE": 43,
        "EL-ANNASSER": 9, "EL-EULMA": 19, "EL CHALI": 22,
        "EL-ANCER": 18, "EL-KANTARA-GORGES": 7, "EL AKHDARIYA": 10,
        "ALGER": 16, "HUSSEIN DEY": 16, "DAR EL BEIDA": 16,
        "BABA ALI": 16, "SIDI ABD ALLAH": 16, "REGHAIA": 16,
        "ROUIBA": 35, "BOUDOUAOU": 35, "CORSO": 35, "BOUMERDES": 35,
        "BORDJ BOUNAAMA": 35, "BOUDAROUA": 35, "BOUGHEZOUL": 16,
        "HASSI BOUNIF": 31, "HASSI AMEUR": 31, "HASSI BAHBAH": 31,
        "HASSI MAMECHE": 31, "HASSI FEDOUL": 22, "HASSI KHABI": 22,
        "HASSI MAFSOUKH": 31, "HASSI EL GHELLA": 31, "HASSI BEN OKBA": 31,
        "MOHAMMADIA": 31, "MISSERGHINE": 31, "ES SENIA": 31,
        "ARZEW": 31, "OUED TLELAT": 31, "BIR EL DJIR": 31,
        "BIR SAF SAF": 21, "BIR AISSA AYADA": 44, "BIRINE": 26,
        "BIRTOUTA": 48, "BOUFARIK": 9, "MOUZAIA": 9, "CHEBLI": 9,
        "BOUGURRA": 26, "CHIFFA": 9, "BOUKHALFA": 12, "BOUKHAMOUZA": 7,
        "BOUKANEFIS": 27, "BOUKADIR": 13, "BOUHENNI": 43,
        "BOUCHEGOUF": 37, "BOUMAHRA": 28, "BOUTLELIS": 29,
        "BOUTI SAYEH": 7, "BOUZEGZA": 48, "BOUKHADRA": 12,
        "KHEMIS MILLIANA": 44, "MELIANA": 44, "MECHERIA": 45,
        "MECHROHA": 7, "MOGHRAR": 48, "MOHGOUN": 48, "MORSOTT": 48,
        "MOSTAGANEM": 27, "MASCARA": 29, "MAZAGRAN": 27,
        "MOHAMMEDIA": 31, "M'DAOUROUCH": 36, "M'DJEZ": 4,
        "M'SILA": 28, "M'TOUSSA": 28, "M'ZITA EL-MCHIR": 13,
        "MAGHNIA": 13, "MANSOURAH": 13, "MANBAA EL GHAZEL": 29,
        "MADROUMA": 24, "MESKIANA": 41, "MESLOUG": 5, "MEDJEZ SFA": 24,
        "MOULEY SLISSEN": 22, "OAIC KHROUB": 9, "OGGAZ": 29,
        "ORAN": 31, "OUED TINN": 36, "OUED ZITOUN": 43,
        "OUED ZIED": 29, "OUED GHIR": 6, "OUED KEBRIT": 41,
        "OUED HAMIMINE": 41, "OUED MOUGRAS": 24, "OUED CHOUK": 13,
        "OUED ALI": 10, "OUED DJEMAA": 44, "OUED DJER": 9,
        "OUED DAMOUS": 42, "OUED FARAH": 44, "OUED FODDA": 2,
        "OUED RHIOU": 48, "OUED SLY": 2, "OUED SMAR": 16,
        "OUED AISSI": 15, "NAAMA": 45, "NACIRIA": 46,
        "OULED AMMAR": 35, "OULED BENZIANE": 10, "OULED CHOULY": 9,
        "OULED MIMOUN": 13, "OULED RACHED": 10, "OULED YOUB": 19,
        "OUMASTEUR": 31, "KADIRIA": 10, "KEF NAAJA": 34,
        "KEF SALAH": 28, "KHEDARA": 48, "LA MACTA": 48,
        "LAGHOUAT": 3, "LAKHDARIA": 10, "LOTTA": 10, "ISSERS": 35,
        "R DEMOUCHE": 10, "RAS EL MA": 19, "RAS EL OUED": 34,
        "RAMDANE DJAMEL": 21, "RELOUCH": 8, "REGOUCHE": 19,
        "ROUINA": 2, "SABRA": 13, "SAFSAF": 21, "SAHKI AHMED": 19,
        "SAHOURIA": 17, "SAIDA": 20, "SALAH BOUCHAOUR": 26,
        "SETIF": 19, "SETTARA": 10, "SI MUSTAPHA": 9,
        "SIDI ALI BONGUEN": 13, "TLEMCEN": 13, "TABIA": 13,
        "BEJAIA": 6, "TEBESSA": 12, "KOUIF": 12, "AFLON": 59,
        "HADJ LAKHDER": 8, "BECHAR": 8, "IMAMA": 8,
        "HASSI FEDOUL": 22, "HANIF": 22, "SIDI BEL ABBES": 22,
        "SIDI ABEDMOUMEN": 22, "SIDI ABID": 22, "SIDI ACHOUR": 26,
        "SIDI ALI": 48, "DIDOUCH MOURAD": 25, "HAMMA MARCH": 16,
        "HAMMA BOUZIANE": 25, "HAMMAGUIR": 25, "HAMOUDI KROUMA": 25,
        "GUE DE CONSTANTINE": 25, "DJAMA": 16, "DJAMAA": 17,
        "ABID": 22, "AFFROUN": 9, "BBA": 34,
        "AKBOU": 6, "AKID ABBAS": 16, "ALLAGHAN": 10,
        "AMMAL": 35, "ARBAL": 15, "ARIB": 44, "ATELIERS": 16,
        "ATH-MANSOUR": 15, "AZIB-BEN-ALI-CHERIF": 15, "AZZABA": 21,
        "AZZAGAR": 31, "BAGHAI": 5, "BAJA": 9, "BAKIRA": 31,
        "BARIKA": 63, "BAZOUL": 2, "BERRHAL": 5, "BERRAHAL": 25,
        "BIBAN EL HADID": 43, "BORDJ BOU ARRERIDJ": 34, "BORDJ BOUNAAMA": 35,
        "BOUGURRA": 26, "DJENIEN BOUREIZG": 44, "DJENIENE MESKINE": 26,
        "DRA EL MIZAN": 15, "DRAA BENKHEDDA": 10, "DREA": 10, "DREAN": 21,
        "EMDJEZ EDCHICHE": 24, "FORNAKA": 24, "FRENDA": 14,
        "GARA DJEBILET": 45, "GARITA": 36, "GDYEL": 8,
        "GHARDIMAOU": 13, "GHAZAOUET": 13, "IGHZER AMOUKRAN": 6,
        "JENDOUBA": 36, "KHEMIS": 22, "KHENCHELA": 40,
        "MAGHNIA": 13, "MANSOURAH": 13, "REGHED": 42,
        "RELIEN": 48, "SARNA": 7, "ZAATRA": 19,
        "HOCEINIA": 18, "JIJEL": 18, "MARBÂA": 5,
        "BENI MANSOUR": 10, "TAZMA LT": 6, "LAAGANE": 6,
        "TIFRETS": 6, "SIDI AICH": 6,
    }
    for k, v in known.items():
        if k in up:
            return v, str(WILAYA_BY_ID.get(v, {}).get("name_en", ""))

    return None


def geocode_station(name: str) -> dict | None:
    """Geocode one station via Nominatim search."""
    query = f"{name} gare Algérie"
    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "limit": 1,
    })
    url = f"{NOMINATIM_SEARCH}?{params}"
    data = _req(url)
    if not data or not isinstance(data, list) or len(data) == 0:
        # retry without "gare"
        params2 = urllib.parse.urlencode({
            "q": f"{name} Algeria",
            "format": "json",
            "limit": 1,
        })
        url2 = f"{NOMINATIM_SEARCH}?{params2}"
        data = _req(url2)
        if not data or not isinstance(data, list) or len(data) == 0:
            return None
    result = data[0]
    lat = float(result.get("lat", 0))
    lng = float(result.get("lon", 0))
    return {"lat": lat, "lng": lng}


def clean_name(name: str) -> str:
    """Return a clean display name."""
    n = name.strip().title()
    return n


# ── Main ────────────────────────────────────────────────────────────────────

def _load_progress() -> tuple[list[dict], set[str]]:
    """Load previously saved progress. Returns (results, done_names)."""
    if TMP_OUTPUT.exists():
        data = json.loads(TMP_OUTPUT.read_text(encoding="utf-8"))
        done = {r["name"] for r in data}
        return data, done
    return [], set()


def _save_progress(results: list[dict]) -> None:
    """Save intermediate progress to temp file."""
    TMP_OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    stations = _build_station_names()
    stations = _add_stations(stations)
    total = len(stations)

    results, done_names = _load_progress()
    failed_geo: list[str] = []
    no_wilaya_list: list[str] = []
    wilaya_counts: dict[int, int] = {}

    # Rebuild counts from loaded results
    for r in results:
        w = r.get("wilaya_id")
        if w:
            c = wilaya_counts.get(w, 0) + 1
            wilaya_counts[w] = c
        if r.get("lat") is None:
            failed_geo.append(r["name"])
        if r.get("lat") is not None and r.get("wilaya_id") is None:
            no_wilaya_list.append(r["name"])

    print(f"Total stations: {total} | Already done: {len(done_names)} | Remaining: {total - len(done_names)}")

    for idx, name in enumerate(stations, 1):
        if name in done_names:
            print(f"[{idx}/{total}] {name} ... ✓ (cached)")
            continue

        print(f"[{idx}/{total}] {name} ... ", end="", flush=True)

        # Use station-name heuristic first (avoids expensive reverse-geocode call)
        w = _wilaya_from_station_name(name)

        coords = geocode_station(name)

        if coords is None:
            print("FAILED (geocode)")
            failed_geo.append(name)
            lat = lng = None
        else:
            lat, lng = coords["lat"], coords["lng"]
            # Try reverse geocode if no heuristic match
            if w is None:
                rev = _wilaya_from_reverse(lat, lng)
                if rev:
                    w = rev

        if w:
            wid, wname = w
        else:
            wid, wname = None, None
            if coords is not None:
                no_wilaya_list.append(name)

        entry = {
            "name": name,
            "name_clean": clean_name(name),
            "lat": lat,
            "lng": lng,
            "wilaya_id": wid,
            "wilaya_name": wname,
        }
        results.append(entry)
        done_names.add(name)

        if wid:
            wilaya_counts[wid] = wilaya_counts.get(wid, 0) + 1

        if coords:
            print(f"✓ {lat:.4f}, {lng:.4f} | wilaya={wname or '?'}")
        else:
            print(f"  (no coords) | wilaya={wname or '?'}")

        # Save progress periodically
        if idx % 10 == 0:
            _save_progress(results)

        time.sleep(SLEEP)

    # Final save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_progress(results)

    total_geocoded = sum(1 for r in results if r["lat"] is not None)
    print(f"\n{'='*60}")
    print(f"Saved {len(results)} stations to {OUTPUT}")
    print(f"Total stations geocoded: {total_geocoded}/{len(results)}")
    print(f"Failed geocodes: {len(failed_geo)}")
    if failed_geo:
        for f in failed_geo:
            print(f"  - {f}")

    print(f"\nStations per wilaya:")
    for wid in sorted(wilaya_counts, key=lambda x: wilaya_counts[x], reverse=True):
        wname = WILAYA_BY_ID.get(wid, {}).get("name_en", "?")
        print(f"  Wilaya {wid:2d} ({wname}): {wilaya_counts[wid]}")

    if no_wilaya_list:
        print(f"\nGeocoded stations without wilaya: {len(no_wilaya_list)}")
        for rn in no_wilaya_list:
            print(f"  - {rn}")

    # Show full JSON
    print(f"\n{'='*60}")
    print("FULL JSON:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
