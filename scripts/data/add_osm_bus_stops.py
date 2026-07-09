#!/usr/bin/env python3
"""Fetch bus stop nodes from OSM for major Algerian cities missing bus data.

Queries Overpass API for highway=bus_stop in each city area, adds stops as
bus-type nodes, and creates minimal walking connections to nearby transit.

Usage:
  python scripts/data/add_osm_bus_stops.py [--fetch]
"""

import hashlib
import json
import math
import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"
CACHE_DIR = ROOT / "tmp" / "osm_bus_stops"

OVERPOST_URL = "https://overpass-api.de/api/interpreter"
OSM_USER_AGENT = "ATHAR-TransitGraph/1.0 (bus stop enrichment)"

CITIES = [
    ("Constantine", 36.365, 6.6145, 16),
    ("Annaba", 36.9, 7.7667, 23),
    ("Blida", 36.47, 2.84, 9),
    ("Tlemcen", 34.8783, -1.315, 13),
    ("Béjaïa", 36.7509, 5.064, 6),
    ("Skikda", 36.8672, 6.9075, 21),
    ("Batna", 35.5553, 6.1736, 5),
    ("Biskra", 34.85, 5.7333, 7),
    ("Tébessa", 35.4039, 8.1194, 12),
    ("Médéa", 36.2642, 2.7539, 26),
    ("Djelfa", 34.65, 3.25, 17),
    ("M'Sila", 35.7058, 4.5411, 28),
    ("Laghouat", 33.8, 2.8833, 3),
    ("Guelma", 36.4619, 7.425, 24),
    ("Jijel", 36.8208, 5.7667, 18),
    ("Bordj Bou Arreridj", 36.0667, 4.7667, 34),
    ("Souk Ahras", 36.2864, 7.9511, 41),
    ("Mascara", 35.3972, 0.14, 29),
    ("Relizane", 35.7372, 0.5558, 48),
    ("Chlef", 36.165, 1.3311, 2),
    ("Bouira", 36.38, 3.9, 10),
    ("El Oued", 33.3689, 6.8592, 39),
    ("Saïda", 34.8333, 0.145, 20),
    ("Boumerdes", 36.7667, 3.4772, 35),
    ("Tizi Ouzou", 36.7167, 4.05, 15),
    ("Aïn Témouchent", 35.3, -1.14, 46),
    ("Tamanrasset", 22.785, 5.5228, 11),
    ("Adrar", 27.874, -0.286, 1),
    ("Sidi Bel Abbès", 35.194, -0.642, 22),
    ("Mostaganem", 35.93, 0.09, 27),
    ("Ouargla", 31.95, 5.33, 30),
    ("Sétif", 36.19, 5.41, 19),
]

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi",
    5: "Batna", 6: "Béjaïa", 7: "Biskra", 8: "Béchar",
    9: "Blida", 10: "Bouira", 11: "Tamanrasset", 12: "Tébessa",
    13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou", 16: "Algiers",
    17: "Djelfa", 18: "Jijel", 19: "Sétif", 20: "Saïda",
    21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba", 24: "Guelma",
    25: "Constantine", 26: "Médéa", 27: "Mostaganem", 28: "M'Sila",
    29: "Mascara", 30: "Ouargla", 31: "Oran", 32: "El Bayadh",
    33: "Illizi", 34: "Bordj Bou Arreridj", 35: "Boumerdes", 36: "El Tarf",
    37: "Tindouf", 38: "Tissemsilt", 39: "El Oued", 40: "Khenchela",
    41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Aïn Defla",
    45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa", 48: "Relizane",
    49: "Timimoun", 50: "Bordj Badji Mokhtar", 51: "Ouled Djellal",
    52: "Béni Abbès", 53: "In Salah", 54: "In Guezzam",
    55: "Touggourt", 56: "Djanet", 57: "El M'Ghair", 58: "El Meniaa",
}


def fetch_bus_stops(city_name, lat, lon, wilaya_id, radius_km=6):
    query = f"""
    [out:json][timeout:30];
    node["highway"="bus_stop"](around:{radius_km * 1000},{lat},{lon});
    out body;
    """
    data = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(OVERPOST_URL, data=data,
                                 headers={"User-Agent": OSM_USER_AGENT})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode())
                stops = []
                for el in result.get("elements", []):
                    tags = el.get("tags", {})
                    name = tags.get("name", "") or f"Arrêt {city_name}"
                    stops.append({
                        "osm_id": el["id"],
                        "name": name,
                        "lat": el["lat"],
                        "lon": el["lon"],
                    })
                return stops
        except Exception as e:
            if attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"    Retry {attempt + 1} after {wait}s: {e}")
                time.sleep(wait)
            else:
                print(f"    Error after 3 attempts: {e}")
                return []


def make_station_id(osm_id, city_name):
    raw = f"OSM_BUS_STOP_{osm_id}"
    return f"STN_{hashlib.md5(raw.encode()).hexdigest()[:12].upper()}"


def make_edge_id(nid_a, nid_b):
    raw = f"WALK_{nid_a[-16:]}_{nid_b[-16:]}".upper()
    return raw


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def download_all(fetch=True):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    results = {}
    for city_name, lat, lon, wilaya_id in CITIES:
        cache_file = CACHE_DIR / f"{city_name.lower().replace(' ', '_')}.json"
        if cache_file.exists() and not fetch:
            with open(cache_file) as f:
                stops = json.load(f)
            print(f"  {city_name}: {len(stops)} stops (cached)")
            results[city_name] = stops
            continue
        print(f"  {city_name}: fetching...", end="", flush=True)
        stops = fetch_bus_stops(city_name, lat, lon, wilaya_id)
        print(f" {len(stops)} stops")
        with open(cache_file, "w") as f:
            json.dump(stops, f, ensure_ascii=False)
        results[city_name] = stops
        time.sleep(5.0)
    return results


def merge_into_graph(results):
    with open(NODES_PATH) as f:
        nodes = json.load(f)
    with open(EDGES_PATH) as f:
        edges = json.load(f)

    existing_ids = {n["node_id"] for n in nodes}
    existing_edge_keys = {
        (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
        for e in edges
    }

    new_nodes = []
    new_edges = []
    osm_to_nid = {}

    for city_name, stops in results.items():
        if not stops:
            continue

        # Find wilaya from city name
        wilaya_id = None
        for cname, _, _, wid in CITIES:
            if cname == city_name:
                wilaya_id = wid
                break

        osm_to_nid.clear()
        city_nodes_created = 0

        # Create nodes for each stop
        for stop in stops:
            nid = make_station_id(stop["osm_id"], city_name)
            if nid in existing_ids:
                osm_to_nid[stop["osm_id"]] = nid
                continue
            name = stop["name"]
            if not name or name.strip() == "":
                name = f"Arrêt {city_name}"
            node = {
                "node_id": nid,
                "name": name,
                "name_ar": "",
                "name_en": name,
                "type": "bus",
                "subtype": "urban",
                "operator": None,
                "wilaya_id": wilaya_id,
                "wilaya_name": city_name,
                "latitude": stop["lat"],
                "longitude": stop["lon"],
                "osm_data": {"osm_id": stop["osm_id"]},
                "codes": {},
                "lines_at_station": [],
                "has_parking": None,
                "has_accessibility": None,
                "metadata": {"source": "osm_bus_stop", "city": city_name},
            }
            new_nodes.append(node)
            existing_ids.add(nid)
            osm_to_nid[stop["osm_id"]] = nid
            city_nodes_created += 1

        if city_nodes_created == 0:
            continue

        # Create a virtual city hub node
        city_lat = next(clat for cn, clat, _, _ in CITIES if cn == city_name)
        city_lon = next(clon for cn, _, clon, _ in CITIES if cn == city_name)
        hub_id = f"HUB_{city_name.upper().replace(' ', '_')}"
        if hub_id not in existing_ids:
            hub_node = {
                "node_id": hub_id,
                "name": city_name,
                "name_ar": "",
                "name_en": city_name,
                "type": "bus",
                "subtype": "urban",
                "operator": None,
                "wilaya_id": wilaya_id,
                "wilaya_name": city_name,
                "latitude": city_lat,
                "longitude": city_lon,
                "osm_data": {},
                "codes": {},
                "lines_at_station": [],
                "has_parking": None,
                "has_accessibility": None,
                "metadata": {"source": "city_hub", "city": city_name},
            }
            new_nodes.append(hub_node)
            existing_ids.add(hub_id)
        else:
            pass  # hub already exists

        # Connect each new bus stop to the hub
        for stop in stops:
            nid = osm_to_nid[stop["osm_id"]]
            if not nid:
                continue
            dist = haversine_km(stop["lat"], stop["lon"], city_lat, city_lon)
            dur = max(1, int(dist / 5 * 60))
            for f, t in [(nid, hub_id), (hub_id, nid)]:
                eid = make_edge_id(f, t)[:60]
                key = (f, t, "", "")
                if key not in existing_edge_keys:
                    new_edges.append({
                        "edge_id": eid,
                        "from_node_id": f,
                        "to_node_id": t,
                        "mode": "transfer",
                        "subtype": "walking",
                        "operator": None,
                        "line_id": None,
                        "line_name": None,
                        "direction": "forward",
                        "distance_km": round(dist, 3),
                        "duration_min": dur,
                        "stops_between": 0,
                        "frequency_min": None,
                        "pricing": {"single": 0},
                        "schedule": None,
                        "metadata": {"source": "city_hub_connection"},
                    })
                    existing_edge_keys.add(key)

    # Merge
    nodes.extend(new_nodes)
    edges.extend(new_edges)

    NODES_PATH.write_text(json.dumps(nodes, ensure_ascii=False, indent=2))
    EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))

    print(f"\nAdded: {len(new_nodes)} new nodes, {len(new_edges)} new edges")
    print(f"Total nodes: {len(nodes)}, Total edges: {len(edges)}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Add OSM bus stops for missing cities")
    parser.add_argument("--fetch", action="store_true", help="Fetch from Overpass API")
    args = parser.parse_args()

    print("=" * 60)
    print("Fetching bus stop nodes from OSM for missing cities")
    print("=" * 60)

    results = download_all(fetch=args.fetch)

    total_stops = sum(len(s) for s in results.values())
    print(f"\nTotal bus stops fetched: {total_stops}")

    merge_into_graph(results)


if __name__ == "__main__":
    main()
