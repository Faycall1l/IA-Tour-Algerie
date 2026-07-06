#!/usr/bin/env python3
"""Scrape urban bus routes from OpenStreetMap for all major Algerian cities.

Fetches bus route relations via Overpass API, extracts stop nodes in order,
and generates transit nodes + edges compatible with the enriched graph format.

Usage:
  python scripts/data/scrape_urban_bus_osm.py [--fetch] [--output DIR]

Options:
  --fetch   Fetch fresh data from Overpass API (otherwise use cached)
  --output  Output directory (default: app/data)
"""

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
CACHE_PATH = ROOT / "tmp" / "osm_bus_data.json"
OUTPUT_DIR = ROOT / "app" / "data"
NODES_PATH = OUTPUT_DIR / "transit_nodes_enriched.json"
EDGES_PATH = OUTPUT_DIR / "transit_edges_enriched.json"

OVERPass_URL = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
BUS_SPEED_KPH = 25
BUS_PRICE_PER_KM = 10
OVERPASS_QUERY = """
[out:json][timeout:240];
area["name:en"="Algeria"]->.a;
relation[route=bus](area.a);
(._;>;);
out body;
"""


def fetch_osm_data() -> dict:
    print("Fetching bus data from Overpass API...")
    data = json.dumps({"data": OVERPASS_QUERY}).encode()
    req = urllib.request.Request(
        OVERPass_URL,
        data=OVERPASS_QUERY.encode(),
        headers={"Content-Type": "text/plain"},
    )
    resp = urllib.request.urlopen(req, timeout=300)
    result = json.loads(resp.read())
    rels = [e for e in result["elements"] if e["type"] == "relation"]
    nodes = [e for e in result["elements"] if e["type"] == "node"]
    print(f"  Got {len(rels)} relations, {len(nodes)} nodes")
    return result


def make_station_id(name: str, osm_id: int) -> str:
    suffix = hashlib.md5(f"{name}_{osm_id}".encode()).hexdigest()[:8].upper()
    return f"STATION_BUS_{suffix}"


def make_edge_id(from_id: str, to_id: str, line_ref: str) -> str:
    raw = f"EDGE_BUS_OSM_{line_ref}_{from_id[-20:]}_{to_id[-20:]}"
    return raw.upper().replace("-", "_")


def haversine_km(lat1, lng1, lat2, lng2) -> float:
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(
        math.radians(lat2)
    ) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_wilaya(lat: float, lng: float) -> int:
    """Crude wilaya mapping by capital proximity."""
    WILAYA_CAPITALS = {
        1: (36.767, 3.058), 2: (36.717, 3.208), 3: (36.750, 3.080), 4: (36.367, 6.615),
        5: (35.556, 6.174), 6: (36.751, 5.064), 7: (35.401, 8.121), 8: (33.004, 6.007),
        9: (36.717, 4.050), 10: (36.367, 7.267), 11: (36.167, 5.417), 12: (35.904, 7.122),
        13: (34.878, -1.316), 14: (36.150, 4.767), 15: (36.717, 4.050), 16: (36.767, 3.058),
        17: (36.750, 3.080), 18: (36.717, 3.208), 19: (36.191, 5.410), 20: (36.767, 3.058),
        21: (36.767, 3.058), 22: (35.194, -0.642), 23: (36.900, 7.767), 24: (36.733, 3.083),
        25: (36.367, 6.615), 26: (36.717, 3.208), 27: (36.750, 3.080), 28: (36.367, 6.615),
        29: (36.767, 3.058), 30: (36.367, 6.615), 31: (35.697, -0.633), 32: (36.367, 6.615),
        33: (36.367, 6.615), 34: (36.367, 6.615), 35: (36.750, 3.080), 36: (36.367, 6.615),
        37: (36.750, 3.080), 38: (36.767, 3.058), 39: (36.750, 3.080), 40: (36.750, 3.080),
    }
    best_wid = 16
    best_dist = float("inf")
    for wid, (clat, clng) in WILAYA_CAPITALS.items():
        d = haversine_km(lat, lng, clat, clng)
        if d < best_dist:
            best_dist = d
            best_wid = wid
    return best_wid


def process_routes(osm_data: dict, existing_nodes: list, existing_edges: list):
    """Process OSM bus route relations into transit nodes + edges."""
    elem_map = {e["type"] + "_" + str(e["id"]): e for e in osm_data["elements"]}
    relations = [e for e in osm_data["elements"] if e["type"] == "relation"]

    # Build existing node index for matching (by name proximity)
    existing_coords = {}
    for n in existing_nodes:
        if n.get("latitude") and n.get("longitude"):
            existing_coords[n["node_id"]] = (n["latitude"], n["longitude"])

    new_nodes = []
    new_edges = []

    # Track unique stops by (name, lat, lng) proximity
    stop_registry = {}  # (name_normalized, lat_rounded, lng_rounded) -> node_id
    stop_node_map = {}  # osm_node_key -> our node_id

    edges_added = 0
    nodes_added = 0
    routes_processed = 0

    # Pre-process all stop nodes in the OSM data
    osm_stop_nodes = {}
    for e in osm_data["elements"]:
        if e["type"] == "node":
            t = e.get("tags", {})
            name = t.get("name", "")
            if name:
                key = e["type"] + "_" + str(e["id"])
                osm_stop_nodes[key] = {
                    "id": e["id"],
                    "name": name,
                    "name_ar": t.get("name:ar", ""),
                    "lat": e.get("lat", 0),
                    "lon": e.get("lon", 0),
                }

    for rel in relations:
        tags = rel.get("tags", {})
        ref = tags.get("ref", "").strip()
        name = tags.get("name", "").strip()
        network = tags.get("network", "").strip()
        operator = tags.get("operator", "").strip()
        route_from = tags.get("from", "").strip()
        route_to = tags.get("to", "").strip()
        colour = tags.get("colour", "").strip()

        if not ref and not name:
            continue

        # Get stop members in order (filter to role=stop/platform/node)
        members = rel.get("members", [])
        stop_members = [
            m for m in members
            if m["type"] == "node" and m.get("role") in (
                "stop", "platform", "stop_entry_only", "stop_exit_only",
                "platform_entry_only", "platform_exit_only", "bus_stop", ""
            )
        ]

        if len(stop_members) < 2:
            continue

        # Collect stop data
        stops = []
        for m in stop_members:
            key = m["type"] + "_" + str(m["ref"])
            sn = osm_stop_nodes.get(key)
            if sn:
                # Check if stop has valid coords
                if sn["lat"] == 0 and sn["lon"] == 0:
                    continue
                stop_label = f"{sn['name']} ({sn['lat']:.4f}, {sn['lon']:.4f})"

                # Create or reuse our station ID
                lat_r = round(sn["lat"], 4)
                lng_r = round(sn["lon"], 4)
                norm_name = sn["name"].strip().lower()[:30]
                dedup_key = (norm_name, lat_r, lng_r)

                if dedup_key in stop_registry:
                    sid = stop_registry[dedup_key]
                else:
                    sid = make_station_id(sn["name"], sn["id"])
                    stop_registry[dedup_key] = sid
                    new_nodes.append({
                        "node_id": sid,
                        "name": sn["name"],
                        "name_ar": sn.get("name_ar", ""),
                        "name_en": "",
                        "type": "bus",
                        "subtype": "urban",
                        "operator": operator or "ETUSA",
                        "wilaya_id": get_wilaya(sn["lat"], sn["lon"]),
                        "latitude": sn["lat"],
                        "longitude": sn["lon"],
                        "osm_data": {"osm_id": sn["id"], "role": m.get("role", "")},
                        "codes": {},
                        "lines_at_station": [],
                        "has_parking": None,
                        "has_accessibility": None,
                        "metadata": {"source": "osm_bus"},
                    })
                    nodes_added += 1

                stop_node_map[key] = sid
                stops.append({
                    "node_id": sid,
                    "name": sn["name"],
                    "lat": sn["lat"],
                    "lon": sn["lon"],
                })

        if len(stops) < 2:
            continue

        routes_processed += 1
        line_id = f"BUS_OSM_{ref}" if ref else f"BUS_OSM_{rel['id']}"
        line_name = name or f"Bus {ref}" if ref else name
        if route_from and route_to:
            line_name = f"{route_from} → {route_to}"

        # Create edges between consecutive stops
        for i in range(len(stops) - 1):
            a, b = stops[i], stops[i + 1]
            dist = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            if dist < 0.05:
                continue
            road_dist = round(dist * 1.3, 2)
            duration = max(2, int(road_dist / BUS_SPEED_KPH * 60))
            price = int(road_dist * BUS_PRICE_PER_KM)

            # Forward edge
            eid_fwd = make_edge_id(a["node_id"], b["node_id"], line_id)
            new_edges.append({
                "edge_id": eid_fwd,
                "from_node_id": a["node_id"],
                "to_node_id": b["node_id"],
                "mode": "bus",
                "subtype": "urban",
                "operator": operator or "ETUSA",
                "line_id": line_id,
                "line_name": line_name,
                "direction": "forward",
                "distance_km": road_dist,
                "duration_min": duration,
                "stops_between": 0,
                "frequency_min": 15,
                "pricing": {"single": max(20, price)},
                "schedule": {
                    "first_departure": "06:00",
                    "last_departure": "18:30",
                    "frequency_min": 15,
                    "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "destination": b.get("name", ""),
                },
                "metadata": {"source": "osm_bus", "osm_relation_id": rel["id"]},
            })
            edges_added += 1

            # Backward edge
            eid_bwd = make_edge_id(b["node_id"], a["node_id"], line_id)
            new_edges.append({
                "edge_id": eid_bwd,
                "from_node_id": b["node_id"],
                "to_node_id": a["node_id"],
                "mode": "bus",
                "subtype": "urban",
                "operator": operator or "ETUSA",
                "line_id": line_id,
                "line_name": line_name,
                "direction": "backward",
                "distance_km": road_dist,
                "duration_min": duration,
                "stops_between": 0,
                "frequency_min": 15,
                "pricing": {"single": max(20, price)},
                "schedule": {
                    "first_departure": "06:00",
                    "last_departure": "18:30",
                    "frequency_min": 15,
                    "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    "destination": a.get("name", ""),
                },
                "metadata": {"source": "osm_bus", "osm_relation_id": rel["id"]},
            })
            edges_added += 1

    print(f"\nProcessed {routes_processed} routes")
    print(f"Added {nodes_added} new bus stop nodes")
    print(f"Added {edges_added} new bus edges")
    return new_nodes, new_edges


def merge_with_existing(new_nodes, new_edges):
    """Merge new bus data with existing enriched data, deduplicating."""
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


def main():
    parser = argparse.ArgumentParser(description="Scrape urban bus routes from OSM")
    parser.add_argument("--fetch", action="store_true", help="Fetch fresh data from Overpass API")
    args = parser.parse_args()

    # Fetch or load cached OSM data
    if args.fetch or not CACHE_PATH.exists():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        osm_data = fetch_osm_data()
        CACHE_PATH.write_text(json.dumps(osm_data))
        print(f"Cached to {CACHE_PATH}")
    else:
        osm_data = json.loads(CACHE_PATH.read_text())
        rels_in = [e for e in osm_data["elements"] if e["type"] == "relation"]
        nodes_in = [e for e in osm_data["elements"] if e["type"] == "node"]
        print(f"Loaded cached data: {len(rels_in)} relations, {len(nodes_in)} nodes")

    # Load existing enriched data
    existing_nodes = json.loads(NODES_PATH.read_text()) if NODES_PATH.exists() else []
    existing_edges = json.loads(EDGES_PATH.read_text()) if EDGES_PATH.exists() else []

    print(f"Existing enriched data: {len(existing_nodes)} nodes, {len(existing_edges)} edges")

    # Process routes
    new_nodes, new_edges = process_routes(osm_data, existing_nodes, existing_edges)

    # Merge and save
    merge_with_existing(new_nodes, new_edges)


if __name__ == "__main__":
    main()
