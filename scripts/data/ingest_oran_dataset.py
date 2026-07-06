#!/usr/bin/env python3
"""Ingest the Oran urban transport academic dataset from GitHub into the enriched transit graph.

Source: https://github.com/Reguieg-Seddik/dataset-transport-oran-algeria
34 bus lines + tram, ~600 georeferenced stops, CC-BY licensed.

Usage:
  python scripts/data/ingest_oran_dataset.py
"""

import csv
import hashlib
import io
import json
import math
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "app" / "data"
NODES_PATH = DATA_DIR / "transit_nodes_enriched.json"
EDGES_PATH = DATA_DIR / "transit_edges_enriched.json"

STOPS_URL = "https://raw.githubusercontent.com/Reguieg-Seddik/dataset-transport-oran-algeria/main/arrets_reviewed_terminus.csv"
LINES_URL = "https://raw.githubusercontent.com/Reguieg-Seddik/dataset-transport-oran-algeria/main/lignes_desc.csv"

BUS_SPEED_KPH = 25
TRAM_SPEED_KPH = 20
ROAD_FACTOR = 1.3
ORAN_WILAYA = 31

LINE_META_CACHE = {}


def fetch_csv(url):
    print(f"  Fetching {url}")
    resp = urllib.request.urlopen(url, timeout=30)
    content = resp.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


def make_station_id(name, stop_id):
    suffix = hashlib.md5(f"ORAN_{stop_id}_{name}".encode()).hexdigest()[:8].upper()
    return f"STATION_BUS_ORAN_{suffix}"


def make_edge_id(from_id, to_id, line_ref, direction):
    raw = f"EDGE_BUS_ORAN_{line_ref}_{from_id[-16:]}_{to_id[-16:]}_{direction}"
    return raw.upper().replace("-", "_")


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def build_stop_chain(stops, direction_type):
    """Build ordered stop list for a (line_id, direction) using arret_suiv_id links."""
    type_map = {v["arret_id"]: v for v in stops if v["arret_type"] == direction_type}

    incoming = defaultdict(list)
    for sid, s in type_map.items():
        nid = s["arret_suiv_id"]
        if nid and nid != sid:
            incoming[nid].append(sid)

    # Find heads: stop IDs not pointed to by any other stop in this direction
    heads = []
    for sid in type_map:
        if not incoming.get(sid):
            heads.append(sid)

    if not heads:
        # Fallback: use the terminus (type=0) if present
        termini = [v for v in stops if v["arret_type"] == "0"]
        if termini:
            heads = [termini[0]["arret_id"]]
        else:
            heads = [list(type_map.keys())[0]]

    # Walk the chain from each head
    chain = []
    visited = set()
    for head in heads:
        cur = head
        while cur and cur in type_map and cur not in visited:
            visited.add(cur)
            chain.append(type_map[cur])
            cur = type_map[cur]["arret_suiv_id"]

    return chain


def load_line_meta():
    """Load line metadata (name, pricing) from lignes_desc.csv."""
    rows = fetch_csv(LINES_URL)
    meta = {}
    for r in rows:
        lid = int(r["ligne_id"])
        meta[lid] = {
            "name": r["ligne_nom"],
            "from": r["ligne_depart"],
            "to": r["ligne_arrivee"],
            "price": int(r["cout"]),
            "is_tram": lid == 36,
        }
    return meta


def process():
    print("=" * 60)
    print("Ingesting Oran Urban Transport Dataset")
    print("=" * 60)

    stops_raw = fetch_csv(STOPS_URL)
    line_meta = load_line_meta()
    print(f"  Loaded {len(stops_raw)} stop rows, {len(line_meta)} line definitions")

    # Group stops by line_id
    stops_by_line = defaultdict(list)
    for s in stops_raw:
        lid = int(s["ligne_id"])
        stops_by_line[lid].append(s)

    node_registry = {}
    new_nodes = []
    new_edges = []
    edges_added = 0
    nodes_added = 0

    for lid in sorted(stops_by_line.keys()):
        line_stops = stops_by_line[lid]
        meta = line_meta.get(lid, {})
        line_name = meta.get("name", f"Line {lid}")
        line_price = meta.get("price", 20)
        is_tram = meta.get("is_tram", False)
        mode = "tram" if is_tram else "bus"
        operator = "SETRAM" if is_tram else "ETO"
        line_id = f"ORAN_{'TRAM' if is_tram else 'BUS'}_{line_name}"

        print(f"\n  Line {lid} ({line_name}): {len(line_stops)} stops, {mode}, {line_price} DZD")

        for direction_type, direction_label in [("1", "forward"), ("2", "backward")]:
            chain = build_stop_chain(line_stops, direction_type)
            if len(chain) < 2:
                continue

            # Create or reuse nodes
            chain_node_ids = []
            for s in chain:
                sid = s["arret_id"]
                name = s["arret_nom"]
                lat = float(s["arret_latitude"])
                lng = float(s["arret_longitude"])
                dedup_key = (name.strip().lower()[:30], round(lat, 4), round(lng, 4))

                if dedup_key in node_registry:
                    nid = node_registry[dedup_key]
                else:
                    nid = make_station_id(name, sid)
                    node_registry[dedup_key] = nid
                    new_nodes.append({
                        "node_id": nid,
                        "name": name,
                        "name_ar": "",
                        "name_en": "",
                        "type": mode,
                        "subtype": "urban",
                        "operator": operator,
                        "wilaya_id": ORAN_WILAYA,
                        "latitude": lat,
                        "longitude": lng,
                        "osm_data": {},
                        "codes": {},
                        "lines_at_station": [],
                        "has_parking": None,
                        "has_accessibility": None,
                        "metadata": {"source": "oran_dataset", "line_id": line_id},
                    })
                    nodes_added += 1

                chain_node_ids.append((nid, name, lat, lng))

            # Create edges between consecutive stops
            for i in range(len(chain_node_ids) - 1):
                nid_a, name_a, lat_a, lng_a = chain_node_ids[i]
                nid_b, name_b, lat_b, lng_b = chain_node_ids[i + 1]

                dist = haversine_km(lat_a, lng_a, lat_b, lng_b)
                if dist < 0.05:
                    continue
                road_dist = round(dist * ROAD_FACTOR, 2)
                speed = TRAM_SPEED_KPH if is_tram else BUS_SPEED_KPH
                duration = max(1, int(road_dist / speed * 60))

                eid = make_edge_id(nid_a, nid_b, line_id, direction_label)
                new_edges.append({
                    "edge_id": eid,
                    "from_node_id": nid_a,
                    "to_node_id": nid_b,
                    "mode": mode,
                    "subtype": "urban",
                    "operator": operator,
                    "line_id": line_id,
                    "line_name": line_name,
                    "direction": direction_label,
                    "distance_km": road_dist,
                    "duration_min": duration,
                    "stops_between": 0,
                    "frequency_min": 10 if is_tram else 15,
                    "pricing": {"single": line_price},
                    "schedule": {
                        "first_departure": "06:00",
                        "last_departure": "20:00",
                        "frequency_min": 10 if is_tram else 15,
                        "operating_days": [
                            "Monday", "Tuesday", "Wednesday", "Thursday",
                            "Friday", "Saturday", "Sunday"
                        ],
                        "destination": name_b,
                    },
                    "metadata": {"source": "oran_dataset", "line_id": line_id},
                })
                edges_added += 1

    print(f"\n{'=' * 60}")
    print(f"New nodes: {nodes_added}, New edges: {edges_added}")
    print(f"{'=' * 60}")

    # Merge with existing enriched data
    merge_with_existing(new_nodes, new_edges)


def merge_with_existing(new_nodes, new_edges):
    print("\nMerging with existing enriched data...")
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
    print(f"Saved to {NODES_PATH} and {EDGES_PATH}")


if __name__ == "__main__":
    process()
