#!/usr/bin/env python3
"""Add inter-city taxi edges + bus↔transit transfer edges.

Taxi: connects each taxi station to its 5 nearest neighboring taxi stations.
Transit: adds 500m walking transfers between new bus stops and metro/train/tram.

Usage:
  python scripts/data/add_taxi_edges.py
"""

import json
import math
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"

TAXI_SPEED_KPH = 80
TAXI_PRICE_PER_KM = 15
ROAD_FACTOR = 1.3
NEAREST_K = 5


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def make_edge_id(from_id: str, to_id: str, line: str) -> str:
    return f"EDGE_{line}_{from_id}_{to_id}".replace(" ", "_").upper()


def main():
    nodes = json.loads(NODES_PATH.read_text())
    edges = json.loads(EDGES_PATH.read_text())

    node_map = {n["node_id"]: n for n in nodes}

    # Collect taxi nodes with valid coords
    taxi_nodes = [
        n for n in nodes
        if n.get("type") == "taxi"
        and n.get("latitude") is not None
        and n.get("longitude") is not None
    ]
    print(f"Found {len(taxi_nodes)} taxi stations with valid coordinates")

    # Compute pairwise distances
    pairs = []
    for i in range(len(taxi_nodes)):
        ni = taxi_nodes[i]
        dists = []
        for j in range(len(taxi_nodes)):
            if i == j:
                continue
            nj = taxi_nodes[j]
            d = haversine_km(ni["latitude"], ni["longitude"], nj["latitude"], nj["longitude"])
            dists.append((d, nj))
        dists.sort(key=lambda x: x[0])
        pairs.append((ni, dists[:NEAREST_K]))

    # Build edge set (deduplicate)
    edge_key_set = set()
    existing_keys = set()
    for e in edges:
        existing_keys.add((e["from_node_id"], e["to_node_id"], e.get("mode"), e.get("line_id", "")))

    new_edges = []
    for src_node, neighbors in pairs:
        for orig_dist_km, dst_node in neighbors:
            if orig_dist_km < 0.1:
                continue
            road_km = round(orig_dist_km * ROAD_FACTOR, 2)
            duration_min = max(3, int(road_km / TAXI_SPEED_KPH * 60))

            line_id = "TAXI_INTER_CITY"
            edge_id_fwd = make_edge_id(src_node["node_id"], dst_node["node_id"], line_id)
            edge_key_fwd = (src_node["node_id"], dst_node["node_id"], "taxi", line_id)

            if edge_key_fwd not in existing_keys and edge_key_fwd not in edge_key_set:
                edge_key_set.add(edge_key_fwd)
                new_edges.append({
                    "edge_id": edge_id_fwd,
                    "from_node_id": src_node["node_id"],
                    "to_node_id": dst_node["node_id"],
                    "mode": "taxi",
                    "subtype": "intercity",
                    "operator": "Taxi",
                    "line_id": line_id,
                    "line_name": "Taxi Inter-Villes",
                    "direction": "forward",
                    "distance_km": road_km,
                    "duration_min": duration_min,
                    "stops_between": 0,
                    "frequency_min": 30,
                    "pricing": {
                        "per_km": TAXI_PRICE_PER_KM,
                        "estimated_total": int(road_km * TAXI_PRICE_PER_KM),
                    },
                    "schedule": {
                        "first_departure": "05:00",
                        "last_departure": "23:00",
                        "frequency_min": 30,
                        "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                        "destination": dst_node.get("name", ""),
                    },
                    "metadata": {"source": "generated"},
                })

            edge_key_bwd = (dst_node["node_id"], src_node["node_id"], "taxi", line_id)
            if edge_key_bwd not in existing_keys and edge_key_bwd not in edge_key_set:
                edge_id_bwd = make_edge_id(dst_node["node_id"], src_node["node_id"], line_id)
                edge_key_set.add(edge_key_bwd)
                new_edges.append({
                    "edge_id": edge_id_bwd,
                    "from_node_id": dst_node["node_id"],
                    "to_node_id": src_node["node_id"],
                    "mode": "taxi",
                    "subtype": "intercity",
                    "operator": "Taxi",
                    "line_id": line_id,
                    "line_name": "Taxi Inter-Villes",
                    "direction": "backward",
                    "distance_km": road_km,
                    "duration_min": duration_min,
                    "stops_between": 0,
                    "frequency_min": 30,
                    "pricing": {
                        "per_km": TAXI_PRICE_PER_KM,
                        "estimated_total": int(road_km * TAXI_PRICE_PER_KM),
                    },
                    "schedule": {
                        "first_departure": "05:00",
                        "last_departure": "23:00",
                        "frequency_min": 30,
                        "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                        "destination": src_node.get("name", ""),
                    },
                    "metadata": {"source": "generated"},
                })

    # Ensure connectivity: find disconnected components and connect nearest pair between them
    # Build adjacency from combined edges (existing + new)
    all_node_ids = {n["node_id"] for n in taxi_nodes}
    adj = defaultdict(set)
    for e in edges + new_edges:
        if e["from_node_id"] in all_node_ids and e["to_node_id"] in all_node_ids:
            adj[e["from_node_id"]].add(e["to_node_id"])
            adj[e["to_node_id"]].add(e["from_node_id"])

    visited = set()
    components = []
    for nid in all_node_ids:
        if nid in visited:
            continue
        stack = [nid]
        comp = set()
        while stack:
            cur = stack.pop()
            if cur in visited:
                continue
            visited.add(cur)
            comp.add(cur)
            for nb in adj.get(cur, set()):
                if nb not in visited:
                    stack.append(nb)
        components.append(comp)

    print(f"Components before connectivity fix: {len(components)}")

    while len(components) > 1:
        best_dist = float("inf")
        best_pair = None
        for i in range(len(components)):
            for j in range(i + 1, len(components)):
                for nid_a in components[i]:
                    na = node_map[nid_a]
                    for nid_b in components[j]:
                        nb = node_map[nid_b]
                        d = haversine_km(na["latitude"], na["longitude"], nb["latitude"], nb["longitude"])
                        if d < best_dist:
                            best_dist = d
                            best_pair = (nid_a, nid_b, na, nb)
        if best_pair is None or best_dist < 0.1:
            break
        nid_a, nid_b, na, nb = best_pair
        road_km = round(best_dist * ROAD_FACTOR, 2)
        duration_min = max(10, int(road_km / TAXI_SPEED_KPH * 60))
        line_id = "TAXI_INTER_CITY"

        edge_key_fwd = (nid_a, nid_b, "taxi", line_id)
        if edge_key_fwd not in existing_keys and edge_key_fwd not in edge_key_set:
            edge_key_set.add(edge_key_fwd)
            new_edges.append({
                "edge_id": make_edge_id(nid_a, nid_b, line_id),
                "from_node_id": nid_a,
                "to_node_id": nid_b,
                "mode": "taxi",
                "subtype": "intercity",
                "operator": "Taxi",
                "line_id": line_id,
                "line_name": "Taxi Inter-Villes",
                "direction": "forward",
                "distance_km": road_km,
                "duration_min": duration_min,
                "stops_between": 0,
                "frequency_min": 30,
                "pricing": {
                    "per_km": TAXI_PRICE_PER_KM,
                    "estimated_total": int(road_km * TAXI_PRICE_PER_KM),
                },
                "schedule": {
                    "first_departure": "05:00",
                    "last_departure": "23:00",
                    "frequency_min": 30,
                    "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "destination": nb.get("name", ""),
                },
                "metadata": {"source": "generated"},
            })
            adj[nid_a].add(nid_b)
            adj[nid_b].add(nid_a)

        edge_key_bwd = (nid_b, nid_a, "taxi", line_id)
        if edge_key_bwd not in existing_keys and edge_key_bwd not in edge_key_set:
            edge_key_set.add(edge_key_bwd)
            new_edges.append({
                "edge_id": make_edge_id(nid_b, nid_a, line_id),
                "from_node_id": nid_b,
                "to_node_id": nid_a,
                "mode": "taxi",
                "subtype": "intercity",
                "operator": "Taxi",
                "line_id": line_id,
                "line_name": "Taxi Inter-Villes",
                "direction": "backward",
                "distance_km": road_km,
                "duration_min": duration_min,
                "stops_between": 0,
                "frequency_min": 30,
                "pricing": {
                    "per_km": TAXI_PRICE_PER_KM,
                    "estimated_total": int(road_km * TAXI_PRICE_PER_KM),
                },
                "schedule": {
                    "first_departure": "05:00",
                    "last_departure": "23:00",
                    "frequency_min": 30,
                    "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "destination": na.get("name", ""),
                },
                "metadata": {"source": "generated"},
            })
            adj[nid_b].add(nid_a)

        # Recompute components
        visited.clear()
        components.clear()
        for nid in all_node_ids:
            if nid in visited:
                continue
            stack = [nid]
            comp = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                comp.add(cur)
                for nb in adj.get(cur, set()):
                    if nb not in visited:
                        stack.append(nb)
            components.append(comp)

    print(f"Components after connectivity fix: {len(components)}")
    print(f"Adding {len(new_edges)} new taxi edges")
    print(f"Edge total before: {len(edges)}")

    edges.extend(new_edges)

    print(f"Edge total after: {len(edges)}")

    # Write back
    EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))
    print(f"Wrote {EDGES_PATH}")


if __name__ == "__main__":
    main()
