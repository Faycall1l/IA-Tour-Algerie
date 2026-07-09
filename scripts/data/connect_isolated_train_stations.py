#!/usr/bin/env python3
"""Connect isolated train stations to their nearest connected neighbor.

Creates direct SNTF train edges for stations that have no connections.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"

TRAIN_SPEED = 60


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

connected = set()
for e in edges:
    connected.add(e["from_node_id"])
    connected.add(e["to_node_id"])

existing_keys = {
    (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
    for e in edges
}

train_nodes = [n for n in nodes if n.get("type") == "train"]
connected_train = [n for n in train_nodes if n["node_id"] in connected]
connected_set = {n["node_id"] for n in connected_train}

new_edges = []

for n in train_nodes:
    if n["node_id"] in connected_set:
        continue
    lat_a = n.get("latitude")
    lon_a = n.get("longitude")
    if lat_a is None:
        continue

    best_dist = float("inf")
    best = None
    for nc in connected_train:
        d = haversine_km(lat_a, lon_a, nc["latitude"], nc["longitude"])
        if d < best_dist:
            best_dist = d
            best = nc

    if best and best_dist < 150:
        dur = max(2, int(best_dist / TRAIN_SPEED * 60))
        for direction, f, t in [
            ("forward", n["node_id"], best["node_id"]),
            ("backward", best["node_id"], n["node_id"]),
        ]:
            eid = f"EDGE_TRAIN_CONN_{f[-12:]}_{t[-12:]}".upper()
            key = (f, t, f"SNTF_{best['name']}_{n['name']}", direction)
            if key not in existing_keys:
                new_edges.append({
                    "edge_id": eid,
                    "from_node_id": f,
                    "to_node_id": t,
                    "mode": "train",
                    "subtype": "intercity",
                    "operator": "SNTF",
                    "line_id": f"SNTF_{best['name']}_{n['name']}",
                    "line_name": f"{best['name']} ↔ {n['name']}",
                    "direction": direction,
                    "distance_km": round(best_dist, 2),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 120,
                    "pricing": {"single": int(best_dist * 1.5)},
                })
                existing_keys.add(key)

if new_edges:
    edges.extend(new_edges)
    EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))

print(f"Connected {len([n for n in train_nodes if n['node_id'] not in connected_set])} isolated stations")
print(f"Generated {len(new_edges)} new train edges")
print(f"Total edges: {len(edges)}")
print(f"Total nodes: {len(nodes)}")
