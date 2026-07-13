#!/usr/bin/env python3
"""Generate walking transfer edges for transit nodes missing them.

Connects transit nodes without walking edges to nearest POIs (500m) and
nearest transit nodes (1km). Also connects transit-to-transit for same-city stops.
"""

import json
import math

DATA_DIR = "app/data"
MAX_WALK_POI_KM = 0.5
MAX_WALK_TRANSIT_KM = 1.0
WALK_SPEED_KMH = 5.0


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))


def main():
    nodes_path = f"{DATA_DIR}/transit_nodes_enriched.json"
    edges_path = f"{DATA_DIR}/transit_edges_enriched.json"

    with open(nodes_path) as f:
        nodes = json.load(f)
    with open(edges_path) as f:
        edges = json.load(f)

    # Build walking edge index
    walk_connected = set()
    for e in edges:
        if e.get('mode') == 'transfer':
            walk_connected.add(e['from_node_id'])
            walk_connected.add(e['to_node_id'])

    # Separate POI and transit nodes (with coordinates)
    all_with_coords = []  # (nid, lat, lon)
    transit_missing = []  # (nid, lat, lon, type)
    for n in nodes:
        nid = n.get('node_id', '')
        lat = n.get('latitude')
        lon = n.get('longitude')
        if lat is None or lon is None:
            continue
        all_with_coords.append((nid, lat, lon))
        if n.get('type') != 'poi' and nid not in walk_connected:
            transit_missing.append((nid, lat, lon, n.get('type', '')))

    # Build spatial grid (0.005 deg ~500m)
    grid = {}
    for nid, lat, lon in all_with_coords:
        gx = round(lon, 2)
        gy = round(lat, 2)
        grid.setdefault((gx, gy), []).append((nid, lat, lon))

    print(f"All nodes: {len(all_with_coords)}, Transit missing walks: {len(transit_missing)}")

    new_edges = []
    new_edge_ids = {e['edge_id'] for e in edges}
    still_missing = 0
    connected_now = 0

    for nid, lat, lon, ntype in transit_missing:
        # Search nearby cells
        candidates = []
        for dx in (-0.01, 0, 0.01):
            for dy in (-0.01, 0, 0.01):
                cell = grid.get((round(round(lon, 2) + dx, 2), round(round(lat, 2) + dy, 2)), [])
                candidates.extend(cell)

        # Filter and score by distance
        poi_conns = []
        transit_conns = []
        for cid, clat, clon in candidates:
            if cid == nid:
                continue
            d = haversine_km(lat, lon, clat, clon)
            dur = max(1, round(d / WALK_SPEED_KMH * 60))
            if d <= MAX_WALK_POI_KM:
                poi_conns.append((cid, d, dur))
            elif d <= MAX_WALK_TRANSIT_KM:
                transit_conns.append((cid, d, dur))

        # Prioritize POI connections, then transit connections
        poi_conns.sort(key=lambda x: x[1])
        transit_conns.sort(key=lambda x: x[1])

        connections = poi_conns[:3] + transit_conns[:2]

        if not connections:
            still_missing += 1
            continue

        for cid, dist, dur in connections:
            eid1 = f"EDGE_TRANSFER_WALK_{nid}_{cid}"
            eid2 = f"EDGE_TRANSFER_WALK_{cid}_{nid}"

            if eid1 not in new_edge_ids:
                new_edges.append({
                    "edge_id": eid1,
                    "from_node_id": nid,
                    "to_node_id": cid,
                    "mode": "transfer",
                    "subtype": "walking",
                    "operator": "N/A",
                    "distance_km": round(dist, 3),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 0,
                    "pricing": {"single": 0},
                    "schedule": {"start": "00:00", "end": "23:59", "frequency_min": 0,
                                 "days": ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]},
                })
                new_edge_ids.add(eid1)

            if eid2 not in new_edge_ids:
                new_edges.append({
                    "edge_id": eid2,
                    "from_node_id": cid,
                    "to_node_id": nid,
                    "mode": "transfer",
                    "subtype": "walking",
                    "operator": "N/A",
                    "distance_km": round(dist, 3),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 0,
                    "pricing": {"single": 0},
                    "schedule": {"start": "00:00", "end": "23:59", "frequency_min": 0,
                                 "days": ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]},
                })
                new_edge_ids.add(eid2)
            connected_now += 1

    print(f"New walking edges: {len(new_edges)}")
    print(f"Transit nodes connected: {connected_now}")
    print(f"Still missing walks: {still_missing}")

    # For the still-missing nodes, try a wider search (2km) connecting to ANY node
    if still_missing > 0:
        print(f"\n--- Wide search for {still_missing} remaining nodes ---")
        for nid, lat, lon, ntype in transit_missing:
            # Check if already connected
            if nid in new_edge_ids or nid in walk_connected:
                continue

            # Wider grid search
            candidates = []
            for dx in (-0.05, -0.03, 0, 0.03, 0.05):
                for dy in (-0.05, -0.03, 0, 0.03, 0.05):
                    cell = grid.get((round(round(lon, 2) + dx, 2), round(round(lat, 2) + dy, 2)), [])
                    candidates.extend(cell)

            best = None
            best_dist = float('inf')
            for cid, clat, clon in candidates:
                if cid == nid:
                    continue
                d = haversine_km(lat, lon, clat, clon)
                if d < best_dist and d <= 3.0:
                    best_dist = d
                    best = (cid, clat, clon)

            if best:
                cid, clat, clon = best
                dur = max(1, round(best_dist / WALK_SPEED_KMH * 60))
                for eid, f_id, t_id in [
                    (f"EDGE_TRANSFER_WALK_{nid}_{cid}", nid, cid),
                    (f"EDGE_TRANSFER_WALK_{cid}_{nid}", cid, nid),
                ]:
                    if eid not in new_edge_ids:
                        new_edges.append({
                            "edge_id": eid,
                            "from_node_id": f_id,
                            "to_node_id": t_id,
                            "mode": "transfer",
                            "subtype": "walking",
                            "operator": "N/A",
                            "distance_km": round(best_dist, 3),
                            "duration_min": dur,
                            "stops_between": 0,
                            "frequency_min": 0,
                            "pricing": {"single": 0},
                            "schedule": {"start": "00:00", "end": "23:59", "frequency_min": 0,
                                         "days": ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]},
                        })
                        new_edge_ids.add(eid)

    print(f"\nTotal new edges after wide search: {len(new_edges)}")

    if new_edges:
        edges.extend(new_edges)
        with open(edges_path, 'w') as f:
            json.dump(edges, f, ensure_ascii=False, indent=2)
        print(f"Saved! Total edges: {len(edges)}")


if __name__ == "__main__":
    main()
