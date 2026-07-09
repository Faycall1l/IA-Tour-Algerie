#!/usr/bin/env python3
"""Generate walking transfer edges between nearby transit nodes.

Connects nearby stops within cities to enable multimodal routing:
- bus ↔ bus (within 100m)
- bus ↔ tram/train/metro/cablecar/ferry (within 200m)
- tram ↔ tram (within 150m)
- train ↔ train (within 300m)
- Any ↔ any within same transit hub (within 80m)

Usage:
  python scripts/data/generate_walking_transfers.py
"""

import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"

WALK_SPEED_KPH = 5.0

CONNECTION_RANGES = {
    ("bus", "bus"): 0.10,
    ("bus", "tram"): 0.20,
    ("bus", "train"): 0.30,
    ("bus", "metro"): 0.30,
    ("bus", "cablecar"): 0.20,
    ("bus", "ferry"): 0.30,
    ("tram", "tram"): 0.15,
    ("tram", "train"): 0.30,
    ("tram", "metro"): 0.30,
    ("tram", "cablecar"): 0.20,
    ("traim", "ferry"): 0.30,
    ("train", "train"): 0.30,
    ("train", "metro"): 0.50,
    ("train", "cablecar"): 0.30,
    ("train", "ferry"): 0.50,
    ("metro", "metro"): 0.15,
    ("metro", "cablecar"): 0.20,
    ("metro", "ferry"): 0.30,
    ("cablecar", "cablecar"): 0.10,
    ("cablecar", "ferry"): 0.30,
    ("ferry", "ferry"): 0.10,
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def make_transfer_id(nid_a, nid_b, idx=0):
    raw = f"TRANSFER_{nid_a[-16:]}_{nid_b[-16:]}_{idx}"
    return raw.upper()


def build_grid_index(nodes):
    grid = defaultdict(list)
    for n in nodes:
        lat = n.get("latitude")
        lon = n.get("longitude")
        if lat is None or lon is None:
            continue
        gx = int(lon / 0.01)
        gy = int(lat / 0.01)
        grid[(gx, gy)].append(n)
    return grid


def get_range(t1, t2):
    key = (t1, t2)
    if key not in CONNECTION_RANGES:
        key = (t2, t1)
    return CONNECTION_RANGES.get(key, 0.10)


def main():
    with open(NODES_PATH) as f:
        nodes = json.load(f)
    with open(EDGES_PATH) as f:
        edges = json.load(f)

    existing_keys = {
        (e["from_node_id"], e["to_node_id"])
        for e in edges if e.get("mode") == "transfer"
    }

    grid = build_grid_index(nodes)
    node_map = {n["node_id"]: n for n in nodes}

    new_edges = []
    checked_pairs = set()

    for (gx, gy), cell_nodes in grid.items():
        nearby_cells = [(gx + dx, gy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        nearby_nodes = []
        for nc in nearby_cells:
            nearby_nodes.extend(grid.get(nc, []))

        for i in range(len(cell_nodes)):
            a = cell_nodes[i]
            nid_a = a["node_id"]
            lat_a = a.get("latitude")
            lon_a = a.get("longitude")
            if lat_a is None:
                continue
            type_a = a.get("type", "")

            for b in nearby_nodes:
                nid_b = b["node_id"]
                if nid_a >= nid_b:
                    continue
                pair_key = (nid_a, nid_b)
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)

                if (nid_a, nid_b) in existing_keys or (nid_b, nid_a) in existing_keys:
                    continue

                lat_b = b.get("latitude")
                lon_b = b.get("longitude")
                if lat_b is None:
                    continue
                type_b = b.get("type", "")

                max_dist = get_range(type_a, type_b)
                dist = haversine_km(lat_a, lon_a, lat_b, lon_b)
                if dist > max_dist:
                    continue

                dur = max(1, int(dist / WALK_SPEED_KPH * 60))

                for f, t in [(nid_a, nid_b), (nid_b, nid_a)]:
                    eid = make_transfer_id(f, t, len(new_edges))
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
                    })

    if new_edges:
        edges.extend(new_edges)
        EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))

    print(f"Generated {len(new_edges)} new walking transfer edges")
    print(f"Total edges: {len(edges)}")


if __name__ == "__main__":
    main()
