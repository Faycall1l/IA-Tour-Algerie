#!/usr/bin/env python3
"""Clean up bus data and add transfer edges between bus stops and existing transit.

Usage:
  python scripts/data/cleanup_and_transfers.py
"""
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def main():
    nodes = json.loads(NODES_PATH.read_text())
    edges = json.loads(EDGES_PATH.read_text())
    node_map = {n["node_id"]: n for n in nodes}

    # ── Cleanup ──
    before = len(edges)

    # Remove intra-wilaya taxi (wrongly tagged as bus in OSM)
    edges = [e for e in edges if "Intra-wilaya taxi" not in e.get("line_id", "")]
    print(f"Removed {before - len(edges)} intra-wilaya taxi edges")

    # Remove very short urban bus edges (< 50m — duplicate stop positions)
    before2 = len(edges)
    edges = [e for e in edges if not (e.get("subtype") == "urban" and e.get("distance_km", 1) < 0.05)]
    print(f"Removed {before2 - len(edges)} very short urban bus edges")

    # ── Transfer edges: bus stops ↔ metro/train/tram within 500m ──
    transit_types = {"metro", "train", "tram"}
    transit_nodes = {n["node_id"]: n for n in nodes if n.get("type") in transit_types and n.get("latitude")}
    bus_nodes = {n["node_id"]: n for n in nodes if n.get("type") == "bus" and n.get("subtype") == "urban" and n.get("latitude")}

    existing_edge_keys = {(e["from_node_id"], e["to_node_id"], e.get("mode", "")) for e in edges}

    new_edges = []
    added = 0

    for bid, bn in bus_nodes.items():
        for tid, tn in transit_nodes.items():
            d = haversine_km(bn["latitude"], bn["longitude"], tn["latitude"], tn["longitude"])
            if d <= 0.5:
                key = (bid, tid, "transfer")
                if key not in existing_edge_keys:
                    duration = max(1, int(d / 0.083))
                    eid = f"EDGE_TRANSFER_BUS_{bid[-20:]}_{tid[-20:]}".upper()
                    new_edges.append({
                        "edge_id": eid,
                        "from_node_id": bid,
                        "to_node_id": tid,
                        "mode": "transfer",
                        "subtype": "walking",
                        "operator": "",
                        "line_id": "TRANSFER",
                        "line_name": "Transfert (Marche)",
                        "direction": "forward",
                        "distance_km": round(d, 3),
                        "duration_min": duration,
                        "stops_between": 0,
                        "frequency_min": 5,
                        "pricing": {"single": 0},
                        "schedule": {
                            "first_departure": "00:00",
                            "last_departure": "23:59",
                            "frequency_min": 5,
                            "operating_days": [
                                "Monday", "Tuesday", "Wednesday", "Thursday",
                                "Friday", "Saturday", "Sunday",
                            ],
                            "destination": tn.get("name", ""),
                        },
                        "metadata": {"source": "generated"},
                    })
                    existing_edge_keys.add(key)
                    added += 1

    edges.extend(new_edges)
    print(f"Added {added} bus ↔ transit transfer edges")

    # ── Summary ──
    print(f"\nTotal edges: {len(edges)}")
    print(f"Total nodes: {len(nodes)}")
    mode_counts = defaultdict(int)
    for e in edges:
        mode_counts[e["mode"]] += 1
    for m, c in sorted(mode_counts.items()):
        lines = len({e.get("line_id", "") for e in edges if e["mode"] == m})
        print(f"  {m:10s}: {c:5d} edges, {lines:3d} lines")

    EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))
    print(f"\nSaved to {EDGES_PATH}")


if __name__ == "__main__":
    main()
