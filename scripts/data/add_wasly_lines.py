#!/usr/bin/env python3
"""Scrape Wasly.app for transit line data (cable cars + tram stations) and merge into enriched graph.

Adds:
  - Cable cars: Tlemcen (3 stn), Blida (3 stn), Tizi Ouzou (4 stn), Annaba (2 stn)
  - Tram: improved station-level data for Setif, SBA, Mostaganem, Ouargla

Usage:
  python scripts/data/add_wasly_lines.py
"""

import hashlib
import json
import math
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"
CACHE_PATH = ROOT / "tmp" / "wasly_geocode_cache.json"

CABLE_CAR_SPEED = 7.0  # km/h (cable car slow speed)
TRAM_SPEED = 20.0
ROAD_FACTOR = 1.0  # cable cars and trams follow their line directly

OSM_USER_AGENT = "ATHAR-TransitGraph/1.0 (wasly scraper)"

# ---------------------------------------------------------------------------
# Cable car data from Wasly
# ---------------------------------------------------------------------------

CABLE_CAR_LINES = [
    {
        "name": "Télécabine de Tlemcen",
        "line_id": "CABLECAR_TLE",
        "city": "Tlemcen",
        "wilaya_id": 13,
        "operator": "ETAC",
        "price": 50,
        "frequency_min": 3,
        "stations": ["Station Grand Bassin", "Station Boulevard de l'ALN", "Station Lalla Setti"],
        "first_departure": "07:00",
        "last_departure": "19:00",
    },
    {
        "name": "Télécabine de Blida",
        "line_id": "CABLECAR_BLI",
        "city": "Blida",
        "wilaya_id": 9,
        "operator": "ETAC",
        "price": 50,
        "frequency_min": 3,
        "stations": ["Station Blida", "Station Beni Ali", "Station Chréa"],
        "first_departure": "07:00",
        "last_departure": "19:00",
    },
    {
        "name": "Télécabine de Tizi-Ouzou",
        "line_id": "CABLECAR_TIZ",
        "city": "Tizi Ouzou",
        "wilaya_id": 15,
        "operator": "ETAC",
        "price": 50,
        "frequency_min": 3,
        "stations": ["Station La Wilaya", "Station Stade 1er Novembre", "Station Nouvelle Ville", "Station Kef Naadja"],
        "first_departure": "07:00",
        "last_departure": "19:00",
    },
    {
        "name": "Télécabine d'Annaba",
        "line_id": "CABLECAR_ANN",
        "city": "Annaba",
        "wilaya_id": 23,
        "operator": "ETAC",
        "price": 50,
        "frequency_min": 3,
        "stations": ["Station Annaba", "Station Séraïdi"],
        "first_departure": "07:00",
        "last_departure": "19:00",
    },
    {
        "name": "Télécabine de Constantine",
        "line_id": "CABLECAR_CON",
        "city": "Constantine",
        "wilaya_id": 25,
        "operator": "ETAC",
        "price": 30,
        "frequency_min": 2,
        "stations": ["Tatache Belkacem", "CHU Ben Badis", "Emir Abdelkader"],
        "first_departure": "06:00",
        "last_departure": "22:00",
    },
]

# ---------------------------------------------------------------------------
# Tram data from Wasly (stations in order)
# ---------------------------------------------------------------------------

TRAM_LINES = [
    {
        "name": "Tramway Sétif",
        "line_id": "TRAM_SET",
        "city": "Sétif",
        "wilaya_id": 19,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 8,
        "stations": [
            "11 Décembre 1960", "Bataille Guedil Ouled Tebben", "Bataille Helia Bousselam",
            "Djebel Mokresse Ain Abessa", "Larbi Ben M'hidi", "Didouche Mourad",
            "Rabah Bitat", "Krim Belkacem", "Mohamed Boudiaf",
            "Berarma Abdellah", "Belil Abdallah", "Djebel Boutaleb",
            "Mostafa Benboulaid", "Bouzid Saal", "Les Cinq Fusillés",
            "Les Frères Martyrs Djemli", "08 Mai 1945", "Said Boukhrissa",
            "Ferhat Abbas", "Tombeau Numide", "Fatma Djaballah",
            "Benchekribou Abdelaziz", "Berchi Abid",
        ],
        "first_departure": "05:30",
        "last_departure": "22:30",
    },
    {
        "name": "Tramway Sidi Bel Abbès",
        "line_id": "TRAM_SBA",
        "city": "Sidi Bel Abbès",
        "wilaya_id": 22,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 8,
        "stations": [
            "Gare Routière Sud", "Jardin", "4 Horloges", "Émir Abdelkader",
            "Stade Adda Boudjelal", "Station Maternité", "La Radio", "Houari Boumediene",
            "La Daïra", "El Wiam", "Sidi Djilali", "AADL Benhamouda",
            "Gare Routière Nord", "Gare Ferroviaire", "Campus", "Centre Ennaâma",
            "Faculté de Droit", "L'Environnement", "Benhammouda", "Les Frères Adnane",
            "Gare Routière Est", "Cascade",
        ],
        "first_departure": "05:30",
        "last_departure": "22:30",
    },
    {
        "name": "Tramway Mostaganem L1",
        "line_id": "TRAM_MOS_L1",
        "city": "Mostaganem",
        "wilaya_id": 27,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 8,
        "stations": [
            "Karouba", "Institut d'Éducation Physique et Sportive", "Cité Universitaire Karouba",
            "Haï Es Salam", "Faculté de Médecine", "École de Protection Civile",
            "Cité Universitaire Benyahia Belkacem 2", "Cité Universitaire Benyahia Belkacem 1",
            "Tijditt", "Hôpital de Tijditt", "Armée de Libération Nationale", "Cité El Arsa",
            "Gare de Mostaganem SNTF", "Cité Khemisti", "Cité Cheikh Hamada",
            "Cité Gouaich Charef", "Cité Ben Djlidjel Kaddour", "Route du Port",
            "Cité Administrative", "La Salamandre",
        ],
        "first_departure": "05:30",
        "last_departure": "22:30",
    },
    {
        "name": "Tramway Mostaganem L2",
        "line_id": "TRAM_MOS_L2",
        "city": "Mostaganem",
        "wilaya_id": 27,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 10,
        "stations": [
            "Nouvelle Gare Routière", "Cité 5 Juillet 1962", "Cité Abane Ramdane",
            "Gare de Mostaganem SNTF",
        ],
        "first_departure": "05:30",
        "last_departure": "22:30",
    },
    {
        "name": "Tramway Ouargla",
        "line_id": "TRAM_OUA",
        "city": "Ouargla",
        "wilaya_id": 30,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 8,
        "stations": [
            "Sid Rouhou", "Colonel Sidiki Larbi", "Benabbas Hamadi", "Zoubidi Abdelkader",
            "Hassani Tayeb", "El Mekhadma", "Chatti El Oukal", "Cheikh Benattia Djelloul",
            "Allama Mohamed Ben Hadj Aïssa", "Temmam Ahmed", "Nouveau Pôle Universitaire",
            "Gare Multiservices", "27 Février 1962", "Safrani Abdelkader", "Khelil Abdelkader",
            "Chenine Kaddour",
        ],
        "first_departure": "05:30",
        "last_departure": "23:00",
    },
    {
        "name": "Tramway Constantine",
        "line_id": "TRAM_CON",
        "city": "Constantine",
        "wilaya_id": 25,
        "operator": "SETRAM",
        "price": 40,
        "frequency_min": 8,
        "stations": [
            "Ben Abdelmalek Ramdane", "Belle Vue", "Kadour Bouedous", "Emir Abdelkader",
            "Fadhila Saadane", "Zone Industrielle Palma", "Université Mentouri",
            "Résidence Universitaire Mentouri", "Cité Kheznadar", "Zouaghi", "Laifour",
            "Université Salah Boubnider", "19 Mai 1956", "08 Mai 1945",
            "Chahid Kadri Brahim", "Chouhada", "Cité El-Istiklal", "Ali Mendjeli",
            "Avenue de l'ALN", "Ennasr", "Université Abdelhamid Mehri",
        ],
        "first_departure": "05:30",
        "last_departure": "22:30",
    },
]


def make_node_id(name, ntype):
    safe = re.sub(r"[^a-zA-Z0-9]", "_", name).upper()
    return f"STATION_{ntype.upper()}_{safe}"


def make_edge_id(fid, tid, prefix):
    sf = fid.replace("STATION_", "").replace("_", "")
    st = tid.replace("STATION_", "").replace("_", "")
    return f"{prefix}_{sf}_{st}".upper()


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def osm_geocode(query, cache):
    """Geocode a station name via OSM Nominatim with caching."""
    cache_key = query.lower().strip()
    if cache_key in cache:
        return tuple(cache[cache_key])

    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "format": "json", "limit": 1, "q": query, "countrycodes": "dz"
    })
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": OSM_USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            if data and "lat" in data[0] and "lon" in data[0]:
                result = (float(data[0]["lat"]), float(data[0]["lon"]))
                cache[cache_key] = result
                return result
            print(f"    No results for: {query}")
            return (None, None)
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
                continue
            print(f"    Failed: {query} — {e}")
            return (None, None)


def process_line(line_def, is_tram, cache):
    """Process a single transit line: geocode stations, create nodes + edges."""
    mode = "tram" if is_tram else "cablecar"
    operator = line_def["operator"]
    line_id = line_def["line_id"]
    line_name = line_def["name"]
    price = line_def["price"]
    freq = line_def["frequency_min"]
    wilaya = line_def["wilaya_id"]
    first_dep = line_def["first_departure"]
    last_dep = line_def["last_departure"]
    speed = TRAM_SPEED if is_tram else CABLE_CAR_SPEED

    print(f"\n  {line_name} ({len(line_def['stations'])} stations)")

    # Geocode all stations
    coords = []
    for stn in line_def["stations"]:
        query = f"{stn}, {line_def['city']}, Algérie"
        lat, lng = osm_geocode(query, cache)
        if lat is None:
            # Fallback: try city center
            print(f"    Geocoding failed for {stn}, using city center fallback")
            lat, lng = osm_geocode(f"{line_def['city']}, Algérie", cache)
        coords.append((stn, lat, lng))
        time.sleep(1.1)

    # Create nodes
    nodes = []
    node_ids = []
    for stn, lat, lng in coords:
        if lat is None:
            continue
        nid = make_node_id(stn, mode)
        nodes.append({
            "node_id": nid,
            "name": stn,
            "name_ar": "",
            "name_en": stn,
            "type": mode,
            "subtype": "urban",
            "operator": operator,
            "wilaya_id": wilaya,
            "latitude": lat,
            "longitude": lng,
            "osm_data": {},
            "codes": {},
            "lines_at_station": [line_name],
            "has_parking": None,
            "has_accessibility": None,
            "metadata": {"source": "wasly", "line_id": line_id},
        })
        node_ids.append((nid, stn, lat, lng))

    # Create edges
    edges = []
    for i in range(len(node_ids) - 1):
        nid_a, name_a, lat_a, lng_a = node_ids[i]
        nid_b, name_b, lat_b, lng_b = node_ids[i + 1]
        dist = haversine_km(lat_a, lng_a, lat_b, lng_b)
        if dist < 0.05:
            continue
        duration = max(1, int(dist / speed * 60))

        for direction, f, t, dname in [
            ("forward", nid_a, nid_b, name_b),
            ("backward", nid_b, nid_a, name_a),
        ]:
            eid = make_edge_id(f, t, f"EDGE_{mode.upper()}")
            edges.append({
                "edge_id": eid,
                "from_node_id": f,
                "to_node_id": t,
                "mode": mode,
                "subtype": "urban",
                "operator": operator,
                "line_id": line_id,
                "line_name": line_name,
                "direction": direction,
                "distance_km": round(dist, 3),
                "duration_min": duration,
                "stops_between": 0,
                "frequency_min": freq,
                "pricing": {"single": price},
                "schedule": {
                    "first_departure": first_dep,
                    "last_departure": last_dep,
                    "frequency_min": freq,
                    "operating_days": [
                        "Monday", "Tuesday", "Wednesday", "Thursday",
                        "Friday", "Saturday", "Sunday"
                    ],
                    "destination": dname,
                },
                "metadata": {"source": "wasly", "line_id": line_id},
            })

    print(f"    {len(nodes)} nodes, {len(edges)} edges")
    return nodes, edges


def main():
    print("=" * 60)
    print("Adding transit lines from Wasly.app")
    print("=" * 60)

    # Load geocode cache
    cache_path = CACHE_PATH
    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())
    print(f"Geocode cache: {len(cache)} entries")

    all_new_nodes = []
    all_new_edges = []

    # Process cable car lines
    print("\n--- Cable cars ---")
    for line_def in CABLE_CAR_LINES:
        nodes, edges = process_line(line_def, is_tram=False, cache=cache)
        all_new_nodes.extend(nodes)
        all_new_edges.extend(edges)

    # Process tram lines
    print("\n--- Tram lines ---")
    for line_def in TRAM_LINES:
        nodes, edges = process_line(line_def, is_tram=True, cache=cache)
        all_new_nodes.extend(nodes)
        all_new_edges.extend(edges)

    # Save cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))
    print(f"\nGeocode cache saved: {len(cache)} entries")

    # Merge with existing
    print(f"\n{'=' * 60}")
    print(f"New: {len(all_new_nodes)} nodes, {len(all_new_edges)} edges")
    print(f"{'=' * 60}")

    merge_with_existing(all_new_nodes, all_new_edges)


def merge_with_existing(new_nodes, new_edges):
    nodes = json.loads(NODES_PATH.read_text())
    edges = json.loads(EDGES_PATH.read_text())

    existing_node_ids = {n["node_id"] for n in nodes}
    existing_edge_keys = {
        (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
        for e in edges
    }

    merged_nodes = nodes[:]
    merged_edges = edges[:]
    nodes_merged = 0
    edges_merged = 0

    for n in new_nodes:
        if n["node_id"] not in existing_node_ids:
            merged_nodes.append(n)
            nodes_merged += 1

    for e in new_edges:
        key = (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
        if key not in existing_edge_keys:
            merged_edges.append(e)
            edges_merged += 1

    print(f"Merged: {nodes_merged} new nodes, {edges_merged} new edges")
    print(f"Total nodes: {len(merged_nodes)}, Total edges: {len(merged_edges)}")

    NODES_PATH.write_text(json.dumps(merged_nodes, ensure_ascii=False, indent=2))
    EDGES_PATH.write_text(json.dumps(merged_edges, ensure_ascii=False, indent=2))
    print(f"Saved.")


if __name__ == "__main__":
    main()
