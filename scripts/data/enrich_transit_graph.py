#!/usr/bin/env python3
"""
Enrichment script that reads scraper output + SNTF seed data and produces
improved JSON files with coordinates, types, operators, wilaya mapping,
and additional transport modes (cable car, taxi, ferry, flight).
"""

import json
import math
import os
import re
import time
import urllib.request
import urllib.parse

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "data")

OSM_USER_AGENT = "ATHAR-TransitGraph/1.0 (enrichment script)"

# ---------------------------------------------------------------------------
# 0.  Wilaya data
# ---------------------------------------------------------------------------

WILAYA_BY_ID = {
    1: {"name": "Adrar", "lat": 27.8734, "lng": -0.2838},
    2: {"name": "Chlef", "lat": 36.1644, "lng": 1.3347},
    3: {"name": "Laghouat", "lat": 33.7956, "lng": 2.8742},
    4: {"name": "Oum El Bouaghi", "lat": 35.8739, "lng": 7.1150},
    5: {"name": "Batna", "lat": 35.5544, "lng": 6.1742},
    6: {"name": "Bejaia", "lat": 36.7506, "lng": 5.0778},
    7: {"name": "Biskra", "lat": 34.8528, "lng": 5.7306},
    8: {"name": "Bechar", "lat": 31.6167, "lng": -2.2247},
    9: {"name": "Blida", "lat": 36.4785, "lng": 2.8161},
    10: {"name": "Bouira", "lat": 36.3808, "lng": 3.9053},
    11: {"name": "Tamanrasset", "lat": 22.7850, "lng": 5.5228},
    12: {"name": "Tebessa", "lat": 35.4072, "lng": 8.1208},
    13: {"name": "Tlemcen", "lat": 34.8767, "lng": -1.3156},
    14: {"name": "Tiaret", "lat": 35.3694, "lng": 1.3211},
    15: {"name": "Tizi Ouzou", "lat": 36.7150, "lng": 4.0475},
    16: {"name": "Algiers", "lat": 36.7533, "lng": 3.0631},
    17: {"name": "Djelfa", "lat": 34.6733, "lng": 3.2481},
    18: {"name": "Jijel", "lat": 36.8194, "lng": 5.7714},
    19: {"name": "Setif", "lat": 36.1917, "lng": 5.4089},
    20: {"name": "Saida", "lat": 34.8303, "lng": 0.1514},
    21: {"name": "Skikda", "lat": 36.8728, "lng": 6.9100},
    22: {"name": "Sidi Bel Abbes", "lat": 35.1939, "lng": -0.6378},
    23: {"name": "Annaba", "lat": 36.9067, "lng": 7.7628},
    24: {"name": "Guelma", "lat": 36.4518, "lng": 7.4414},
    25: {"name": "Constantine", "lat": 36.3650, "lng": 6.6147},
    26: {"name": "Medea", "lat": 36.2672, "lng": 2.7531},
    27: {"name": "Mostaganem", "lat": 35.9311, "lng": 0.0889},
    28: {"name": "Msila", "lat": 35.7050, "lng": 4.5417},
    29: {"name": "Mascara", "lat": 35.3986, "lng": 0.1431},
    30: {"name": "Ouargla", "lat": 31.9583, "lng": 5.3333},
    31: {"name": "Oran", "lat": 35.6989, "lng": -0.6423},
    32: {"name": "El Bayadh", "lat": 33.6831, "lng": 1.0192},
    33: {"name": "Illizi", "lat": 26.7153, "lng": 8.5581},
    34: {"name": "Bordj Bou Arreridj", "lat": 36.0711, "lng": 4.7611},
    35: {"name": "Boumerdes", "lat": 36.7567, "lng": 3.4744},
    36: {"name": "El Tarf", "lat": 36.7667, "lng": 8.3167},
    37: {"name": "Tindouf", "lat": 27.6711, "lng": -8.1300},
    38: {"name": "Tissemsilt", "lat": 35.6064, "lng": 1.8089},
    39: {"name": "El Oued", "lat": 33.4644, "lng": 6.8681},
    40: {"name": "Khenchela", "lat": 35.4286, "lng": 7.1494},
    41: {"name": "Souk Ahras", "lat": 36.2861, "lng": 7.9539},
    42: {"name": "Tipaza", "lat": 36.5894, "lng": 2.4447},
    43: {"name": "Mila", "lat": 36.4500, "lng": 6.2647},
    44: {"name": "Ain Defla", "lat": 36.2633, "lng": 1.9672},
    45: {"name": "Naama", "lat": 33.2814, "lng": -0.3072},
    46: {"name": "Ain Temouchent", "lat": 35.2982, "lng": -1.1396},
    47: {"name": "Ghardaia", "lat": 32.4883, "lng": 3.6717},
    48: {"name": "Relizane", "lat": 35.7358, "lng": 0.5539},
    51: {"name": "Ain Salah", "lat": 27.2472, "lng": 2.5119},
    53: {"name": "Touggourt", "lat": 33.1064, "lng": 6.0589},
    54: {"name": "Djanet", "lat": 24.5547, "lng": 9.4842},
    55: {"name": "El M'Ghair", "lat": 33.9500, "lng": 5.9167},
    61: {"name": "El Aricha", "lat": 34.3385, "lng": -0.8494},
    62: {"name": "El Kantara", "lat": 35.2231, "lng": 5.7093},
    63: {"name": "Barika", "lat": 35.3753, "lng": 5.3831},
    64: {"name": "Bou Saada", "lat": 35.2747, "lng": 4.2058},
    66: {"name": "Ksar El Boukhari", "lat": 35.7030, "lng": 2.8432},
    67: {"name": "Ksar Chellala", "lat": 35.4367, "lng": 2.2141},
    68: {"name": "Ain Oussera", "lat": 35.0649, "lng": 3.0334},
}

WILAYA_BY_NAME = {}
for wid, wdata in WILAYA_BY_ID.items():
    for variant in (wdata["name"].lower(), wdata["name"].lower().replace(" ", "").replace("-", "").replace("'", "")):
        WILAYA_BY_NAME[variant] = wid
ADDITIONAL_WILAYA_NAMES = {
    "algiers": 16, "alger": 16, "oran": 31, "constantine": 25, "annaba": 23,
    "bejaia": 6, "bejaïa": 6, "setif": 19, "sétif": 19, "blida": 9,
    "chlef": 2, "tlemcen": 13, "skikda": 21, "biskra": 7, "batna": 5,
    "djelfa": 17, "msila": 28, "mascara": 29, "ouargla": 30, "medea": 26,
    "saida": 20, "guelma": 24, "ain temouchent": 46, "ain defla": 44,
    "naama": 45, "ghardaia": 47, "ghardaïa": 47, "relizane": 48,
    "el tarf": 36, "mila": 43, "boumerdes": 35, "tissemsilt": 38,
    "khenchela": 40, "souk ahras": 41, "tiaret": 14, "adrar": 1,
    "laghouat": 3, "oum el bouaghi": 4, "jijel": 18, "tizi ouzou": 15,
    "bouira": 10, "bechar": 8, "béchar": 8, "tebessa": 12, "tébessa": 12,
    "bordj bou arreridj": 34, "el oued": 39, "el bayadh": 32,
    "illizi": 33, "tindouf": 37, "tamanrasset": 11,
}
WILAYA_BY_NAME.update(ADDITIONAL_WILAYA_NAMES)


# ---------------------------------------------------------------------------
# 1.  Helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def make_node_id(name, ntype):
    safe = re.sub(r"[^a-zA-Z0-9]", "_", name).upper()
    return f"STATION_{ntype.upper()}_{safe}"


def make_edge_id(fid, tid, prefix="EDGE"):
    sf = fid.replace("STATION_", "").replace("_", "")
    st = tid.replace("STATION_", "").replace("_", "")
    return f"{prefix}_{sf}_{st}"


def has_valid_coords(node):
    lat = node.get("latitude") or node.get("lat")
    lng = node.get("longitude") or node.get("lng")
    if lat is None or lng is None:
        return False
    lat = float(lat)
    lng = float(lng)
    return abs(lat) > 0.01 and abs(lng) > 0.01


def osm_geocode(query, retries=3):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "format": "json", "limit": 1, "q": query
    })
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": OSM_USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            if data and "lat" in data[0] and "lon" in data[0]:
                return float(data[0]["lat"]), float(data[0]["lon"])
            return None, None
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                print(f"  429 rate-limited, waiting 60s...")
                time.sleep(60)
                continue
            print(f"  HTTP error {e.code} for '{query}'")
            return None, None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            print(f"  Exception for '{query}': {e}")
            return None, None
    return None, None


def detect_wilaya_from_name(name):
    nl = name.lower()
    for wname, wid in WILAYA_BY_NAME.items():
        if wname in nl:
            return wid
    extra = {
        "ain oussera": 68, "ksar el boukhari": 66, "ksar chellala": 67,
    "el kantara": 62, "barika": 63, "bou saada": 64, "el m'ghair": 55,
    "djanet": 54, "touggourt": 53, "ain salah": 51, "el aricha": 61,
    "ain sefra": 45, "ain safra": 45, "mecheria": 45, "naama": 45,
    "el menia": 55, "el menyia": 55,
    }
    for wname, wid in extra.items():
        if wname in nl:
            return wid
    return None


def detect_wilaya_from_coords(lat, lng):
    best = 16
    best_d = float("inf")
    for wid, wdata in WILAYA_BY_ID.items():
        d = haversine_km(lat, lng, wdata["lat"], wdata["lng"])
        if d < best_d:
            best_d = d
            best = wid
    return best


def ensure_wilaya(node):
    if node.get("wilaya_id") and node["wilaya_id"] not in (None, "", 0):
        return node["wilaya_id"]
    wid = None
    name = node.get("name", "")
    if name:
        wid = detect_wilaya_from_name(name)
    if wid is None:
        lat = node.get("latitude") or node.get("lat")
        lng = node.get("longitude") or node.get("lng")
        if lat and lng and abs(float(lat)) > 0.01 and abs(float(lng)) > 0.01:
            wid = detect_wilaya_from_coords(float(lat), float(lng))
    if wid is None:
        wid = 16
    return wid


def normalize_station_name(name):
    return re.sub(r"\s+", " ", name.strip().lower())


# ---------------------------------------------------------------------------
# 2.  Load input files
# ---------------------------------------------------------------------------

print("=" * 60)
print("ATHAR Transit Graph Enrichment")
print("=" * 60)

with open(os.path.join(DATA_DIR, "transit_nodes.json")) as f:
    scraper_nodes = json.load(f)
print(f"Loaded {len(scraper_nodes)} scraper nodes")

with open(os.path.join(DATA_DIR, "transit_edges.json")) as f:
    scraper_edges = json.load(f)
print(f"Loaded {len(scraper_edges)} scraper edges")

with open(os.path.join(DATA_DIR, "sntf_seed_complete.json")) as f:
    sntf_seed = json.load(f)
print(f"Loaded {len(sntf_seed['stations'])} SNTF seed stations, {len(sntf_seed['lines'])} line definitions")

# Build node_id lookup from scraper data (preserve original IDs)
scraper_node_id_map = {n["name"]: n["node_id"] for n in scraper_nodes}

with open(os.path.join(DATA_DIR, "sntf_enriched.json")) as f:
    sntf_enriched = json.load(f)

# Build SNTF station code lookup
sntf_code_map = {}
for code_name, code_val in sntf_enriched.get("station_codes", {}).items():
    sntf_code_map[code_name.lower().strip()] = code_val

# ---------------------------------------------------------------------------
# 3.  Merge nodes
# ---------------------------------------------------------------------------

seen = {}
merged_nodes = []
duplicate_count = 0
no_coord_count = 0

for node in scraper_nodes:
    if not has_valid_coords(node):
        no_coord_count += 1
        continue
    key = (normalize_station_name(node["name"]), node["type"])
    if key in seen:
        duplicate_count += 1
        continue
    seen[key] = True
    merged_nodes.append(dict(node))

seed_stations_added = 0
for s in sntf_seed["stations"]:
    name = s.get("name_clean", s.get("name", ""))
    lat = s.get("lat")
    lng = s.get("lng")
    if lat is None or lng is None or abs(lat) < 0.01:
        continue
    wilaya_id = s.get("wilaya_id")
    key = (normalize_station_name(name), "train")
    if key in seen:
        continue
    seen[key] = True
    sntf_code = sntf_code_map.get(name.lower().strip())
    node = {
        "node_id": make_node_id(name, "train"),
        "name": name,
        "name_ar": "",
        "name_en": "",
        "type": "train",
        "subtype": "intercity",
        "operator": "SNTF",
        "wilaya_id": wilaya_id or 16,
        "latitude": lat,
        "longitude": lng,
        "osm_data": {},
        "codes": {"sntf": sntf_code} if sntf_code else {},
        "lines_at_station": [],
        "has_parking": None,
        "has_accessibility": None,
        "metadata": {"station_code": sntf_code, "source": "sntf_seed"} if sntf_code else {"source": "sntf_seed"},
    }
    merged_nodes.append(node)
    seed_stations_added += 1

print(f"After dedup: {len(merged_nodes)} nodes ({duplicate_count} dupes, {no_coord_count} no-coord skipped, {seed_stations_added} seed added)")

# ---------------------------------------------------------------------------
# 4.  Geocode missing bus stations
# ---------------------------------------------------------------------------

BUS_GEOCODE_QUERIES = [
    ("Gare Routière de Ain Safra", "Ain Sefra Algeria"),
    ("Gare Routière de El Bayadh", "El Bayadh Algeria"),
    ("Gare Routière de H.Messaoud", "Hassi Messaoud Algeria"),
    ("Gare Routière de Mecheria", "Mecheria Algeria"),
    ("Gare Routière de Mostaghanem", "Mostaganem Algeria"),
    ("Gare Routière de Touggourt", "Touggourt Algeria"),
    ("Gare Routière de Oum El Bouaghi", "Oum El Bouaghi Algeria"),
    ("Gare Routière de Bordj Bou Arreridj", "Bordj Bou Arreridj Algeria"),
    ("Gare Routière de El Menia", "El Menia Algeria"),
]

osm_requests = 0
geocoded_count = 0

bus_geocode_results = {}
print("\n--- Geocoding bus stations ---")
for bus_name, query in BUS_GEOCODE_QUERIES:
    lat, lng = osm_geocode(query)
    osm_requests += 1
    print(f"  {bus_name}: {lat}, {lng}")
    if lat:
        bus_geocode_results[bus_name] = (lat, lng)
        geocoded_count += 1
    time.sleep(1.1)

# Add geocoded bus stations to merged_nodes (they were skipped earlier)
for bus_name, (blat, blng) in bus_geocode_results.items():
    key = (normalize_station_name(bus_name), "bus")
    if key in seen:
        continue
    seen[key] = True
    orig_id = scraper_node_id_map.get(bus_name)
    merged_nodes.append({
        "node_id": orig_id or make_node_id(bus_name, "bus"),
        "name": bus_name,
        "name_ar": "",
        "name_en": bus_name,
        "type": "bus",
        "subtype": "intercity",
        "operator": "SOGRAL",
        "wilaya_id": detect_wilaya_from_name(bus_name.replace("Gare Routière de ", "").strip()) or 16,
        "latitude": blat,
        "longitude": blng,
        "osm_data": {},
        "codes": {},
        "lines_at_station": [],
        "has_parking": None,
        "has_accessibility": None,
        "metadata": {"source": "geocoded"},
    })

# ---------------------------------------------------------------------------
# 5.  Geocode missing SNTF seed stations (lazily, those not yet in merged)
# ---------------------------------------------------------------------------

print("\n--- Geocoding missing SNTF seed stations via OSM ---")
for s in sntf_seed["stations"]:
    name = s.get("name_clean", s.get("name", ""))
    lat = s.get("lat")
    lng = s.get("lng")
    if lat is not None and lng is not None and abs(lat) > 0.01:
        continue
    key = (normalize_station_name(name), "train")
    if key in seen:
        continue
    query = f"{name} Algeria"
    res_lat, res_lng = osm_geocode(query)
    osm_requests += 1
    if res_lat:
        s["lat"] = res_lat
        s["lng"] = res_lng
        geocoded_count += 1
        print(f"  Geocoded: {name} -> {res_lat}, {res_lng}")
        # Add to merged nodes
        sntf_code = sntf_code_map.get(name.lower().strip())
        wilaya_id = s.get("wilaya_id") or detect_wilaya_from_name(name) or 16
        node = {
            "node_id": make_node_id(name, "train"),
            "name": name,
            "name_ar": "",
            "name_en": "",
            "type": "train",
            "subtype": "intercity",
            "operator": "SNTF",
            "wilaya_id": wilaya_id,
            "latitude": res_lat,
            "longitude": res_lng,
            "osm_data": {},
            "codes": {"sntf": sntf_code} if sntf_code else {},
            "lines_at_station": [],
            "has_parking": None,
            "has_accessibility": None,
            "metadata": {"source": "sntf_seed_geocoded"},
        }
        merged_nodes.append(node)
        seen[key] = True
    else:
        print(f"  FAILED: {name}")
    time.sleep(1.1)

# Fallback for SNTF stations that failed OSM geocoding — use wilaya capital coords
fallback_count = 0
for s in sntf_seed["stations"]:
    name = s.get("name_clean", s.get("name", ""))
    lat = s.get("lat")
    lng = s.get("lng")
    if lat is not None and lng is not None and abs(lat) > 0.01:
        continue
    key = (normalize_station_name(name), "train")
    if key in seen:
        continue
    wilaya_id = s.get("wilaya_id") or detect_wilaya_from_name(name) or 16
    wdata = WILAYA_BY_ID.get(wilaya_id)
    if wdata:
        s["lat"] = wdata["lat"]
        s["lng"] = wdata["lng"]
        fallback_count += 1
        sntf_code = sntf_code_map.get(name.lower().strip())
        node = {
            "node_id": make_node_id(name, "train"),
            "name": name,
            "name_ar": "",
            "name_en": "",
            "type": "train",
            "subtype": "intercity",
            "operator": "SNTF",
            "wilaya_id": wilaya_id,
            "latitude": wdata["lat"],
            "longitude": wdata["lng"],
            "osm_data": {},
            "codes": {"sntf": sntf_code} if sntf_code else {},
            "lines_at_station": [],
            "has_parking": None,
            "has_accessibility": None,
            "metadata": {"source": "sntf_seed_fallback"},
        }
        merged_nodes.append(node)
        seen[key] = True

print(f"OSM requests: {osm_requests}, geocoded: {geocoded_count}, fallback: {fallback_count}")

# ---------------------------------------------------------------------------
# 6.  Add cable car stations
# ---------------------------------------------------------------------------

CABLE_CAR_STATIONS = [
    {"name": "Palais de la Culture (Télécabine)", "lat": 36.7431, "lng": 3.0772, "wilaya": 16},
    {"name": "El Madania (Télécabine)", "lat": 36.7486, "lng": 3.0661, "wilaya": 16},
    {"name": "Mémorial du Martyr (Télécabine)", "lat": 36.7469, "lng": 3.0717, "wilaya": 16},
]

ORAN_CABLE_CAR = [
    {"name": "Gare SNTF Oran (Télécabine)", "lat": 35.6939, "lng": -0.6423, "wilaya": 31},
    {"name": "Notre-Dame d'Afrique (Télécabine)", "lat": 35.7033, "lng": -0.6539, "wilaya": 31},
    {"name": "Santa Cruz (Télécabine)", "lat": 35.7056, "lng": -0.6611, "wilaya": 31},
]

cable_car_nodes = []
for cc in CABLE_CAR_STATIONS + ORAN_CABLE_CAR:
    nid = make_node_id(cc["name"], "cablecar")
    cable_car_nodes.append({
        "node_id": nid,
        "name": cc["name"],
        "name_ar": "",
        "name_en": "",
        "type": "cablecar",
        "subtype": "urban",
        "operator": "Télécabine d'Alger" if cc["wilaya"] == 16 else "Télécabine d'Oran",
        "wilaya_id": cc["wilaya"],
        "latitude": cc["lat"],
        "longitude": cc["lng"],
        "osm_data": {},
        "codes": {},
        "lines_at_station": ["Télécabine d'Alger"] if cc["wilaya"] == 16 else ["Télécabine d'Oran"],
        "has_parking": None,
        "has_accessibility": None,
        "metadata": {"source": "manual"},
    })

merged_nodes.extend(cable_car_nodes)
print(f"Added {len(cable_car_nodes)} cable car stations")

# Build cable car edges
cable_car_edges = []
algiers_cable_names = [cc["name"] for cc in CABLE_CAR_STATIONS]
oran_cable_names = [cc["name"] for cc in ORAN_CABLE_CAR]
cc_nodes_by_name = {n["name"]: n["node_id"] for n in cable_car_nodes}

for i in range(len(algiers_cable_names) - 1):
    fn = algiers_cable_names[i]
    tn = algiers_cable_names[i + 1]
    fid = cc_nodes_by_name[fn]
    tid = cc_nodes_by_name[tn]
    dist = haversine_km(
        CABLE_CAR_STATIONS[i]["lat"], CABLE_CAR_STATIONS[i]["lng"],
        CABLE_CAR_STATIONS[i + 1]["lat"], CABLE_CAR_STATIONS[i + 1]["lng"]
    )
    for direction, f, t in [("forward", fid, tid), ("backward", tid, fid)]:
        cable_car_edges.append({
            "edge_id": make_edge_id(f, t, "EDGE_CABLECAR"),
            "from_node_id": f,
            "to_node_id": t,
            "line_name": "Télécabine d'Alger",
            "line_id": "CABLECAR_ALG",
            "operator": "Télécabine d'Alger",
            "mode": "cablecar",
            "subtype": "urban",
            "distance_km": round(dist, 2),
            "duration_min": max(1, round(dist / 0.02 * 0.5)),
            "stops_between": 0,
            "direction": direction,
            "schedule": [],
            "pricing": {},
            "frequency_min": 10,
            "metadata": {},
        })

for i in range(len(oran_cable_names) - 1):
    fn = oran_cable_names[i]
    tn = oran_cable_names[i + 1]
    fid = cc_nodes_by_name[fn]
    tid = cc_nodes_by_name[tn]
    dist = haversine_km(
        ORAN_CABLE_CAR[i]["lat"], ORAN_CABLE_CAR[i]["lng"],
        ORAN_CABLE_CAR[i + 1]["lat"], ORAN_CABLE_CAR[i + 1]["lng"]
    )
    for direction, f, t in [("forward", fid, tid), ("backward", tid, fid)]:
        cable_car_edges.append({
            "edge_id": make_edge_id(f, t, "EDGE_CABLECAR"),
            "from_node_id": f,
            "to_node_id": t,
            "line_name": "Télécabine d'Oran",
            "line_id": "CABLECAR_ORA",
            "operator": "Télécabine d'Oran",
            "mode": "cablecar",
            "subtype": "urban",
            "distance_km": round(dist, 2),
            "duration_min": max(1, round(dist / 0.02 * 0.5)),
            "stops_between": 0,
            "direction": direction,
            "schedule": [],
            "pricing": {},
            "frequency_min": 10,
            "metadata": {},
        })

print(f"Added {len(cable_car_edges)} cable car edges")

# ---------------------------------------------------------------------------
# 7.  Add shared taxi stations
# ---------------------------------------------------------------------------

# Build a map of SOGRAL bus stations for taxi co-location
sogral_nodes = [n for n in merged_nodes if n.get("operator") == "SOGRAL" and has_valid_coords(n)]

taxi_nodes = []
taxi_seen_names = set()

for wid, wdata in WILAYA_BY_ID.items():
    city_name = wdata["name"]
    taxi_name = f"{city_name} (Taxi Station)"
    if taxi_name in taxi_seen_names:
        continue
    taxi_seen_names.add(taxi_name)
    taxi_nodes.append({
        "node_id": make_node_id(taxi_name, "taxi"),
        "name": taxi_name,
        "name_ar": "",
        "name_en": "",
        "type": "taxi",
        "subtype": "intercity",
        "operator": "Taxi",
        "wilaya_id": wid,
        "latitude": wdata["lat"],
        "longitude": wdata["lng"],
        "osm_data": {},
        "codes": {},
        "lines_at_station": [],
        "has_parking": None,
        "has_accessibility": None,
        "metadata": {"source": "manual"},
    })

for sn in sogral_nodes:
    taxi_name = f"{sn['name'].replace('Gare Routière de ', '').strip()} (Taxi Station)"
    if taxi_name in taxi_seen_names:
        continue
    taxi_seen_names.add(taxi_name)
    taxi_nodes.append({
        "node_id": make_node_id(taxi_name, "taxi"),
        "name": taxi_name,
        "name_ar": "",
        "name_en": "",
        "type": "taxi",
        "subtype": "intercity",
        "operator": "Taxi",
        "wilaya_id": sn.get("wilaya_id") or 16,
        "latitude": sn["latitude"],
        "longitude": sn["longitude"],
        "osm_data": {},
        "codes": {},
        "lines_at_station": [],
        "has_parking": None,
        "has_accessibility": None,
        "metadata": {"source": "manual"},
    })

merged_nodes.extend(taxi_nodes)
print(f"Added {len(taxi_nodes)} taxi stations")

# ---------------------------------------------------------------------------
# 8.  Add ferry routes
# ---------------------------------------------------------------------------

FERRIES = [
    {"from": "Port d'Alger (Ferry)", "fl": 36.7556, "fg": 3.0792, "fw": 16,
     "to": "Port de Marseille (Ferry)", "tl": 43.2965, "tg": 5.3698, "tw": None, "dur": 1440, "dist": 770},
    {"from": "Port d'Alger (Ferry)", "fl": 36.7556, "fg": 3.0792, "fw": 16,
     "to": "Port de Tunis (Ferry)", "tl": 36.8000, "tg": 10.1833, "tw": None, "dur": 2160, "dist": 640},
    {"from": "Port d'Alger (Ferry)", "fl": 36.7556, "fg": 3.0792, "fw": 16,
     "to": "Port de Sète (Ferry)", "tl": 43.4167, "tg": 3.7000, "tw": None, "dur": 1380, "dist": 700},
    {"from": "Port d'Oran (Ferry)", "fl": 35.7075, "fg": -0.65, "fw": 31,
     "to": "Port d'Alicante (Ferry)", "tl": 38.3453, "tg": -0.4815, "tw": None, "dur": 480, "dist": 300},
    {"from": "Port de Béjaïa (Ferry)", "fl": 36.7517, "fg": 5.0806, "fw": 6,
     "to": "Port de Marseille (Ferry)", "tl": 43.2965, "tg": 5.3698, "tw": None, "dur": 1380, "dist": 730},
    {"from": "Port de Skikda (Ferry)", "fl": 36.8744, "fg": 6.9108, "fw": 21,
     "to": "Port de Marseille (Ferry)", "tl": 43.2965, "tg": 5.3698, "tw": None, "dur": 1440, "dist": 740},
]

ferry_nodes_added = {}
ferry_edges = []

for f_def in FERRIES:
    for end in ["from", "to"]:
        name = f_def[end]
        if name not in ferry_nodes_added and name not in {n["name"] for n in merged_nodes}:
            fl = f_def[end[0] + "l"]
            fg = f_def[end[0] + "g"]
            fw = f_def[end[0] + "w"]
            ferry_nodes_added[name] = {
                "node_id": make_node_id(name, "ferry"),
                "name": name,
                "name_ar": "",
                "name_en": "",
                "type": "ferry",
                "subtype": "intercity",
                "operator": "Algérie Ferries",
                "wilaya_id": fw or 16,
                "latitude": fl,
                "longitude": fg,
                "osm_data": {},
                "codes": {},
                "lines_at_station": [],
                "has_parking": None,
                "has_accessibility": None,
                "metadata": {"source": "manual"},
            }

# Find existing port nodes
ferry_node_map = {n["name"]: n["node_id"] for n in merged_nodes if n["type"] == "ferry"}
ferry_node_map.update({n["name"]: n["node_id"] for n in ferry_nodes_added.values()})

for f_def in FERRIES:
    fn = f_def["from"]
    tn = f_def["to"]
    fid = ferry_node_map.get(fn)
    tid = ferry_node_map.get(tn)
    if not fid or not tid:
        continue
    for direction, f, t in [("forward", fid, tid), ("backward", tid, fid)]:
        ferry_edges.append({
            "edge_id": make_edge_id(f, t, "EDGE_FERRY"),
            "from_node_id": f,
            "to_node_id": t,
            "line_name": f"{fn} ↔ {tn}",
            "line_id": "FERRY_ALGERIE",
            "operator": "Algérie Ferries",
            "mode": "ferry",
            "subtype": "intercity",
            "distance_km": f_def["dist"],
            "duration_min": f_def["dur"],
            "stops_between": 0,
            "direction": direction,
            "schedule": [],
            "pricing": {},
            "frequency_min": 1440,
            "metadata": {},
        })

merged_nodes.extend(ferry_nodes_added.values())
print(f"Added {len(ferry_nodes_added)} ferry port nodes, {len(ferry_edges)} ferry edges")

# ---------------------------------------------------------------------------
# 9.  Add flight routes (Air Algérie)
# ---------------------------------------------------------------------------

# All existing airport nodes
airport_nodes = {n["name"]: n for n in merged_nodes if n["type"] == "airport"}

# Domestic airports to add
NEW_AIRPORTS = {
    "Aéroport d'Oran (Ahmed Ben Bella)": (35.6239, -0.6211, 31, "ORN"),
    "Aéroport de Constantine (Mohamed Boudiaf)": (36.2811, 6.6172, 25, "CZL"),
    "Aéroport d'Annaba (Rabah Bitat)": (36.8228, 7.8067, 23, "AAE"),
    "Aéroport de Tlemcen (Zenata)": (35.0167, -1.45, 13, "TLM"),
    "Aéroport d'Ouargla (Aïn Beida)": (31.9219, 5.4117, 30, "OGX"),
    "Aéroport de Tamanrasset (Aguenar)": (22.8122, 5.4508, 11, "TMR"),
    "Aéroport de Hassi Messaoud (Oued Irara)": (31.6728, 6.1403, 30, "HME"),
    "Aéroport de Béchar (Boudghene)": (31.6442, -2.2486, 8, "CBH"),
    "Aéroport de Béjaïa (Soummam)": (36.7114, 5.0692, 6, "BJA"),
    "Aéroport de Ghardaïa (Noumérat)": (32.3864, 3.7931, 47, "GHA"),
    "Aéroport de Timimoun": (29.2500, 0.2333, 49, "TMX"),
    "Aéroport d'In Amenas": (28.0500, 9.6333, 33, "IAM"),
    "Aéroport de Djanet (Tiska)": (24.2928, 9.4522, 54, "DJG"),
    "Aéroport d'Illizi (Takhamalt)": (26.7153, 8.5581, 33, "VVZ"),
    "Aéroport d'El Oued (Guemar)": (33.5114, 6.7767, 39, "ELU"),
}

INTERNATIONAL_AIRPORTS = {
    "Aéroport de Paris-Charles-de-Gaulle": (49.0097, 2.5478, None, "CDG"),
    "Aéroport de Marseille Provence": (43.4367, 5.2150, None, "MRS"),
    "Aéroport de Lyon-Saint Exupéry": (45.7256, 5.0811, None, "LYS"),
    "Aéroport de Toulouse-Blagnac": (43.6350, 1.3678, None, "TLS"),
    "Aéroport de Nice-Côte d'Azur": (43.6653, 7.2150, None, "NCE"),
    "Aéroport d'Istanbul": (41.2753, 28.7519, None, "IST"),
}

airport_nodes_added = {}
for aname, (alat, alng, awid, aiata) in {**NEW_AIRPORTS, **INTERNATIONAL_AIRPORTS}.items():
    if aname not in {n["name"] for n in merged_nodes}:
        airport_nodes_added[aname] = {
            "node_id": make_node_id(aname, "airport"),
            "name": aname,
            "name_ar": "",
            "name_en": aname,
            "type": "airport",
            "subtype": "intercity",
            "operator": "EGSA",
            "wilaya_id": awid or 16,
            "latitude": alat,
            "longitude": alng,
            "osm_data": {},
            "codes": {"iata": aiata},
            "lines_at_station": [],
            "has_parking": None,
            "has_accessibility": None,
            "metadata": {"source": "manual"},
        }

merged_nodes.extend(airport_nodes_added.values())

# Rebuild airport node map
all_airport_nodes = {}
for n in merged_nodes:
    if n["type"] == "airport":
        all_airport_nodes[n["name"]] = n["node_id"]

ALGIERS_AIRPORT = "Aéroport d'Alger (Houari Boumediene)"
algiers_aid = all_airport_nodes.get(ALGIERS_AIRPORT)

DOMESTIC_FLIGHT_DEST = list(NEW_AIRPORTS.keys())

FLIGHT_SPEED_KMPH = 800

flight_edges = []
flight_destinations = DOMESTIC_FLIGHT_DEST + list(INTERNATIONAL_AIRPORTS.keys())

for dname in flight_destinations:
    daid = all_airport_nodes.get(dname)
    if not algiers_aid or not daid:
        continue
    ds = None
    for s in [n for n in merged_nodes if n.get("node_id") == daid]:
        ds = s
        break
    al = [n for n in merged_nodes if n.get("node_id") == algiers_aid]
    if not ds or not al:
        continue
    dlat = ds["latitude"]
    dlng = ds["longitude"]
    alat = al[0]["latitude"]
    alng = al[0]["longitude"]
    dist = haversine_km(alat, alng, dlat, dlng)
    duration = max(30, round(dist / FLIGHT_SPEED_KMPH * 60))
    for direction, f, t in [("forward", algiers_aid, daid), ("backward", daid, algiers_aid)]:
        flight_edges.append({
            "edge_id": make_edge_id(f, t, "EDGE_FLIGHT"),
            "from_node_id": f,
            "to_node_id": t,
            "line_name": f"Alger → {dname}",
            "line_id": "FLIGHT_AH",
            "operator": "Air Algérie",
            "mode": "flight",
            "subtype": "intercity",
            "distance_km": round(dist, 1),
            "duration_min": duration,
            "stops_between": 0,
            "direction": direction,
            "schedule": [],
            "pricing": {},
            "frequency_min": 1440,
            "metadata": {},
        })

print(f"Added {len(flight_edges)} flight edges ({len(DOMESTIC_FLIGHT_DEST)} domestic + {len(INTERNATIONAL_AIRPORTS)} intl destinations)")

# ---------------------------------------------------------------------------
# 10.  Build proper SNTF lines from seed data
# ---------------------------------------------------------------------------

# Build name->node_id map for train stations
train_node_map = {}
for n in merged_nodes:
    if n["type"] == "train":
        train_node_map[normalize_station_name(n["name"])] = n["node_id"]

sntf_line_edges = []
line_edge_count = 0

for line in sntf_seed["lines"]:
    stops = line["stops"]
    line_name = line["name"]
    line_op = line.get("operator", "SNTF")
    dist_total = line.get("distance_km")
    fare1 = line.get("estimated_fare_1ere_dzd")
    fare2 = line.get("estimated_fare_2eme_dzd")

    for i in range(len(stops) - 1):
        fn = normalize_station_name(stops[i])
        tn = normalize_station_name(stops[i + 1])
        fid = train_node_map.get(fn)
        tid = train_node_map.get(tn)
        if not fid or not tid:
            continue

        # Estimate distance from coordinates
        fn_node = next((n for n in merged_nodes if n.get("node_id") == fid), None)
        tn_node = next((n for n in merged_nodes if n.get("node_id") == tid), None)
        if fn_node and tn_node:
            dist = haversine_km(fn_node["latitude"], fn_node["longitude"],
                                tn_node["latitude"], tn_node["longitude"])
            duration = round(dist / 0.8)
        else:
            dist = dist_total / max(len(stops) - 1, 1) if dist_total else 0
            duration = round(dist / 0.8)

        for direction, f, t in [("forward", fid, tid), ("backward", tid, fid)]:
            eid = make_edge_id(f, t, "EDGE_SNTF")
            sntf_line_edges.append({
                "edge_id": eid,
                "from_node_id": f,
                "to_node_id": t,
                "line_name": line_name,
                "line_id": f"SNTF_{line_name[:20].replace(' ', '_')}",
                "operator": line_op,
                "mode": "train",
                "subtype": line.get("mode", "intercity"),
                "distance_km": round(dist, 2),
                "duration_min": duration,
                "stops_between": 0,
                "direction": direction,
                "schedule": [{"departure": "06:00", "arrival": "23:00", "train_num": f"SNTF_{line_name[:10]}", "days": "daily"}],
                "pricing": {"first_class": fare1, "second_class": fare2} if fare1 else {},
                "frequency_min": None,
                "metadata": {},
            })
            line_edge_count += 1

print(f"Built {line_edge_count} SNTF line edges from {len(sntf_seed['lines'])} line definitions")

# Also add banlieue edges
for bl in sntf_enriched.get("banlieue_lines", []):
    stops = bl["stops"]
    line_name = bl["name"]
    for i in range(len(stops) - 1):
        fn = normalize_station_name(stops[i])
        tn = normalize_station_name(stops[i + 1])
        fid = train_node_map.get(fn)
        tid = train_node_map.get(tn)
        if not fid or not tid:
            continue
        fn_node = next((n for n in merged_nodes if n.get("node_id") == fid), None)
        tn_node = next((n for n in merged_nodes if n.get("node_id") == tid), None)
        if fn_node and tn_node:
            dist = haversine_km(fn_node["latitude"], fn_node["longitude"],
                                tn_node["latitude"], tn_node["longitude"])
            duration = round(dist / 0.6)
        else:
            dist = 0
            duration = 0
        for direction, f, t in [("forward", fid, tid), ("backward", tid, fid)]:
            sntf_line_edges.append({
                "edge_id": make_edge_id(f, t, "EDGE_BANLIEUE"),
                "from_node_id": f,
                "to_node_id": t,
                "line_name": line_name,
                "line_id": f"BANLIEUE_{line_name[:20].replace(' ', '_')}",
                "operator": "SNTF",
                "mode": "train",
                "subtype": "suburban",
                "distance_km": round(dist, 2),
                "duration_min": duration,
                "stops_between": 0,
                "direction": direction,
                "schedule": [],
                "pricing": {},
                "frequency_min": 30,
                "metadata": {},
            })
            line_edge_count += 1

print(f"After banlieue: {line_edge_count} total SNTF edges")

# Update lines_at_station on train nodes
for edge in sntf_line_edges:
    for node in merged_nodes:
        if node["node_id"] == edge["from_node_id"] or node["node_id"] == edge["to_node_id"]:
            if edge["line_name"] not in node["lines_at_station"]:
                node["lines_at_station"].append(edge["line_name"])

# ---------------------------------------------------------------------------
# 11.  Add transfer edges between co-located stations
# ---------------------------------------------------------------------------

transfer_edges = []
transfer_threshold_km = 0.5  # 500m

print("\n--- Computing transfer edges (within 500m) ---")

for i in range(len(merged_nodes)):
    ni = merged_nodes[i]
    if not has_valid_coords(ni):
        continue
    for j in range(i + 1, len(merged_nodes)):
        nj = merged_nodes[j]
        if not has_valid_coords(nj):
            continue
        if ni["type"] == nj["type"]:
            continue
        dist = haversine_km(ni["latitude"], ni["longitude"],
                            nj["latitude"], nj["longitude"])
        if dist <= transfer_threshold_km:
            eid = make_edge_id(ni["node_id"], nj["node_id"], "EDGE_TRANSFER")
            transfer_edges.append({
                "edge_id": eid,
                "from_node_id": ni["node_id"],
                "to_node_id": nj["node_id"],
                "line_name": "Transfert (correspondance)",
                "line_id": "TRANSFER",
                "operator": "",
                "mode": "transfer",
                "subtype": "walk",
                "distance_km": round(dist, 3),
                "duration_min": max(1, round(dist / 0.083)),
                "stops_between": 0,
                "direction": "bidirectional",
                "schedule": [],
                "pricing": {},
                "frequency_min": None,
                "metadata": {},
            })

print(f"Found {len(transfer_edges)} transfer edges")

# ---------------------------------------------------------------------------
# 12.  Ensure wilaya_id on all nodes
# ---------------------------------------------------------------------------

wilaya_fixes = 0
for node in merged_nodes:
    old_w = node.get("wilaya_id")
    new_w = ensure_wilaya(node)
    if old_w != new_w and (old_w is None or old_w == "" or old_w == 0):
        node["wilaya_id"] = new_w
        wilaya_fixes += 1

print(f"Fixed wilaya_id for {wilaya_fixes} nodes")

# ---------------------------------------------------------------------------
# 13.  Build final edges list
# ---------------------------------------------------------------------------

all_edges = list(scraper_edges) + cable_car_edges + ferry_edges + flight_edges + sntf_line_edges + transfer_edges

# Deduplicate edges by from+to+direction+mode
edge_seen = {}
deduped_edges = []
dupe_edge_count = 0
for e in all_edges:
    key = (e["from_node_id"], e["to_node_id"], e.get("direction", "forward"), e.get("mode", ""))
    if key in edge_seen:
        dupe_edge_count += 1
        continue
    edge_seen[key] = True
    deduped_edges.append(e)

print(f"Deduplicated edges: {dupe_edge_count} dupes removed, {len(deduped_edges)} remaining")

# ---------------------------------------------------------------------------
# 14.  Sort and count
# ---------------------------------------------------------------------------

# Sort nodes by type then name
merged_nodes.sort(key=lambda n: (n["type"], n["name"]))

# Count by type
type_counts = {}
for n in merged_nodes:
    t = n["type"]
    type_counts[t] = type_counts.get(t, 0) + 1

# Count edges by type
edge_type_counts = {}
for e in deduped_edges:
    t = e.get("mode", "unknown")
    edge_type_counts[t] = edge_type_counts.get(t, 0) + 1

# ---------------------------------------------------------------------------
# 15.  Write output
# ---------------------------------------------------------------------------

output_nodes_path = os.path.join(DATA_DIR, "transit_nodes_enriched.json")
output_edges_path = os.path.join(DATA_DIR, "transit_edges_enriched.json")

with open(output_nodes_path, "w") as f:
    json.dump(merged_nodes, f, indent=2, ensure_ascii=False)
print(f"\nWritten: {output_nodes_path}")

with open(output_edges_path, "w") as f:
    json.dump(deduped_edges, f, indent=2, ensure_ascii=False)
print(f"Written: {output_edges_path}")

# ---------------------------------------------------------------------------
# 16.  Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("ENRICHMENT SUMMARY")
print("=" * 60)
print(f"\nTotal nodes: {len(merged_nodes)}")
print(f"  Breakdown by type:")
for t in sorted(type_counts.keys()):
    print(f"    {t}: {type_counts[t]}")
print(f"\nTotal edges: {len(deduped_edges)}")
print(f"  Breakdown by mode:")
for t in sorted(edge_type_counts.keys()):
    print(f"    {t}: {edge_type_counts[t]}")
print(f"\nOSM Nominatim requests: {osm_requests}")
print(f"  Stations geocoded successfully: {geocoded_count}")
print(f"  Failed: {osm_requests - geocoded_count}")
print(f"\nWilaya IDs fixed: {wilaya_fixes}")
print(f"Cable car stations: {len(cable_car_nodes)}")
print(f"Taxi stations: {len(taxi_nodes)}")
print(f"Ferry ports added: {len(ferry_nodes_added)}")
print(f"Airport nodes added: {len(airport_nodes_added)}")
print(f"Transfer edges: {len(transfer_edges)}")
print(f"SNTF line edges built: {line_edge_count}")
print(f"\nDone.")
