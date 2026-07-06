#!/usr/bin/env python3
"""Build complete SNTF seed data: validate wilaya mappings + build lines + price estimates.

Produces sntf_seed_complete.json with all stations and transport lines.
Self-contained — no imports from the athar project.
"""

import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
import random
import time
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
RAW_PATH = DATA_DIR / "sntf_stations_raw.json"
OUTPUT_PATH = DATA_DIR / "sntf_seed_complete.json"

NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) StationValidator/1.0",
    "OpenTrainProject/2.0 (algeria-transit)",
    "Mozilla/5.0 (X11; Linux x86_64) AlgiersGeo/1.0",
]

WILAYA_CAPITALS: dict[int, dict[str, float]] = {
    1: {"lat": 27.87, "lng": -0.29}, 2: {"lat": 36.16, "lng": 1.33},
    3: {"lat": 33.80, "lng": 2.88}, 4: {"lat": 35.87, "lng": 7.12},
    5: {"lat": 35.55, "lng": 6.17}, 6: {"lat": 36.75, "lng": 5.06},
    7: {"lat": 34.85, "lng": 5.73}, 8: {"lat": 31.62, "lng": -2.22},
    9: {"lat": 36.47, "lng": 2.83}, 10: {"lat": 36.37, "lng": 3.90},
    11: {"lat": 22.79, "lng": 5.52}, 12: {"lat": 35.40, "lng": 8.12},
    13: {"lat": 34.88, "lng": -1.32}, 14: {"lat": 35.37, "lng": 1.32},
    15: {"lat": 36.72, "lng": 4.05}, 16: {"lat": 36.75, "lng": 3.04},
    17: {"lat": 34.67, "lng": 3.25}, 18: {"lat": 36.82, "lng": 5.77},
    19: {"lat": 36.19, "lng": 5.41}, 20: {"lat": 34.83, "lng": 0.15},
    21: {"lat": 36.87, "lng": 6.91}, 22: {"lat": 35.19, "lng": -0.63},
    23: {"lat": 36.90, "lng": 7.77}, 24: {"lat": 36.46, "lng": 7.43},
    25: {"lat": 36.37, "lng": 6.61}, 26: {"lat": 36.27, "lng": 2.75},
    27: {"lat": 35.93, "lng": 0.09}, 28: {"lat": 35.70, "lng": 4.55},
    29: {"lat": 35.40, "lng": 0.14}, 30: {"lat": 31.96, "lng": 5.33},
    31: {"lat": 35.70, "lng": -0.65}, 32: {"lat": 32.76, "lng": 1.02},
    33: {"lat": 26.51, "lng": 8.48}, 34: {"lat": 36.07, "lng": 4.76},
    35: {"lat": 36.76, "lng": 3.48}, 36: {"lat": 36.77, "lng": 8.31},
    37: {"lat": 27.67, "lng": -8.13}, 38: {"lat": 35.61, "lng": 1.81},
    39: {"lat": 33.37, "lng": 6.86}, 40: {"lat": 35.43, "lng": 7.14},
    41: {"lat": 36.29, "lng": 7.95}, 42: {"lat": 36.59, "lng": 2.45},
    43: {"lat": 36.45, "lng": 6.26}, 44: {"lat": 36.26, "lng": 1.97},
    45: {"lat": 33.27, "lng": -0.31}, 46: {"lat": 35.30, "lng": -1.14},
    47: {"lat": 32.49, "lng": 3.67}, 48: {"lat": 35.74, "lng": 0.56},
    49: {"lat": 29.26, "lng": 0.23}, 50: {"lat": 30.08, "lng": -2.16},
    51: {"lat": 27.19, "lng": 2.46}, 52: {"lat": 19.57, "lng": 5.77},
    53: {"lat": 33.11, "lng": 6.06}, 54: {"lat": 24.55, "lng": 9.48},
    55: {"lat": 33.95, "lng": 5.92}, 56: {"lat": 30.58, "lng": 2.88},
    57: {"lat": 34.43, "lng": 5.07}, 58: {"lat": 21.33, "lng": 0.95},
    59: {"lat": 34.11, "lng": 2.10}, 60: {"lat": 32.90, "lng": 0.54},
    61: {"lat": 34.22, "lng": -1.26}, 62: {"lat": 35.19, "lng": 5.67},
    63: {"lat": 35.40, "lng": 5.37}, 64: {"lat": 35.22, "lng": 4.18},
    65: {"lat": 34.75, "lng": 8.06}, 66: {"lat": 35.89, "lng": 2.75},
    67: {"lat": 35.22, "lng": 2.32}, 68: {"lat": 35.45, "lng": 2.90},
    69: {"lat": 34.17, "lng": 3.50},
}

WILAYA_NAMES: dict[int, str] = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi",
    5: "Batna", 6: "Bejaia", 7: "Biskra", 8: "Bechar",
    9: "Blida", 10: "Bouira", 11: "Tamanrasset", 12: "Tebessa",
    13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou", 16: "Algiers",
    17: "Djelfa", 18: "Jijel", 19: "Setif", 20: "Saida",
    21: "Skikda", 22: "Sidi Bel Abbes", 23: "Annaba", 24: "Guelma",
    25: "Constantine", 26: "Medea", 27: "Mostaganem", 28: "Msila",
    29: "Mascara", 30: "Ouargla", 31: "Oran", 32: "El Bayadh",
    33: "Illizi", 34: "Bordj Bou Arreridj", 35: "Boumerdes", 36: "El Tarf",
    37: "Tindouf", 38: "Tissemsilt", 39: "El Oued", 40: "Khenchela",
    41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Ain Defla",
    45: "Naama", 46: "Ain Temouchent", 47: "Ghardaia", 48: "Relizane",
    49: "Timimoun", 50: "Beni Abbes", 51: "Ain Salah", 52: "Ain Guezzam",
    53: "Touggourt", 54: "Djanet", 55: "El M'Ghair", 56: "El Menia",
    57: "Ouled Djellal", 58: "Bordj Badji Mokhtar", 59: "Aflou",
    60: "El Abiodh Sidi Cheikh", 61: "El Aricha", 62: "El Kantara",
    63: "Barika", 64: "Bou Saada", 65: "Bir El Ater",
    66: "Ksar El Boukhari", 67: "Ksar Chellala", 68: "Ain Oussera", 69: "Messaad",
}

_WILAYA_BY_NAME: dict[str, int] = {}
for wid, name in WILAYA_NAMES.items():
    _WILAYA_BY_NAME[name.lower()] = wid
_WILAYA_BY_NAME["alger"] = 16
_WILAYA_BY_NAME["alger centre"] = 16
_WILAYA_BY_NAME["ain oussera"] = 68


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def normalize(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"\s+", " ", s.strip().upper().replace("-", " ").replace("'", " ").replace("(", "").replace(")", "").replace(",", "").replace(".", ""))


def _ua() -> str:
    return random.choice(USER_AGENTS)


def reverse_geocode(lat: float, lng: float) -> int | None:
    time.sleep(0.5)
    params = urllib.parse.urlencode({
        "lat": lat, "lon": lng, "format": "json",
        "addressdetails": 1, "accept-language": "fr",
    })
    req = urllib.request.Request(
        f"{NOMINATIM_REVERSE}?{params}",
        headers={"User-Agent": _ua(), "Accept-Language": "fr,en;q=0.9"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    addr = data.get("address") or {}
    state = (addr.get("state") or addr.get("region") or "").lower().strip()
    county = (addr.get("county") or "").lower().strip()
    for key in (state, county):
        if key in _WILAYA_BY_NAME:
            return _WILAYA_BY_NAME[key]
    m = re.search(r"(\w[\w\s'-]+)", state)
    if m and m.group(1).strip() in _WILAYA_BY_NAME:
        return _WILAYA_BY_NAME[m.group(1).strip()]
    for wid, w in WILAYA_NAMES.items():
        if w.lower() in (addr.get("city") or "").lower():
            return wid
    return None


def nearest_wilaya_by_distance(lat: float, lng: float) -> tuple[int, float]:
    best_wid = None
    best_dist = float("inf")
    for wid, cap in WILAYA_CAPITALS.items():
        d = haversine_km(lat, lng, cap["lat"], cap["lng"])
        if d < best_dist:
            best_dist = d
            best_wid = wid
    return best_wid, best_dist


def validate_wilaya(station: dict) -> tuple[int | None, str | None, bool]:
    lat = station.get("lat")
    lng = station.get("lng")
    orig_wid = station.get("wilaya_id")
    if lat is None or lng is None:
        return orig_wid, WILAYA_NAMES.get(orig_wid) if orig_wid else None, False
    nearest, dist = nearest_wilaya_by_distance(lat, lng)
    changed = False
    if dist <= 50.0:
        if nearest != orig_wid:
            changed = True
        return nearest, WILAYA_NAMES.get(nearest), changed
    rev_wid = reverse_geocode(lat, lng)
    if rev_wid is not None:
        if rev_wid != orig_wid:
            changed = True
        return rev_wid, WILAYA_NAMES.get(rev_wid), changed
    if nearest != orig_wid:
        changed = True
    return nearest, WILAYA_NAMES.get(nearest), changed


def match_station(name_query: str, stations: list[dict]) -> dict | None:
    nq = normalize(name_query)
    for s in stations:
        sn = normalize(s["name"])
        sc = normalize(s.get("name_clean", ""))
        if nq == sn or nq == sc:
            return s
    for s in stations:
        sn = normalize(s["name"])
        sc = normalize(s.get("name_clean", ""))
        if nq in sn or nq in sc or sn in nq or sc in nq:
            return s
    for s in stations:
        sn = normalize(s["name"])
        sc = normalize(s.get("name_clean", ""))
        words_nq = set(nq.split())
        words_sn = set(sn.split())
        words_sc = set(sc.split())
        if len(words_nq & words_sn) >= min(len(words_nq), len(words_sn)) * 0.7:
            return s
        if len(words_nq & words_sc) >= min(len(words_nq), len(words_sc)) * 0.7:
            return s
    return None


# ── Synthetic stations for well-known SNTF stops missing from scraped data ──
# (name -> (wilaya_id, approx_lat, approx_lng))
SYNTHETIC_STATIONS: dict[str, tuple[int, float, float]] = {
    "Thénia":                (35, 36.7283, 3.5550),
    "Bordj Menaiel":         (35, 36.7333, 3.7250),
    "Tizi Ouzou":            (15, 36.7150, 4.0469),
    "Draâ El Mizan":         (15, 36.5381, 3.8367),
    "El Akhdariya":          (10, 36.4000, 3.8500),
    "Aghnif":                (10, 36.3500, 4.1500),
    "Tazmalt":               (6,  36.3833, 4.4000),
    "Béjaïa":                (6,  36.7506, 5.0778),
    "Sétif":                 (19, 36.1908, 5.4080),
    "Sidi Bel Abbès":        (22, 35.1944, -0.6372),
    "Oued Sefioun":          (22, 35.1000, -0.7500),
    "Batna":                 (5,  35.5544, 6.1742),
    "Mascara":               (29, 35.3989, 0.1433),
    "Oued Roumane":          (48, 35.8500, 0.6500),
    "Boukadir":              (2,  36.0651, 1.1279),
    "Mécheria":              (45, 33.5435, -0.2567),
    "Naâma":                 (45, 33.2814, -0.3072),
    "Béchar":                (8,  31.6161, -2.2244),
    "Tindouf":               (37, 27.6711, -8.1300),
    "Aïn M'lila":            (4,  36.0375, 6.5710),
    "Oum El Bouaghi":        (4,  35.8739, 7.1150),
    "Tébessa":               (12, 35.4075, 8.1206),
    "Touggourt":             (53, 33.1064, 6.0589),
    "Saïda":                 (20, 34.8422, 0.1517),
    "Tiaret":                (14, 35.3708, 1.3211),
    "Tissemsilt":            (38, 35.6067, 1.8086),
    "Souk Ahras":            (41, 36.2864, 7.9536),
    "Thenia":                (35, 36.7283, 3.5550),
    "Moulay Slissen":        (22, 34.8228, -0.7571),
}

# Known exact fares (DZD) from SNTF pricing
KNOWN_FARES: dict[tuple[str, str], tuple[float, float]] = {
    ("Alger (Agha)", "Oran"): (1750, 1250),
    ("Alger (Agha)", "Annaba"): (2350, 1680),
    ("Alger (Agha)", "Constantine"): (2150, 1530),
    ("Alger (Agha)", "Blida"): (210, 150),
    ("Alger (Agha)", "Boufarik"): (180, 130),
    ("Alger (Agha)", "El Harrach"): (100, 70),
    ("Alger (Agha)", "Chlef"): (1050, 750),
    ("Alger (Agha)", "Bejaia"): (1550, 1100),
    ("Alger (Agha)", "Setif"): (1650, 1180),
    ("Alger (Agha)", "Tizi Ouzou"): (800, 570),
    ("Alger (Agha)", "Batna"): (2200, 1570),
    ("Alger (Agha)", "Biskra"): (3100, 2210),
    ("Alger (Agha)", "Tlemcen"): (2350, 1680),
    ("Oran", "Tlemcen"): (800, 570),
    ("Constantine", "Batna"): (450, 320),
    ("Constantine", "Annaba"): (600, 430),
    ("Constantine", "Biskra"): (900, 640),
    ("Alger (Agha)", "Oued Aissi"): (650, 460),
    ("Alger (Agha)", "Boumerdes"): (250, 180),
    ("Alger (Agha)", "Thenia"): (300, 210),
    ("Alger (Agha)", "Thénia"): (300, 210),
}


def estimate_fare(origin: str, dest: str, distance_km: float) -> tuple[float, float]:
    key = (origin, dest)
    rev = (dest, origin)
    if key in KNOWN_FARES:
        return KNOWN_FARES[key]
    if rev in KNOWN_FARES:
        return KNOWN_FARES[rev]
    first_class = round(distance_km * 3.5, 0)
    second_class = round(distance_km * 2.5, 0)
    return first_class, second_class


# ── Line definitions ──────────────────────────────────────────────
LINE_DEFS: list[dict] = [
    {
        "name": "Alger → Oran (Rocade Nord)",
        "operator": "SNTF", "mode": "train", "color": "#E53935",
        "description": "Ligne Alger-Oran via Blida, Chlef, Relizane (418 km)",
        "stops": [
            "Alger (Agha)", "El Harrach", "Hussein Dey", "Boufarik", "Blida",
            "Mouzaia", "Chiffa", "El Affroun", "Khemis Milliana",
            "Ain Defla", "Oued Fodda", "Chlef", "Oued Sly", "Oued Djemaa",
            "Boukadir", "Oued Roumane", "Relizane", "Oued Rhiou", "Mohammadia",
            "Mascara", "Oued Tlelat", "Es Senia", "Oran",
        ],
    },
    {
        "name": "Alger → Béjaïa",
        "operator": "SNTF", "mode": "train", "color": "#43A047",
        "description": "Ligne Alger-Béjaïa via Tizi Ouzou",
        "stops": [
            "Alger (Agha)", "Hussein Dey", "El Harrach", "Corso", "Boumerdes",
            "Thénia", "Bordj Menaiel", "Issers", "Oued Aissi", "Tizi Ouzou",
            "Draâ El Mizan", "El Akhdariya", "Bouira", "Aghnif", "Beni Mansour",
            "Tazmalt", "El Kseur", "Oued Ghir", "Béjaïa",
        ],
    },
    {
        "name": "Alger → Constantine → Annaba",
        "operator": "SNTF", "mode": "train", "color": "#1E88E5",
        "description": "Ligne Alger-Constantine-Annaba via Sétif",
        "stops": [
            "Alger (Agha)", "Hussein Dey", "El Harrach", "Corso", "Boumerdes",
            "Thénia", "Bordj Menaiel", "Issers", "Oued Aissi", "Tizi Ouzou",
            "Draâ El Mizan", "El Akhdariya", "Bouira", "Bordj Bou Arreridj",
            "El Eulma", "Sétif", "El Gourzi", "Constantine", "El Khroub",
            "M'Daourouch", "Annaba",
        ],
    },
    {
        "name": "Oran → Tlemcen",
        "operator": "SNTF", "mode": "train", "color": "#FB8C00",
        "description": "Ligne Oran-Tlemcen via Sidi Bel Abbès",
        "stops": [
            "Oran", "Es Senia", "Sidi Bel Abbès", "Oued Sefioun", "Tabia",
            "Tlemcen", "Maghnia", "Ghazaouet",
        ],
    },
    {
        "name": "Oran → Béchar (Ligne Minière Ouest)",
        "operator": "SNTF", "mode": "train", "color": "#6D4C41",
        "description": "Ligne minière Ouest Oran-Béchar-Tindouf-Gara Djebilet",
        "stops": [
            "Oran", "Es Senia", "Sidi Bel Abbès", "Tabia", "Ras El Ma",
            "Mécheria", "Naâma", "Béchar", "Tindouf", "Gara Djebilet",
        ],
    },
    {
        "name": "Constantine → Batna → Biskra",
        "operator": "SNTF", "mode": "train", "color": "#8E24AA",
        "description": "Ligne Constantine-Batna-Biskra via El Khroub",
        "stops": [
            "Constantine", "El Khroub", "Batna", "Biskra", "El Kantara",
        ],
    },
    {
        "name": "Boughezoul → Djelfa → Laghouat (Pénétrante Centre)",
        "operator": "SNTF", "mode": "train", "color": "#00ACC1",
        "description": "Pénétrante Centre Boughezoul-Djelfa-Laghouat",
        "stops": [
            "Boughezoul", "Djelfa", "Laghouat",
        ],
    },
    {
        "name": "Constantine → Touggourt",
        "operator": "SNTF", "mode": "train", "color": "#C62828",
        "description": "Ligne Constantine-Touggourt via Aïn M'lila",
        "stops": [
            "Constantine", "El Gourzi", "Aïn M'lila", "Aïn Yagout",
            "Oum El Bouaghi", "Tébessa", "Touggourt",
        ],
    },
    {
        "name": "Hauts Plateaux (Moulay Slissen → Tébessa)",
        "operator": "SNTF", "mode": "train", "color": "#1565C0",
        "description": "Ligne des Hauts Plateaux",
        "stops": [
            "Moulay Slissen", "Saïda", "Tiaret", "Tissemsilt", "M'Sila",
            "Barika", "Batna", "Aïn M'lila", "Tébessa",
        ],
    },
    {
        "name": "Thénia → Oued Aissi (Banlieue)",
        "operator": "SNTF", "mode": "train", "color": "#7CB342",
        "description": "Banlieue Thénia-Oued Aissi",
        "stops": ["Thénia", "Bordj Menaiel", "Issers", "Oued Aissi"],
    },
    {
        "name": "Blida → El Affroun (Banlieue)",
        "operator": "SNTF", "mode": "train", "color": "#FFB300",
        "description": "Banlieue Blida-El Affroun",
        "stops": ["Blida", "Mouzaia", "Chiffa", "El Affroun"],
    },
    {
        "name": "Annaba → Souk Ahras → Tunis (International)",
        "operator": "SNTF", "mode": "train", "color": "#5E35B1",
        "description": "Ligne internationale Annaba-Souk Ahras-Tunis",
        "stops": ["Annaba", "Souk Ahras"],
    },
    {
        "name": "Alger → Oran (Direct)",
        "operator": "SNTF", "mode": "train", "color": "#E53935",
        "description": "Ligne directe Alger-Oran",
        "stops": ["Alger (Agha)", "Blida", "Chlef", "Oran"],
    },
    {
        "name": "Alger → Constantine (Direct)",
        "operator": "SNTF", "mode": "train", "color": "#1E88E5",
        "description": "Ligne directe Alger-Constantine",
        "stops": ["Alger (Agha)", "Sétif", "Constantine"],
    },
]


def main() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    total_raw = len(raw)
    print(f"Loaded {total_raw} raw stations from {RAW_PATH}")

    # ── Step 1: Validate wilaya mappings ──
    validated: list[dict] = []
    issues: list[str] = []
    wilaya_counts: dict[int, int] = {}
    corrected: int = 0
    unchanged: int = 0
    no_coords: int = 0

    for s in raw:
        wid, wname, changed = validate_wilaya(s)
        if changed:
            corrected += 1
        else:
            unchanged += 1
        if s.get("lat") is None:
            no_coords += 1
        if wid is None and s.get("lat") is not None:
            issues.append(f"Uncertain wilaya: {s['name']} at ({s['lat']:.4f}, {s['lng']:.4f})")

        entry = {
            "name": s["name"],
            "name_clean": s.get("name_clean", s["name"]),
            "lat": s.get("lat"),
            "lng": s.get("lng"),
            "wilaya_id": wid,
            "wilaya_name": wname,
        }
        validated.append(entry)
        if wid:
            wilaya_counts[wid] = wilaya_counts.get(wid, 0) + 1

    stations_coords = [s for s in validated if s["lat"] is not None]
    print(f"Validated {len(validated)} stations ({len(stations_coords)} with coords)")
    print(f"  Corrected: {corrected}, Unchanged: {unchanged}, No coords: {no_coords}")

    # ── Step 2: Add synthetic stations for well-known SNTF stops ──
    existing_names = {normalize(s["name"]) for s in validated}
    existing_clean = {normalize(s.get("name_clean", "")) for s in validated}
    added_synthetic = 0
    for syn_name, (wid, lat, lng) in SYNTHETIC_STATIONS.items():
        n = normalize(syn_name)
        if n not in existing_names and n not in existing_clean:
            entry = {
                "name": syn_name.upper(),
                "name_clean": syn_name,
                "lat": lat,
                "lng": lng,
                "wilaya_id": wid,
                "wilaya_name": WILAYA_NAMES.get(wid),
            }
            validated.append(entry)
            wilaya_counts[wid] = wilaya_counts.get(wid, 0) + 1
            added_synthetic += 1

    stations_coords = [s for s in validated if s["lat"] is not None]
    print(f"Added {added_synthetic} synthetic stations → total {len(validated)} ({len(stations_coords)} with coords)")

    # ── Step 3: Build lines ──
    lines: list[dict] = []
    unmatched_stops: list[tuple[str, str]] = []

    lookup: dict[str, dict] = {}
    for s in validated:
        lookup[normalize(s["name"])] = s
        lookup[normalize(s.get("name_clean", ""))] = s

    def resolve(name: str) -> dict | None:
        n = normalize(name)
        if n in lookup:
            return lookup[n]
        return match_station(name, validated)

    for line_def in LINE_DEFS:
        resolved_stops: list[dict] = []
        for stop_name in line_def["stops"]:
            match = resolve(stop_name)
            if match is None:
                unmatched_stops.append((line_def["name"], stop_name))
            else:
                resolved_stops.append(match)

        if not resolved_stops:
            continue

        total_dist = 0.0
        for i in range(len(resolved_stops) - 1):
            s1 = resolved_stops[i]
            s2 = resolved_stops[i + 1]
            if s1["lat"] and s1["lng"] and s2["lat"] and s2["lng"]:
                total_dist += haversine_km(s1["lat"], s1["lng"], s2["lat"], s2["lng"])

        first_stop_name = resolved_stops[0]["name_clean"]
        last_stop_name = resolved_stops[-1]["name_clean"]
        first_fare, second_fare = estimate_fare(first_stop_name, last_stop_name, total_dist)

        line = {
            "name": line_def["name"],
            "operator": line_def["operator"],
            "mode": line_def["mode"],
            "color": line_def["color"],
            "description": line_def["description"],
            "stops": [s["name_clean"] for s in resolved_stops],
            "distance_km": round(total_dist, 1),
            "estimated_fare_1ere_dzd": first_fare,
            "estimated_fare_2eme_dzd": second_fare,
        }
        lines.append(line)

    # ── Step 4: Write output ──
    output = {"stations": validated, "lines": lines}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOutput written to {OUTPUT_PATH}")

    # ── Step 5: Summary ──
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total stations (validated + synthetic): {len(validated)}")
    print(f"  With coordinates: {len(stations_coords)}")
    print(f"  Without coordinates: {sum(1 for s in validated if s['lat'] is None)}")
    print(f"  Wilaya corrections from raw data: {corrected}")
    print(f"  Synthetic stations added: {added_synthetic}")
    used_in_lines = set()
    for l in lines:
        for s in l["stops"]:
            for v in validated:
                if v["name_clean"] == s:
                    used_in_lines.add(v["name"])
                    break
    print(f"  Stations referenced in lines: {len(used_in_lines)}")

    print(f"\nStations per wilaya:")
    for wid in sorted(wilaya_counts, key=lambda x: wilaya_counts[x], reverse=True):
        wname = WILAYA_NAMES.get(wid, f"Wilaya {wid}")
        print(f"  Wilaya {wid:2d} ({wname:30s}): {wilaya_counts[wid]:3d}")

    print(f"\nTotal lines: {len(lines)}")
    for line in lines:
        stop_count = len(line["stops"])
        print(f"  {line['name']:55s} → {stop_count:2d} stops, {line['distance_km']:6.1f} km, "
              f"1ère: {line['estimated_fare_1ere_dzd']:6.0f} DZD, "
              f"2ème: {line['estimated_fare_2eme_dzd']:6.0f} DZD")

    if issues:
        print(f"\nKnown issues ({len(issues)}):")
        for iss in issues[:10]:
            print(f"  - {iss}")

    if unmatched_stops:
        print(f"\nUnmatched stops ({len(unmatched_stops)} total):")
        for line_name, stop in unmatched_stops:
            print(f"  [{line_name}] -> '{stop}'")


if __name__ == "__main__":
    main()
