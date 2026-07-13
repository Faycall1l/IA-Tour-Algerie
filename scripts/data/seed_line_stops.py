#!/usr/bin/env python3
"""Seed the line_stops table from the transit edges JSON.

Reconstructs stop sequences from forward edges for each transport line,
maps JSON nodes to DB station UUIDs, and populates line_stops with
ordering and distance data. Also creates pedestrian transfer lines
for walking connectivity.
"""

import json
import math
import uuid
from collections import defaultdict

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost", "port": 5432,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

DATA_DIR = "app/data"
WALK_MODE = "walking"
TRANSPORT_MODES = {"bus", "tram", "train", "metro", "cablecar", "taxi", "ferry", "flight"}
NON_ROUTABLE_MODES = {"transfer", "intercity"}  # handled separately


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))


def build_stop_sequence(forward_edges):
    """Reconstruct stop order from forward edges by topological sort."""
    if not forward_edges:
        return []

    successors = {}
    predecessors = {}
    for e in forward_edges:
        f = e['from_node_id']
        t = e['to_node_id']
        successors[f] = t
        predecessors[t] = f

    # Find start node (no predecessor among the edges' nodes)
    all_from = {e['from_node_id'] for e in forward_edges}
    all_to = {e['to_node_id'] for e in forward_edges}
    start_nodes = all_from - all_to

    if not start_nodes:
        # Fallback: cycle or disconnected — use a node as start
        start_nodes = {next(iter(all_from))}

    sequences = []
    for start in start_nodes:
        seq = [start]
        cur = start
        while cur in successors and successors[cur] not in seq:
            cur = successors[cur]
            seq.append(cur)
        sequences.append(seq)

    # Return the longest sequence
    sequences.sort(key=len, reverse=True)
    return sequences[0] if sequences else []


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Load JSON data
    with open(f"{DATA_DIR}/transit_nodes_enriched.json") as f:
        nodes = json.load(f)
    with open(f"{DATA_DIR}/transit_edges_enriched.json") as f:
        edges = json.load(f)

    print(f"Loaded {len(nodes)} nodes, {len(edges)} edges")

    # Build spatial index: (rounded lat, rounded lon) → JSON node
    node_index = {}
    for n in nodes:
        lat = n.get('latitude')
        lon = n.get('longitude')
        nid = n.get('node_id')
        if lat is not None and lon is not None and nid:
            key = (round(lat, 4), round(lon, 4))
            node_index[key] = n

    # Build DB station lookup: (rounded lat, rounded lon) → (id, name, type)
    cur.execute("SELECT id, name, latitude, longitude, station_type FROM stations")
    db_stations = {}
    for sid, sname, slat, slon, stype in cur:
        if slat and slon:
            key = (round(slat, 4), round(slon, 4))
            db_stations.setdefault(key, []).append((sid, sname, stype))

    print(f"DB stations indexed: {len(db_stations)} unique coordinate keys")

    def resolve_node_to_db_station(node_id, lat, lon):
        """Find the DB station UUID for a JSON node."""
        key = (round(lat, 4), round(lon, 4))
        candidates = db_stations.get(key, [])
        if not candidates:
            # Try within 0.002 degrees
            for k, v in db_stations.items():
                if abs(k[0] - round(lat, 4)) <= 0.002 and abs(k[1] - round(lon, 4)) <= 0.002:
                    candidates = v
                    break
        if candidates:
            return candidates[0][0]
        return None

    # ── Phase 1: Seed transport_lines and line_stops ──
    print("\n=== Phase 1: Transport line stops ===\n")

    # Group edges by (line_id, mode, operator) for routable modes
    line_edges = defaultdict(list)
    for e in edges:
        mode = e.get('mode', '')
        if mode not in TRANSPORT_MODES:
            continue
        lid = e.get('line_id', e.get('line_name', ''))
        if not lid:
            continue
        key = (lid, mode, e.get('operator', 'Various'), e.get('line_name', ''))
        line_edges[key].append(e)

    print(f"Line groups: {len(line_edges)}")

    total_ls = 0
    new_lines = 0
    skips = 0

    for (lid, mode, operator, line_name), ledges in sorted(line_edges.items()):
        forward = [e for e in ledges if e.get('direction') == 'forward']
        if not forward:
            forward = ledges  # fallback

        seq = build_stop_sequence(forward)
        if len(seq) < 2:
            skips += 1
            continue

        # Find DB transport_line by name (mode-prefixed)
        db_line_name = f"{mode.capitalize()} {line_name}" if mode != 'flight' else line_name
        if mode == 'bus' and line_name.startswith('Bus '):
            db_line_name = line_name
        elif mode == 'bus':
            db_line_name = f"Bus {line_name}"

        cur.execute(
            "SELECT id FROM transport_lines WHERE name = %s", (db_line_name,))
        db_line = cur.fetchone()

        if not db_line:
            # Try alternate naming: strip mode prefix
            if db_line_name.startswith(mode.capitalize() + " "):
                alt = db_line_name[len(mode.capitalize()) + 1:]
                cur.execute("SELECT id FROM transport_lines WHERE name = %s", (alt,))
                db_line = cur.fetchone()

        if not db_line:
            # Try by line_id stored somewhere — or create a new line
            cur.execute(
                "SELECT id FROM transport_lines WHERE name = %s",
                (lid.replace('BUS_OSM_', '').replace('_', ' ')[:200],))
            db_line = cur.fetchone()

        if not db_line:
            # Create new transport line
            new_id = str(uuid.uuid4())
            mode_label = mode.capitalize() if mode != 'bus' else 'Bus'
            if not line_name:
                line_name = lid.replace('_', ' ')[:200]
            full_name = f"{mode_label} {line_name}"[:200]
            if mode == 'flight':
                full_name = line_name[:200]
            try:
                cur.execute(
                    """INSERT INTO transport_lines (id, name, operator, mode, is_active)
                       VALUES (%s, %s, %s, %s, true)""",
                    (new_id, full_name, operator[:30], mode))
                db_line = (new_id,)
                new_lines += 1
            except Exception as exc:
                skips += 1
                continue

        line_uuid = db_line[0]

        # Map JSON node IDs to DB station UUIDs
        stop_uuids = []
        for nid in seq:
            node = node_index.get((round(next(
                (n['latitude'] for n in nodes if n.get('node_id') == nid), 0
            ), 4), 0))
            # Find node by node_id
            matching_json = [n for n in nodes if n.get('node_id') == nid]
            if not matching_json:
                continue
            mn = matching_json[0]
            lat, lon = mn.get('latitude'), mn.get('longitude')
            if lat is None or lon is None:
                continue
            db_id = resolve_node_to_db_station(nid, lat, lon)
            if db_id:
                stop_uuids.append((nid, db_id, lat, lon))

        if len(stop_uuids) < 2:
            skips += 1
            continue

        # Delete existing line_stops for this line
        cur.execute("DELETE FROM line_stops WHERE line_id = %s", (line_uuid,))

        # Insert line_stops with cumulative distances
        cum_dist = 0.0
        cum_time = 0
        for i, (nid, sid, lat, lon) in enumerate(stop_uuids):
            if i > 0:
                prev_lat, prev_lon = stop_uuids[i - 1][2], stop_uuids[i - 1][3]
                seg_dist = haversine_km(prev_lat, prev_lon, lat, lon)
                cum_dist += seg_dist * 1.3  # road distance factor
                cum_time += max(1, round(seg_dist * 1.3 / 0.5 * 60))  # ~30km/h

            cur.execute(
                """INSERT INTO line_stops (id, line_id, station_id, stop_order,
                   distance_from_start_km, travel_time_from_start_min)
                   VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (str(uuid.uuid4()), line_uuid, sid, i,
                 round(cum_dist, 2), cum_time)
            )
            total_ls += 1

        if new_lines % 20 == 0:
            conn.commit()

    conn.commit()
    print(f"  Lines created: {new_lines}")
    print(f"  Line stops inserted: {total_ls}")
    print(f"  Skipped (no stops mapped): {skips}")

    # ── Phase 2: Create walking transfer lines ──
    print("\n=== Phase 2: Walking transfer edges ===\n")

    # Ensure 'walking' lines exist: create per-city walking "lines"
    # Group transfer edges by source neighborhoods
    transfer_edges = [e for e in edges if e.get('mode') == 'transfer' and e.get('subtype') == 'walking']

    # Create a single "Walking" transport line for pedestrian connections
    cur.execute("SELECT id FROM transport_lines WHERE name = 'Walking (pedestrian)' AND mode = 'walking'")
    walking_line = cur.fetchone()
    if not walking_line:
        walking_line_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO transport_lines (id, name, operator, mode, is_active) VALUES (%s, 'Walking (pedestrian)', 'N/A', 'walking', true)",
            (walking_line_id,))
        walking_line = (walking_line_id,)
        print(f"  Created Walking (pedestrian) line")

    walking_line_id = walking_line[0]
    cur.execute("DELETE FROM line_stops WHERE line_id = %s", (walking_line_id,))

    # Add walking edges as line_stops — but this is tricky since line_stops
    # expects ordered stops on a route. Walking is point-to-point, not a route.
    # We'll skip this for now — the TransitGraph already creates transfer edges
    # between lines that share a station.

    # ── Phase 3: Add transfer edges between stations sharing a city ──
    print("\n=== Phase 3: Intra-city transfer edges ===\n")

    # Group stations by wilaya_id
    cur.execute("SELECT id, latitude, longitude, station_type, wilaya_id FROM stations")
    all_stations = cur.fetchall()

    by_wilaya = defaultdict(list)
    for sid, lat, lon, stype, wid in all_stations:
        if lat and lon and wid:
            by_wilaya[wid].append((sid, lat, lon, stype))

    # For each wilaya, create walking transfers between nearby stations (within 300m)
    transfer_count = 0
    for wid, stations in by_wilaya.items():
        if len(stations) < 2:
            continue

        # Simple 300m threshold for intra-modal transfer
        for i in range(len(stations)):
            s1_id, s1_lat, s1_lon, s1_type = stations[i]
            for j in range(i + 1, len(stations)):
                s2_id, s2_lat, s2_lon, s2_type = stations[j]
                d = haversine_km(s1_lat, s1_lon, s2_lat, s2_lon)
                if d <= 0.3:  # 300m
                    # Check if already exists
                    cur.execute(
                        """SELECT 1 FROM line_stops
                           WHERE line_id = %s AND station_id = %s AND stop_order = 0""",
                        (walking_line_id, s1_id))
                    exists = cur.fetchone()

                    # Insert as forward + backward stop entries on walking line
                    # Using a convention: stop_order tracks distance in cm
                    order_val = int(d * 1000)

                    cur.execute(
                        """INSERT INTO line_stops (id, line_id, station_id, stop_order,
                           distance_from_start_km, travel_time_from_start_min)
                           VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                        (str(uuid.uuid4()), walking_line_id, s1_id,
                         transfer_count * 2, round(d, 3), max(1, round(d / 5 * 60)))
                    )
                    cur.execute(
                        """INSERT INTO line_stops (id, line_id, station_id, stop_order,
                           distance_from_start_km, travel_time_from_start_min)
                           VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                        (str(uuid.uuid4()), walking_line_id, s2_id,
                         transfer_count * 2 + 1, round(d, 3), max(1, round(d / 5 * 60)))
                    )
                    transfer_count += 1

        if transfer_count % 500 == 0:
            conn.commit()

    conn.commit()
    print(f"  Intra-city transfer pairs: {transfer_count}")

    # ── Final summary ──
    cur.execute("SELECT COUNT(*) FROM line_stops")
    print(f"\n=== Final ===")
    print(f"  Line stops total: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM transport_lines")
    print(f"  Transport lines total: {cur.fetchone()[0]}")
    cur.execute("SELECT mode, COUNT(*) FROM transport_lines GROUP BY mode ORDER BY mode")
    for mode, cnt in cur:
        print(f"    {mode}: {cnt}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
