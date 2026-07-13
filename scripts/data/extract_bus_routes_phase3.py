#!/usr/bin/env python3
"""Extract additional OSM bus routes for underserved cities (Phase 3).

Targets: Batna, Tlemcen (A42/B42), Jijel
"""

import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DATA_DIR = "app/data"
OVERSPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"

NEW_ROUTES = [
    {"id": 18591051, "ref": "03", "direction": "forward", "city": "Batna"},
    {"id": 7848044, "ref": "A42", "direction": "forward", "city": "Tlemcen", "line_name": "A42 Oujlida-Aboutachfine-Tlemcen"},
    {"id": 7848086, "ref": "B42", "direction": "forward", "city": "Tlemcen", "line_name": "B42 Oujlida-Aboutachfine-Tlemcen"},
    {"id": 19605702, "ref": "JIJEL_1", "direction": "forward", "city": "Jijel", "line_name": "الطاهير-جيجل"},
]


def fetch_relation(rel_id, retries=5):
    query = f"""
    [out:json][timeout:90];
    relation({rel_id});
    (._;>>;);
    out body;
    """
    headers = {"User-Agent": USER_AGENT}
    data = urllib.parse.urlencode({"data": query}).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(OVERSPASS_URL, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 504):
                wait = (3 ** attempt) + 5
                print(f"    Error {e.code}, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code}: {e.reason}", flush=True)
            return None
        except Exception as e:
            print(f"    Error: {e}", flush=True)
            time.sleep((3 ** attempt) + 2)
            continue
    return None


def extract_stops(result):
    if not result or 'elements' not in result:
        return []

    elements = result['elements']
    relation = None
    nodes = {}
    ways = {}

    for elem in elements:
        if elem['type'] == 'relation':
            relation = elem
        elif elem['type'] == 'node':
            nodes[elem['id']] = elem
        elif elem['type'] == 'way':
            ways[elem['id']] = elem

    if not relation:
        return []

    members = relation.get('members', [])

    # First pass: collect stop/platform members in order
    ordered_stop_ids = []
    for m in members:
        if m['type'] == 'node' and m.get('role') in ('stop', 'platform', 'stop_position', ''):
            ordered_stop_ids.append(m['ref'])

    # Second pass: collect way nodes in order
    ordered_way_node_ids = []
    for m in members:
        if m['type'] == 'way' and m['ref'] in ways:
            ordered_way_node_ids.extend(ways[m['ref']].get('nodes', []))

    # De-duplicate while preserving order
    seen = set()
    unique_way_nodes = []
    for nid in ordered_way_node_ids:
        if nid not in seen:
            seen.add(nid)
            unique_way_nodes.append(nid)

    # Use way nodes to extract stops, preferring explicit stop members
    all_candidate_ids = list(dict.fromkeys(ordered_stop_ids + unique_way_nodes))

    stops = []
    seen_stop_node_ids = set()
    for nid in all_candidate_ids:
        if nid in seen_stop_node_ids:
            continue
        node = nodes.get(nid)
        if not node:
            continue
        tags = node.get('tags', {})
        is_bus_stop = (
            tags.get('public_transport') in ('stop_position', 'platform')
            or tags.get('highway') == 'bus_stop'
            or tags.get('bus') == 'yes'
        )
        has_name = bool(tags.get('name', '') or tags.get('name:ar', '') or tags.get('name:fr', ''))

        if is_bus_stop or has_name:
            name = tags.get('name', '') or tags.get('name:ar', '') or tags.get('name:fr', '') or ''
            stops.append({
                'osm_node_id': nid,
                'name': name[:200],
                'name_ar': (tags.get('name:ar', '') or '')[:200],
                'name_en': (tags.get('name:en', '') or '')[:200],
                'latitude': node['lat'],
                'longitude': node['lon'],
            })
            seen_stop_node_ids.add(nid)

    return stops


def node_id(stop):
    return f"STATION_BUS_{stop['osm_node_id']}"


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))


def build_line_name(tags, route_info):
    if route_info.get('line_name'):
        return route_info['line_name']
    name = tags.get('name', '')
    from_val = tags.get('from', '')
    to_val = tags.get('to', '')
    if from_val and to_val:
        return f"{from_val} → {to_val}"
    return name or f"Ligne {route_info['ref']}"


def build_operator(tags):
    op = tags.get('operator', '')
    if op:
        return op
    network = tags.get('network', '')
    if network:
        return network
    return 'Various'


def process_route(route_info):
    rel_id = route_info['id']
    ref = route_info['ref']
    direction = route_info['direction']
    city = route_info['city']

    print(f"\n  [{city}] Relation {rel_id} (ref={ref}, {direction})...", flush=True)

    result = fetch_relation(rel_id)
    if not result:
        print(f"    FAILED: no result", flush=True)
        return None, None

    relation = None
    for elem in result['elements']:
        if elem['type'] == 'relation':
            relation = elem
            break

    if not relation:
        print(f"    FAILED: no relation element", flush=True)
        return None, None

    tags = relation.get('tags', {})
    stops = extract_stops(result)

    if len(stops) < 2:
        print(f"    SKIP: only {len(stops)} verified stops", flush=True)
        return None, None

    line_name = build_line_name(tags, route_info)
    operator = build_operator(tags)
    osm_line_id = f"BUS_OSM_{ref}"

    new_nodes = {}
    for stop in stops:
        nid = node_id(stop)
        new_nodes[nid] = {
            "node_id": nid,
            "name": stop['name'],
            "name_ar": stop['name_ar'],
            "name_en": stop['name_en'],
            "type": "bus",
            "subtype": "urban",
            "operator": operator,
            "latitude": stop['latitude'],
            "longitude": stop['longitude'],
            "wilaya_id": None,
        }

    new_edges = []
    duration_factor = 2.0

    for i in range(len(stops) - 1):
        s1 = stops[i]
        s2 = stops[i + 1]
        f_id = node_id(s1)
        t_id = node_id(s2)
        dist = haversine_km(s1['latitude'], s1['longitude'],
                            s2['latitude'], s2['longitude'])
        road_dist = max(0.1, dist * 1.3)
        dur = max(1, round(road_dist * duration_factor))

        new_edges.append({
            "edge_id": f"EDGE_BUS_OSM_{ref}_forward_{s1['osm_node_id']}_{s2['osm_node_id']}",
            "from_node_id": f_id,
            "to_node_id": t_id,
            "mode": "bus",
            "subtype": "urban",
            "operator": operator,
            "line_id": osm_line_id,
            "line_name": line_name,
            "direction": "forward",
            "distance_km": round(road_dist, 2),
            "duration_min": dur,
            "stops_between": 0,
            "frequency_min": 15,
            "pricing": {"single": 20},
            "schedule": {
                "start": "06:00",
                "end": "18:30",
                "frequency_min": 15,
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            },
        })

        new_edges.append({
            "edge_id": f"EDGE_BUS_OSM_{ref}_backward_{s2['osm_node_id']}_{s1['osm_node_id']}",
            "from_node_id": t_id,
            "to_node_id": f_id,
            "mode": "bus",
            "subtype": "urban",
            "operator": operator,
            "line_id": osm_line_id,
            "line_name": line_name,
            "direction": "backward",
            "distance_km": round(road_dist, 2),
            "duration_min": dur,
            "stops_between": 0,
            "frequency_min": 15,
            "pricing": {"single": 20},
            "schedule": {
                "start": "06:00",
                "end": "18:30",
                "frequency_min": 15,
                "days": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            },
        })

    print(f"    {len(new_nodes)} stops, {len(new_edges)} edges", flush=True)
    return new_nodes, new_edges


def main():
    print("=== Extract Bus Routes Phase 3 ===\n")

    nodes_path = f"{DATA_DIR}/transit_nodes_enriched.json"
    edges_path = f"{DATA_DIR}/transit_edges_enriched.json"

    with open(nodes_path) as f:
        existing_nodes = json.load(f)
    with open(edges_path) as f:
        existing_edges = json.load(f)

    print(f"Existing: {len(existing_nodes)} nodes, {len(existing_edges)} edges")

    existing_node_ids = {n.get('node_id', '') for n in existing_nodes}
    existing_edge_ids = {e.get('edge_id', '') for e in existing_edges}

    all_new_nodes = {}
    all_new_edges = {}
    processed = 0
    skipped = 0
    failed = 0

    for route in NEW_ROUTES:
        nodes, edges = process_route(route)
        if nodes is None:
            failed += 1
            continue
        if not nodes:
            skipped += 1
            continue

        processed += 1

        for nid, node in nodes.items():
            if nid not in existing_node_ids and nid not in all_new_nodes:
                all_new_nodes[nid] = node

        for edge in edges:
            eid = edge['edge_id']
            if eid not in existing_edge_ids and eid not in all_new_edges:
                all_new_edges[eid] = edge

        time.sleep(5)

    print(f"\n=== Results ===")
    print(f"  Processed: {processed} routes")
    print(f"  Skipped (no stops): {skipped}")
    print(f"  Failed: {failed} routes")
    print(f"  New nodes: {len(all_new_nodes)}")
    print(f"  New edges: {len(all_new_edges)}")

    if not all_new_nodes and not all_new_edges:
        print("  Nothing new to add.")
        return

    existing_nodes.extend(all_new_nodes.values())
    existing_edges.extend(all_new_edges.values())

    with open(nodes_path, 'w') as f:
        json.dump(existing_nodes, f, ensure_ascii=False, indent=2)
    with open(edges_path, 'w') as f:
        json.dump(existing_edges, f, ensure_ascii=False, indent=2)

    print(f"  Final: {len(existing_nodes)} nodes, {len(existing_edges)} edges")
    print("Done!")


if __name__ == "__main__":
    main()
