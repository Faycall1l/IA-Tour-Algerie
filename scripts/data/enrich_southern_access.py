#!/usr/bin/env python3
"""Enrich southern Algeria transit access: airports ↔ cities, flight routes, SOGRAL gaps.

People reach southern resorts (Djanet, Tamanrasset, Ghardaïa, Timimoun, etc.)
via flights + ground transfers, intercity buses (SOGRAL), and shared taxis.
This script fills the gaps between these modes.

Adds:
  1. Walking/transfer edges from airports to nearest city node
  2. Missing domestic flight routes (Ouargla, In Salah, Touggourt, Sétif ↔ Algiers)
  3. Missing SOGRAL intercity routes to Timimoun, In Salah, Djanet
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


with open(NODES_PATH) as f:
    nodes = json.load(f)
with open(EDGES_PATH) as f:
    edges = json.load(f)

node_map = {n["node_id"]: n for n in nodes}

# Existing edge keys for dedup
existing_edge_keys = {
    (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
    for e in edges
}

new_edges = []

# ===================================================================
# 1. Airport → city transfer edges
# ===================================================================
airports = [n for n in nodes if n.get("type") == "airport"]

# Only connect domestic Algerian airports (skip European ones)
domestic_airport_codes = set()

for ap in airports:
    ap_id = ap["node_id"]
    lat_ap = ap.get("latitude")
    lon_ap = ap.get("longitude")
    if lat_ap is None:
        continue

    # Check if already has ground connections
    has_ground = any(
        e["from_node_id"] == ap_id or e["to_node_id"] == ap_id
        for e in edges if e.get("mode") not in ("flight",)
    )
    if has_ground:
        continue

    # Skip European airports
    ap_name = ap.get("name", "")
    european = ["Paris", "Marseille", "Lyon", "Nice", "Toulouse", "Istanbul"]
    if any(c in ap_name for c in european):
        continue

    # Find nearest city-center bus/train/taxi node in same wilaya
    wid = ap.get("wilaya_id")
    best_dist = float("inf")
    best_node = None
    for n in nodes:
        if n["node_id"] == ap_id:
            continue
        n_wid = n.get("wilaya_id")
        # Match same wilaya, or within 10 km
        lat_n = n.get("latitude")
        lon_n = n.get("longitude")
        if lat_n is None:
            continue
        d = haversine_km(lat_ap, lon_ap, lat_n, lon_n)
        if n_wid == wid and d < best_dist:
            best_dist = d
            best_node = n
        elif d < best_dist and d < 50:
            best_dist = d
            best_node = n

    if best_node and best_dist < 50:
        dur = max(1, int(best_dist / 5 * 60))
        for f, t in [(ap_id, best_node["node_id"]), (best_node["node_id"], ap_id)]:
            direction = "forward" if f == ap_id else "backward"
            key = (f, t, "AIRPORT_TRANSFER", direction)
            if key not in existing_edge_keys:
                eid = f"TRANSFER_AIRPORT_{ap_id[-12:]}_{best_node['node_id'][-12:]}".upper()
                new_edges.append({
                    "edge_id": eid,
                    "from_node_id": f,
                    "to_node_id": t,
                    "mode": "transfer",
                    "subtype": "walking",
                    "operator": None,
                    "line_id": "AIRPORT_TRANSFER",
                    "line_name": f"Navette aéroport",
                    "direction": direction,
                    "distance_km": round(best_dist, 2),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 30,
                    "pricing": {"single": 0},
                })
                existing_edge_keys.add(key)

# ===================================================================
# 2. Missing flight routes to/from Algiers
# ===================================================================
# Air Algérie domestic flights Algiers ↔ southern cities
MISSING_FLIGHTS = [
    ("Alger", "Ouargla"),
    ("Alger", "In Salah"),
    ("Alger", "Touggourt"),
    ("Alger", "Sétif"),
]

def find_airport(name):
    name_lower = name.lower()
    for n in airports:
        aname = n.get("name", "").lower()
        if name_lower in aname:
            return n
        # Try without accents/diacritics
        if name_lower.replace("é", "e").replace("è", "e") in aname.replace("é", "e").replace("è", "e"):
            return n
    return None

for origin_name, dest_name in MISSING_FLIGHTS:
    origin = find_airport(origin_name)
    dest = find_airport(dest_name)
    if not origin or not dest:
        continue
    lat_o, lon_o = origin.get("latitude"), origin.get("longitude")
    lat_d, lon_d = dest.get("latitude"), dest.get("longitude")
    if None in (lat_o, lon_o, lat_d, lon_d):
        continue
    dist = haversine_km(lat_o, lon_o, lat_d, lon_d)
    dur = int(dist / 800 * 60)

    for direction, f, t in [
        ("forward", origin["node_id"], dest["node_id"]),
        ("backward", dest["node_id"], origin["node_id"]),
    ]:
        key = (f, t, "AIR_ALGERIE_DOMESTIC", direction)
        if key not in existing_edge_keys:
            eid = f"FLIGHT_ALGERIE_{f[-12:]}_{t[-12:]}".upper()
            new_edges.append({
                "edge_id": eid,
                "from_node_id": f,
                "to_node_id": t,
                "mode": "flight",
                "subtype": "domestic",
                "operator": "Air Algérie",
                "line_id": "AIR_ALGERIE_DOMESTIC",
                "line_name": f"AH {origin_name} → {dest_name}",
                "direction": direction,
                "distance_km": round(dist, 1),
                "duration_min": dur,
                "stops_between": 0,
                "frequency_min": 1440,
                "pricing": {"single": 10000},
            })
            existing_edge_keys.add(key)

# ===================================================================
# 3. Missing SOGRAL bus routes to southern resorts
# ===================================================================
# Find existing SOGRAL bus station nodes
bus_stations = [n for n in nodes if "Gare Routière" in n.get("name", "")]

# Find or create missing southern bus stations
MISSING_SOUTHERN_STATIONS = [
    ("Timimoun", 49, 29.25, 0.23),
    ("In Salah", 51, 27.19, 2.46),
    ("Djanet", 54, 24.56, 9.48),
    ("Tindouf", 37, 27.67, -8.13),
]

def find_or_create_bus_station(city_name, wilaya_id, lat, lon):
    existing = next((n for n in bus_stations if city_name.lower() in n.get("name", "").lower()), None)
    if existing:
        return existing
    # Create new bus station node
    nid = f"STATION_BUS_SOGRAL_{city_name.upper().replace(' ', '_')}"
    # Check if it already exists (might have been added previously)
    existing_n = next((n for n in nodes if n["node_id"] == nid), None)
    if existing_n:
        return existing_n

    # Create a convenient hub node
    nid = f"STATION_BUS_SOGRAL_{city_name.upper().replace(' ', '_')}"
    node = {
        "node_id": nid,
        "name": f"Gare Routière de {city_name}",
        "name_ar": "",
        "name_en": f"Bus Station {city_name}",
        "type": "bus",
        "subtype": "intercity",
        "operator": "SOGRAL",
        "wilaya_id": wilaya_id,
        "wilaya_name": city_name,
        "latitude": lat,
        "longitude": lon,
        "osm_data": {},
        "codes": {},
        "lines_at_station": [],
        "has_parking": True,
        "has_accessibility": None,
        "metadata": {"source": "southern_enrichment", "city": city_name},
    }
    nodes.append(node)
    bus_stations.append(node)
    print(f"  Created new station: {node['name']}")
    return node

# Connect missing southern cities to existing SOGRAL hub
CONNECTIONS = {
    "Timimoun": ["Adrar", "Béchar", "Ghardaïa"],
    "In Salah": ["Tamanrasset", "Ghardaïa", "Adrar", "Ouargla"],
    "Djanet": ["Illizi", "Tamanrasset", "Ouargla"],
    "Tindouf": ["Béchar", "Adrar", "Tlemcen"],
}

for city_name, wilaya_id, lat, lon in MISSING_SOUTHERN_STATIONS:
    station = find_or_create_bus_station(city_name, wilaya_id, lat, lon)
    for neighbor_name in CONNECTIONS.get(city_name, []):
        neighbor = next((n for n in bus_stations if neighbor_name.lower() in n.get("name", "").lower()), None)
        if not neighbor:
            continue
        d = haversine_km(lat, lon, neighbor["latitude"], neighbor["longitude"])
        dur = int(d / 60 * 60)
        price = int(d * 1.5)
        for direction, f, t in [
            ("forward", station["node_id"], neighbor["node_id"]),
            ("backward", neighbor["node_id"], station["node_id"]),
        ]:
            key = (f, t, f"SOGRAL_{city_name}_{neighbor_name}", direction)
            if key not in existing_edge_keys:
                eid = f"EDGE_SOGRAL_{f[-12:]}_{t[-12:]}".upper()
                new_edges.append({
                    "edge_id": eid,
                    "from_node_id": f,
                    "to_node_id": t,
                    "mode": "bus",
                    "subtype": "intercity",
                    "operator": "SOGRAL",
                    "line_id": f"SOGRAL_{city_name}_{neighbor_name}",
                    "line_name": f"{city_name} ↔ {neighbor_name}",
                    "direction": direction,
                    "distance_km": round(d, 1),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 1440,
                    "pricing": {"single": price},
                })
                existing_edge_keys.add(key)

# Save
if new_edges:
    edges.extend(new_edges)

NODES_PATH.write_text(json.dumps(nodes, ensure_ascii=False, indent=2))
EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))

print(f"Added {len([e for e in new_edges if e['mode'] == 'transfer'])} airport transfer edges")
print(f"Added {len([e for e in new_edges if e['mode'] == 'flight'])} flight edges")
print(f"Added {len([e for e in new_edges if e['mode'] == 'bus'])} SOGRAL bus edges")
print(f"Total new edges: {len(new_edges)}")
print(f"Total nodes: {len(nodes)}, Total edges: {len(edges)}")

# List airport-city connections created
for e in new_edges:
    if e['mode'] == 'transfer':
        fn = node_map.get(e['from_node_id'], {}).get('name', e['from_node_id'])
        tn = node_map.get(e['to_node_id'], {}).get('name', e['to_node_id'])
        print(f"  {fn} ↔ {tn}")
