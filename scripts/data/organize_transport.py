#!/usr/bin/env python3
"""Organize the transport graph for agent-based trip planning.

1. Group taxi edges into named routes by wilaya pair
2. Consolidate SOGRAL into a proper inter-city network
3. Add inter-city connections between neighboring wilaya capitals
4. Build line → station index for quick agent querying
5. Populate stations, transport_lines, line_stops DB tables
"""

import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)

# Wilaya coordinates (id → lat, lon) for inter-city connectivity
WILAYA_COORDS = {
    1: (27.87, -0.29), 2: (36.16, 1.33), 3: (33.80, 2.88), 4: (35.87, 7.12),
    5: (35.55, 6.17), 6: (36.75, 5.06), 7: (34.85, 5.73), 8: (31.62, -2.22),
    9: (36.47, 2.83), 10: (36.37, 3.90), 11: (22.79, 5.52), 12: (35.40, 8.12),
    13: (34.88, -1.32), 14: (35.37, 1.32), 15: (36.72, 4.05), 16: (36.75, 3.04),
    17: (34.67, 3.25), 18: (36.82, 5.77), 19: (36.19, 5.41), 20: (34.83, 0.15),
    21: (36.87, 6.91), 22: (35.19, -0.63), 23: (36.90, 7.77), 24: (36.46, 7.43),
    25: (36.37, 6.61), 26: (36.27, 2.75), 27: (35.93, 0.09), 28: (35.70, 4.55),
    29: (35.40, 0.14), 30: (31.96, 5.33), 31: (35.70, -0.65), 32: (32.76, 1.02),
    33: (26.51, 8.48), 34: (36.07, 4.76), 35: (36.76, 3.48), 36: (36.77, 8.31),
    37: (27.67, -8.13), 38: (35.61, 1.81), 39: (33.37, 6.86), 40: (35.43, 7.14),
    41: (36.29, 7.95), 42: (36.59, 2.45), 43: (36.45, 6.26), 44: (36.26, 1.97),
    45: (33.27, -0.31), 46: (35.30, -1.14), 47: (32.49, 3.67), 48: (35.74, 0.56),
    49: (29.26, 0.23), 50: (30.08, -2.16), 51: (27.19, 2.46), 52: (19.57, 5.77),
    53: (33.11, 6.06), 54: (24.55, 9.48), 55: (33.95, 5.92), 56: (30.58, 2.88),
    57: (34.43, 5.07), 58: (21.33, 0.95),
}

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi", 5: "Batna",
    6: "Béjaïa", 7: "Biskra", 8: "Béchar", 9: "Blida", 10: "Bouira",
    11: "Tamanrasset", 12: "Tébessa", 13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou",
    16: "Alger", 17: "Djelfa", 18: "Jijel", 19: "Sétif", 20: "Saïda",
    21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba", 24: "Guelma", 25: "Constantine",
    26: "Médéa", 27: "Mostaganem", 28: "M'Sila", 29: "Mascara", 30: "Ouargla",
    31: "Oran", 32: "El Bayadh", 33: "Illizi", 34: "Bordj Bou Arréridj",
    35: "Boumerdès", 36: "El Tarf", 37: "Tindouf", 38: "Tissemsilt", 39: "El Oued",
    40: "Khenchela", 41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Aïn Defla",
    45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa", 48: "Relizane",
    49: "Timimoun", 50: "Béni Abbès", 51: "Aïn Salah", 52: "Aïn Guezzam",
    53: "Touggourt", 54: "Djanet", 55: "El M'Ghair", 56: "El Meniaa",
    57: "Ouled Djellal", 58: "Bordj Badji Mokhtar",
}


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    print("=== Transport Graph Organization ===\n")

    # Load current graph
    nodes_list = json.loads(NODES_PATH.read_text())
    edges_list = json.loads(EDGES_PATH.read_text())
    nodes = {n["node_id"]: n for n in nodes_list}

    print(f"Current: {len(nodes_list)} nodes, {len(edges_list)} edges")

    # --- Phase 1: Group taxi edges into named routes ---
    print("\n--- Phase 1: Organize taxi edges into routes ---")

    taxi_edges = [e for e in edges_list if e.get("mode") == "taxi"]
    untaxied = [e for e in edges_list if e.get("mode") != "taxi"]
    print(f"Taxi edges: {len(taxi_edges)}")

    # Group by (from_wilaya, to_wilaya) pair
    taxi_routes = defaultdict(list)
    taxi_grouped = []
    for e in taxi_edges:
        nf = nodes.get(e["from_node_id"])
        nt = nodes.get(e["to_node_id"])
        if nf and nt:
            fw = nf.get("wilaya_id", 0)
            tw = nt.get("wilaya_id", 0)
            pair = (fw, tw)
            taxi_routes[pair].append(e)

    for pair, group in sorted(taxi_routes.items()):
        fw, tw = pair
        fn = WILAYA_NAMES.get(fw, f"W{fw}")
        tn = WILAYA_NAMES.get(tw, f"W{tw}")
        route_id = f"TAXI_{fn.upper()[:6]}_{tn.upper()[:6]}"
        route_name = f"Taxi {fn} → {tn}"

        for e in group:
            e["line_id"] = route_id
            e["line_name"] = route_name
            e["route_type"] = "intercity_taxi"
            taxi_grouped.append(e)

    print(f"Grouped into {len(taxi_routes)} routes")
    for (fw, tw), es in sorted(taxi_routes.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {WILAYA_NAMES.get(fw,'?')} ↔ {WILAYA_NAMES.get(tw,'?')}: {len(es)} edges")

    # --- Phase 2: Consolidate SOGRAL ---
    print("\n--- Phase 2: Consolidate SOGRAL inter-city bus network ---")

    sogral_edges = [e for e in untaxied if (e.get("line_id") or "").startswith("SOGRAL")]
    non_sogral = [e for e in untaxied if not (e.get("line_id") or "").startswith("SOGRAL")]

    single_edge_sogral = [e for e in sogral_edges if e["line_id"].startswith("SOGRAL_L")]
    named_routes_sogral = [e for e in sogral_edges if not e["line_id"].startswith("SOGRAL_L")]

    print(f"SOGRAL single-edge lines: {len(single_edge_sogral)} edges")
    print(f"SOGRAL named multi-edge routes: {len(named_routes_sogral)} edges")

    # Consolidate single-edge lines into one big network
    sogral_consolidated = []
    for e in single_edge_sogral:
        nf = nodes.get(e["from_node_id"])
        nt = nodes.get(e["to_node_id"])
        fw = nf.get("wilaya_id") if nf else None
        tw = nt.get("wilaya_id") if nt else None
        fn = WILAYA_NAMES.get(fw, "Unknown")
        tn = WILAYA_NAMES.get(tw, "Unknown")
        e["line_id"] = "SOGRAL_INTER_CITY"
        e["line_name"] = f"{fn} → {tn}"
        e["route_type"] = "intercity_bus"
        sogral_consolidated.append(e)

    # Keep named routes as-is
    for e in named_routes_sogral:
        e["route_type"] = "intercity_bus"

    all_sogral = sogral_consolidated + named_routes_sogral
    print(f"Consolidated to 1 inter-city + {len(named_routes_sogral)} named-route edges")

    # --- Phase 3: Add inter-city connections for missing wilaya pairs ---
    print("\n--- Phase 3: Inter-city connectivity overlay ---")

    # Find what wilayas have transport hubs
    wilaya_hubs = defaultdict(list)
    for n in nodes_list:
        wid = n.get("wilaya_id")
        if wid and n.get("type") in ("bus", "train", "taxi", "airport"):
            if n.get("latitude") and n.get("longitude"):
                wilaya_hubs[wid].append(n)

    # For wilayas with no transport hub, create a virtual hub at wilaya center
    for wid, (lat, lon) in WILAYA_COORDS.items():
        if wid not in wilaya_hubs:
            nid = f"HUB_VIRTUAL_{WILAYA_NAMES[wid].upper()[:10]}"
            hub = {
                "node_id": nid,
                "name": f"{WILAYA_NAMES[wid]} (Hub)",
                "type": "virtual_hub",
                "subtype": "intercity_hub",
                "wilaya_id": wid,
                "wilaya_name": WILAYA_NAMES[wid],
                "latitude": lat,
                "longitude": lon,
                "lines_at_station": [],
                "metadata": {"source": "connectivity_overlay", "is_virtual": True},
            }
            nodes_list.append(hub)
            nodes[nid] = hub
            wilaya_hubs[wid].append(hub)

    # Build inter-city edges between neighboring wilayas within 300km
    inter_city_edges = []
    connected_pairs = set()

    # Existing connections (from taxi + SOGRAL + train)
    for e in edges_list:
        nf = nodes.get(e.get("from_node_id", ""))
        nt = nodes.get(e.get("to_node_id", ""))
        if nf and nt and nf.get("wilaya_id") and nt.get("wilaya_id"):
            fw, tw = nf["wilaya_id"], nt["wilaya_id"]
            if fw != tw:
                connected_pairs.add((fw, tw))
                connected_pairs.add((tw, fw))

    print(f"Already connected wilaya pairs: {len(connected_pairs)//2}")

    # Connect each wilaya to nearby ones within 250km
    new_connections = 0
    for wid1, (lat1, lon1) in WILAYA_COORDS.items():
        hubs1 = wilaya_hubs.get(wid1, [])
        for wid2, (lat2, lon2) in WILAYA_COORDS.items():
            if wid1 >= wid2:
                continue
            if (wid1, wid2) in connected_pairs:
                continue
            dist = haversine_km(lat1, lon1, lat2, lon2)
            if dist > 250:
                continue

            # Connect main hub of each
            h1 = max(hubs1, key=lambda h: h.get("latitude", 0)) if hubs1 else None
            h2 = max(wilaya_hubs.get(wid2, []), key=lambda h: h.get("latitude", 0)) if wilaya_hubs.get(wid2) else None
            if not h1 or not h2:
                continue

            dur = max(30, int(dist / 60 * 60))
            fn = WILAYA_NAMES[wid1]
            tn = WILAYA_NAMES[wid2]
            for fwd, rev in [(True, "forward"), (False, "backward")]:
                f, t = (h1["node_id"], h2["node_id"]) if fwd else (h2["node_id"], h1["node_id"])
                eid = f"EDGE_INTERCITY_{fn[:6]}_{tn[:6]}_{rev[:3]}".upper()
                inter_city_edges.append({
                    "edge_id": eid,
                    "from_node_id": f,
                    "to_node_id": t,
                    "mode": "intercity",
                    "subtype": "road",
                    "operator": "Estimation ATHAR",
                    "line_id": f"ATHAR_CONNECT_{fn[:6]}_{tn[:6]}".upper(),
                    "line_name": f"{fn} ↔ {tn}",
                    "direction": rev,
                    "distance_km": round(dist, 1),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 60,
                    "pricing": {"estimated_dzd": int(dist * 10), "note": "Estimated pricing"},
                    "schedule": {
                        "first_departure": "05:00",
                        "last_departure": "20:00",
                        "frequency_min": 60,
                        "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    },
                    "first_departure": "05:00",
                    "last_departure": "20:00",
                    "metadata": {"source": "connectivity_overlay", "estimated": True},
                })
            connected_pairs.add((wid1, wid2))
            connected_pairs.add((wid2, wid1))
            new_connections += 1

    print(f"New inter-city connections added: {new_connections}")
    print(f"Total connected pairs: {len(connected_pairs)//2}")

    # --- Phase 4: Build transport line index ---
    print("\n--- Phase 4: Build transport line index ---")

    # Collect all lines with their stops
    transport_lines = defaultdict(lambda: {
        "line_id": "",
        "line_name": "",
        "mode": "",
        "operator": "",
        "stops": [],
        "edges": [],
        "total_distance_km": 0,
        "total_duration_min": 0,
        "stop_count": 0,
        "pricing": {},
    })

    all_transport = [e for e in non_sogral if e.get("mode") in ("bus", "train", "tram", "metro", "cablecar", "ferry", "flight")]
    for e in all_transport:
        lid = e.get("line_id", "")
        if not lid:
            continue
        tl = transport_lines[lid]
        if not tl["line_id"]:
            tl["line_id"] = lid
            tl["line_name"] = e.get("line_name", "")
            tl["mode"] = e.get("mode", "")
            tl["operator"] = e.get("operator", "")
        if e["from_node_id"] not in tl["stops"]:
            tl["stops"].append(e["from_node_id"])
        if e["to_node_id"] not in tl["stops"]:
            tl["stops"].append(e["to_node_id"])
        tl["edges"].append(e["edge_id"])
        tl["total_distance_km"] += e.get("distance_km", 0)
        tl["total_duration_min"] += e.get("duration_min", 0)
        tl["stop_count"] = len(tl["stops"])
        tl["pricing"] = e.get("pricing", {})

    # Also include taxi routes
    for lid in set(e["line_id"] for e in taxi_grouped):
        if lid not in transport_lines:
            routes_edges = [e for e in taxi_grouped if e["line_id"] == lid]
            if routes_edges:
                tl = transport_lines[lid]
                tl["line_id"] = lid
                tl["line_name"] = routes_edges[0].get("line_name", lid)
                tl["mode"] = "taxi"
                tl["operator"] = "Taxi"
                for e in routes_edges:
                    if e["from_node_id"] not in tl["stops"]:
                        tl["stops"].append(e["from_node_id"])
                    if e["to_node_id"] not in tl["stops"]:
                        tl["stops"].append(e["to_node_id"])
                    tl["edges"].append(e["edge_id"])
                    tl["total_distance_km"] += e.get("distance_km", 0)
                    tl["total_duration_min"] += e.get("duration_min", 0)
                    tl["stop_count"] = len(tl["stops"])

    print(f"Unique transport lines indexed: {len(transport_lines)}")
    mode_counts = defaultdict(int)
    for tl in transport_lines.values():
        mode_counts[tl["mode"]] += 1
    for m, c in sorted(mode_counts.items()):
        print(f"  {m:10s}: {c} lines")

    # --- Phase 5: Update node `lines_at_station` ---
    print("\n--- Phase 5: Update station line lists ---")

    for lid, tl in transport_lines.items():
        for sid in tl["stops"]:
            n = nodes.get(sid)
            if n and lid not in n.get("lines_at_station", []):
                if "lines_at_station" not in n:
                    n["lines_at_station"] = []
                n["lines_at_station"].append(lid)

    # --- Phase 6: Save updated graph ---
    print("\n--- Phase 6: Save updated graph ---")

    # Reassemble all edges
    all_edge_updates = inter_city_edges + taxi_grouped + non_sogral
    # Dedup by edge_id
    seen_eids = set()
    deduped_edges = []
    for e in all_edge_updates:
        if e["edge_id"] not in seen_eids:
            seen_eids.add(e["edge_id"])
            deduped_edges.append(e)

    NODES_PATH.write_text(json.dumps(nodes_list, ensure_ascii=False, indent=2))
    EDGES_PATH.write_text(json.dumps(deduped_edges, ensure_ascii=False, indent=2))

    print(f"Final transit nodes: {len(nodes_list)}")
    print(f"Final transit edges: {len(deduped_edges)}")

    # --- Phase 7: Populate DB tables ---
    print("\n--- Phase 7: Seed stations, transport_lines, line_stops tables ---")

    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        # Stations: all transport nodes with lat/lon
        conn.execute(text("TRUNCATE TABLE line_stops RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE transport_lines RESTART IDENTITY CASCADE"))
        conn.execute(text("TRUNCATE TABLE stations RESTART IDENTITY CASCADE"))

        transport_types = {"bus", "train", "tram", "taxi", "airport", "cablecar", "metro", "ferry", "virtual_hub"}
        station_count = 0
        for n in nodes_list:
            if n.get("type") not in transport_types:
                continue
            conn.execute(
                text("""
                    INSERT INTO stations
                        (id, name, station_type, operator, wilaya_id, latitude, longitude, is_active)
                    VALUES
                        (gen_random_uuid(), :name, :stype, :op, :wilaya_id, :lat, :lon, true)
                """),
                {
                    "name": n.get("name", "Station")[:200],
                    "stype": (n.get("type") or "bus")[:20],
                    "op": ((n.get("operator") or "Various")[:30]),
                    "wilaya_id": n.get("wilaya_id", 1),
                    "lat": n.get("latitude", 0),
                    "lon": n.get("longitude", 0),
                },
            )
            station_count += 1
        print(f"Stations inserted: {station_count}")

        # Transport lines
        line_count = 0
        for tl in transport_lines.values():
            conn.execute(
                text("""
                    INSERT INTO transport_lines
                        (id, name, operator, mode, distance_km, description, color, is_active)
                    VALUES
                        (gen_random_uuid(), :name, :op, :mode, :dist, :desc, :color, true)
                """),
                {
                    "name": f"{tl['mode'].title()} {tl['line_name']}"[:200],
                    "op": (tl["operator"] or "Various")[:30],
                    "mode": tl["mode"][:20],
                    "dist": tl["total_distance_km"],
                    "desc": f"{len(tl['stops'])} arrêts, {len(tl['edges'])} segments"[:500],
                    "color": None,
                },
            )
            line_count += 1
        print(f"Transport lines inserted: {line_count}")

        # Inter-city connections as transport lines
        for lid, lname, mode, op in [
            ("TAXI_INTER_CITY", "Taxi Inter-Villes", "taxi", "Taxi"),
            ("SOGRAL_INTER_CITY", "SOGRAL Inter-Villes", "bus", "SOGRAL"),
            ("ATHAR_INTER_CITY", "ATHAR Connect", "intercity", "Estimation"),
        ]:
            conn.execute(
                text("""
                    INSERT INTO transport_lines
                        (id, name, operator, mode, description, is_active)
                    VALUES
                        (gen_random_uuid(), :name, :op, :mode, :desc, true)
                """),
                {"name": lname, "op": op, "mode": mode, "desc": f"Réseau {lname}"[:500]},
            )
        print("Extra inter-city lines inserted")

    print(f"\n{'='*50}")
    print("Transport organization complete!")
    print(f"Total nodes: {len(nodes_list)}")
    print(f"Total edges: {len(deduped_edges)}")
    print(f"Taxi routes: {len(taxi_routes)}")
    print(f"Transport lines in DB: ~{line_count + 3}")
    print(f"Inter-city connections: {new_connections} new pairs")


if __name__ == "__main__":
    main()
