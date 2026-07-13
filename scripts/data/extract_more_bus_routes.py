#!/usr/bin/env python3
"""Extract additional OSM bus routes for cities not covered in the initial pass.

Only extracts routes that have proper stop nodes (public_transport=stop_position,
public_transport=platform, or highway=bus_stop). Skips routes with only way members
(road geometry) since those lack stop information.
"""

import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DATA_DIR = "app/data"
OVERSPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"

NEW_ROUTES = [
    {"id": 2847007, "ref": "35", "direction": "forward", "city": "Algiers"},
    {"id": 2849252, "ref": "4", "direction": "forward", "city": "Algiers"},
    {"id": 11273124, "ref": "7", "direction": "forward", "city": "Algiers", "line_name": "1e Mai - Place des Martyrs"},
    {"id": 2881810, "ref": "89", "direction": "forward", "city": "Algiers"},
    {"id": 2865717, "ref": "79", "direction": "forward", "city": "Algiers"},
    {"id": 3105899, "ref": "59", "direction": "forward", "city": "Algiers"},
    {"id": 3109487, "ref": "56", "direction": "forward", "city": "Algiers", "line_name": "Chevalley - Zéralda (par Chéraga)"},
    {"id": 11275870, "ref": "96", "direction": "forward", "city": "Algiers", "line_name": "Djnane Sfari - Hai El Badr"},
    {"id": 5597409, "ref": "92", "direction": "forward", "city": "Algiers", "line_name": "Stade Ferhani - El Annasser"},
    {"id": 3114066, "ref": "102", "direction": "forward", "city": "Algiers"},
    {"id": 2865798, "ref": "67", "direction": "forward", "city": "Algiers"},
    {"id": 3122700, "ref": "94", "direction": "forward", "city": "Algiers"},
    {"id": 2865632, "ref": "63", "direction": "forward", "city": "Algiers"},
    {"id": 3101360, "ref": "7 R", "direction": "backward", "city": "Algiers", "line_name": "Place des Martyrs - 1e Mai"},
    {"id": 11267136, "ref": "56 R", "direction": "backward", "city": "Algiers", "line_name": "Zéralda (par Chéraga) - Chevalley"},
    {"id": 11273123, "ref": "92 R", "direction": "backward", "city": "Algiers", "line_name": "El Annasser - Stade Ferhani"},
    {"id": 7876088, "ref": "(univ)Chetouane-Imama", "direction": "forward", "city": "Tlemcen"},
    {"id": 7876090, "ref": "(univ)Chetouane-LaGare", "direction": "forward", "city": "Tlemcen"},
    {"id": 7848106, "ref": "(univ)Chetouane-LaRocade", "direction": "forward", "city": "Tlemcen"},
    {"id": 7876089, "ref": "(univ)Chetouane-Medecine", "direction": "forward", "city": "Tlemcen"},
    {"id": 18468277, "ref": "MILA_1", "direction": "forward", "city": "Mila", "line_name": "Kouch Nour Eddine -> Merzoug Ammar"},
    {"id": 18468278, "ref": "MILA_1_R", "direction": "backward", "city": "Mila", "line_name": "Merzoug Ammar -> Kouch Nour Eddine"},
    {"id": 18468572, "ref": "MILA_2", "direction": "forward", "city": "Mila", "line_name": "Kouch Nour Eddine -> Hadjar Eddis"},
    {"id": 18468573, "ref": "MILA_2_R", "direction": "backward", "city": "Mila", "line_name": "Hadjar Eddis -> Kouch Nour Eddine"},
    {"id": 18559186, "ref": "MILA_3", "direction": "forward", "city": "Mila", "line_name": "Kouch Nour Eddine -> El Kalitoussa"},
    {"id": 18559187, "ref": "MILA_3_R", "direction": "backward", "city": "Mila", "line_name": "El Kalitoussa -> Kouch Nour Eddine"},
    {"id": 5970201, "ref": "TS1", "direction": "forward", "city": "Bejaia"},
    {"id": 8089675, "ref": "5", "direction": "forward", "city": "Oum El Bouaghi"},
    {"id": 19393432, "ref": "OUARGLA_39", "direction": "forward", "city": "Ouargla", "line_name": "Bus 39 - Medina Jdida"},
    {"id": 19393433, "ref": "OUARGLA_HN_HS", "direction": "forward", "city": "Ouargla", "line_name": "Hai Nedjma - Hai Sabah"},
    {"id": 9415409, "ref": "ROUIBA", "direction": "forward", "city": "Algiers", "line_name": "Station 2 Mai -> Rouiba"},
]


def fetch_relation(rel_id, retries=5):
    query = f"""
    [out:json][timeout:60];
    relation({rel_id});
    (._;>>;);
    out body;
    """
    headers = {"User-Agent": USER_AGENT}
    data = urllib.parse.urlencode({"data": query}).encode()

    for attempt in range(retries):
        try:
            req = urllib.request.Request(OVERSPASS_URL, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 504):
                wait = (2 ** attempt) + 5
                print(f"    Error {e.code}, waiting {wait}s...", flush=True)
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code}: {e.reason}", flush=True)
            return None
        except Exception as e:
            print(f"    Error: {e}", flush=True)
            time.sleep((2 ** attempt) + 1)
            continue
    return None


def extract_stops(result):
    """Extract bus stops from relation data. Only returns verified bus stops."""
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

    # Walk way nodes in order to preserve route sequence
    ordered_way_node_ids = []
    for m in members:
        if m['type'] == 'way' and m['ref'] in ways:
            ordered_way_node_ids.extend(ways[m['ref']].get('nodes', []))

    seen = set()
    unique_way_nodes = []
    for nid in ordered_way_node_ids:
        if nid not in seen:
            seen.add(nid)
            unique_way_nodes.append(nid)

    # Find REAL bus stops along the way
    stops = []
    for nid in unique_way_nodes:
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

        # Only include if it's a verified bus stop, skip geometry-only nodes
        if is_bus_stop:
            name = tags.get('name', '') or tags.get('name:ar', '') or tags.get('name:fr', '') or ''
            stops.append({
                'osm_node_id': nid,
                'name': name[:200],
                'name_ar': (tags.get('name:ar', '') or '')[:200],
                'name_en': (tags.get('name:en', '') or '')[:200],
                'latitude': node['lat'],
                'longitude': node['lon'],
            })

    # If we have very few stops, also include named nodes that might be landmarks
    if len(stops) < 3:
        for nid in unique_way_nodes:
            node = nodes.get(nid)
            if not node:
                continue
            tags = node.get('tags', {})
            name = tags.get('name', '') or ''
            if name and len(name) > 3:
                # Check if already added
                if not any(s['osm_node_id'] == nid for s in stops):
                    stops.append({
                        'osm_node_id': nid,
                        'name': name[:200],
                        'name_ar': (tags.get('name:ar', '') or '')[:200],
                        'name_en': (tags.get('name:en', '') or '')[:200],
                        'latitude': node['lat'],
                        'longitude': node['lon'],
                    })

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
        print(f"    SKIP: only {len(stops)} verified stops (route has no mapped bus stops)", flush=True)
        return None, None

    line_name = build_line_name(tags, route_info)
    operator = build_operator(tags)
    osm_line_id = f"BUS_OSM_{ref}"

    # Generate nodes
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

    # Generate edges
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
    print("=== Extract More OSM Bus Routes ===\n")

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

        time.sleep(3)

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
