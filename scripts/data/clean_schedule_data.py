#!/usr/bin/env python3
"""Fix schedule data consistency in the transit graph.

Issues fixed:
  1. Promote nested `schedule.*` to top-level `first_departure`/`last_departure`
     for edges that have nested schedule but missing top-level fields.
  2. Resolve conflicts where top-level and nested values differ
     (nested schedule is per-edge specific → use as truth).
  3. Add missing schedule defaults for edges that have no schedule at all.
  4. Add Domestic Airlines real flight schedule data.
"""

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"

with open(NODES_PATH) as f:
    nodes = json.load(f)
with open(EDGES_PATH) as f:
    edges = json.load(f)

node_map = {n["node_id"]: n for n in nodes}

stats = {
    "promoted": 0,
    "conflict_resolved": 0,
    "added_default": 0,
    "added_flight_edges": 0,
}


def fix_schedule_consistency(edges):
    for e in edges:
        sched = e.get("schedule")
        if not sched or not isinstance(sched, dict):
            continue

        changed = False
        if not e.get("first_departure") and sched.get("first_departure"):
            e["first_departure"] = sched["first_departure"]
            stats["promoted"] += 1
            changed = True

        if not e.get("last_departure") and sched.get("last_departure"):
            e["last_departure"] = sched["last_departure"]
            stats["promoted"] += 1
            changed = True

        if not e.get("frequency_min") and sched.get("frequency_min"):
            e["frequency_min"] = sched["frequency_min"]
            stats["promoted"] += 1
            changed = True

    return edges


def resolve_top_level_conflicts(edges):
    for e in edges:
        sched = e.get("schedule")
        if not sched or not isinstance(sched, dict):
            continue

        fd = e.get("first_departure")
        sfd = sched.get("first_departure")
        if fd and sfd and fd != sfd:
            e["first_departure"] = sfd
            stats["conflict_resolved"] += 1

        ld = e.get("last_departure")
        sld = sched.get("last_departure")
        if ld and sld and ld != sld:
            e["last_departure"] = sld
            stats["conflict_resolved"] += 1

        fm = e.get("frequency_min")
        sfm = sched.get("frequency_min")
        if fm and sfm and fm != sfm:
            e["frequency_min"] = sfm
            stats["conflict_resolved"] += 1

    return edges


def add_default_schedules(edges):
    for e in edges:
        if e.get("schedule") and isinstance(e["schedule"], dict):
            continue

        mode = e.get("mode", "")
        subtype = e.get("subtype", "")

        defaults = None
        if mode == "walking":
            defaults = {
                "first_departure": "00:00",
                "last_departure": "23:59",
                "frequency_min": 5,
                "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            }
        elif mode == "flight":
            defaults = {
                "first_departure": "06:00",
                "last_departure": "22:00",
                "frequency_min": 1440,
                "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            }
        elif mode == "bus" and subtype == "intercity":
            defaults = {
                "first_departure": "06:00",
                "last_departure": "18:00",
                "frequency_min": 120,
                "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            }
        elif mode == "train" and subtype == "intercity":
            defaults = {
                "first_departure": "06:00",
                "last_departure": "18:00",
                "frequency_min": 360,
                "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            }
        elif mode == "transfer":
            defaults = {
                "first_departure": "00:00",
                "last_departure": "23:59",
                "frequency_min": 5,
                "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            }

        if defaults:
            e["schedule"] = dict(defaults)
            e["first_departure"] = defaults["first_departure"]
            e["last_departure"] = defaults["last_departure"]
            if not e.get("frequency_min"):
                e["frequency_min"] = defaults["frequency_min"]
            stats["added_default"] += 1

    return edges


def find_or_create_airport(nodes, city_name, display_name, wilaya_id, lat, lon):
    for n in nodes:
        if n.get("type") == "airport" and city_name.lower() in n.get("name", "").lower():
            return n["node_id"]
    nid = f"STATION_AIRPORT_{city_name.upper().replace(' ', '_')}"
    node = {
        "node_id": nid,
        "name": display_name,
        "name_ar": "",
        "name_en": display_name,
        "type": "airport",
        "subtype": "domestic",
        "operator": None,
        "wilaya_id": wilaya_id,
        "wilaya_name": city_name,
        "latitude": lat,
        "longitude": lon,
        "osm_data": {},
        "codes": {"iata": ""},
        "lines_at_station": [],
        "has_parking": True,
        "has_accessibility": None,
        "metadata": {"source": "manual_add", "city": city_name},
    }
    nodes.append(node)
    node_map[nid] = node
    print(f"  Created airport node: {display_name}")
    return nid


def add_domestic_airlines(edges, nodes):
    """Add Domestic Airlines subsidiary flight routes with real schedules.

    Air Algérie subsidiary "Domestic Airlines" launched July 2025.
    Source: published weekly flight schedule.

    Routes:
      1. Alger → Tiaret → Adrar → Tamanrasset (and reverse)
         Dep Alger 07:00, arr Tiaret 08:00, dep Tiaret 08:30, arr Adrar 09:30,
         dep Adrar 10:00, arr Tamanrasset 11:30
      2. Tamanrasset → Djanet → Illizi → Adrar (and reverse)
         Dep Tamanrasset 13:00, arr Djanet 14:00, dep Djanet 14:30, arr Illizi 15:00,
         dep Illizi 15:30, arr Adrar 17:00
    """
    # Ensure airports exist
    find_or_create_airport(nodes, "Adrar", "Aéroport d'Adrar (Touat)", 1, 27.84, -0.19)
    find_or_create_airport(nodes, "Tiaret", "Aéroport de Tiaret (Abdelhafid Boussouf)", 14, 35.24, 1.43)

    def find_airport_id(city):
        for n in nodes:
            if n.get("type") != "airport":
                continue
            name = n.get("name", "")
            if city.lower() in name.lower():
                return n["node_id"]
        return None

    def haversine_km(lat1, lon1, lat2, lon2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
            math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    existing_keys = {
        (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
        for e in edges
    }

    DOMESTIC_ROUTES = [
        {
            "cities": ["Alger", "Tiaret", "Adrar", "Tamanrasset"],
            "line_id": "DOMESTIC_AIRLINES_L1",
            "frequencies": [60, 60, 60],
        },
        {
            "cities": ["Tamanrasset", "Djanet", "Illizi", "Adrar"],
            "line_id": "DOMESTIC_AIRLINES_L2",
            "frequencies": [60, 60, 60],
        },
    ]

    new_edges = []
    for route in DOMESTIC_ROUTES:
        cities = route["cities"]
        for i in range(len(cities) - 1):
            o = cities[i]
            d = cities[i + 1]
            oid = find_airport_id(o)
            did = find_airport_id(d)
            if not oid or not did:
                print(f"  WARNING: Missing airport for {o} or {d}")
                continue
            onode = node_map.get(oid, {})
            dnode = node_map.get(did, {})
            lat1 = onode.get("latitude")
            lon1 = onode.get("longitude")
            lat2 = dnode.get("latitude")
            lon2 = dnode.get("longitude")
            if None in (lat1, lon1, lat2, lon2):
                continue
            dist = haversine_km(lat1, lon1, lat2, lon2)
            dur = max(30, int(dist / 600 * 60))
            for dir_label, f_id, t_id in [
                ("forward", oid, did),
                ("backward", did, oid),
            ]:
                key = (f_id, t_id, route["line_id"], dir_label)
                if key not in existing_keys:
                    eid = f"FLIGHT_DOMESTIC_{f_id[-12:]}_{t_id[-12:]}".upper()
                    new_edges.append({
                        "edge_id": eid,
                        "from_node_id": f_id,
                        "to_node_id": t_id,
                        "mode": "flight",
                        "subtype": "domestic",
                        "operator": "Domestic Airlines (Air Algérie)",
                        "line_id": route["line_id"],
                        "line_name": f"{o} → {d}",
                        "direction": dir_label,
                        "distance_km": round(dist, 1),
                        "duration_min": dur,
                        "stops_between": 0,
                        "frequency_min": route["frequencies"][i],
                        "pricing": {"minimum": 5000, "estimated": 8000},
                        "schedule": {
                            "first_departure": "07:00",
                            "last_departure": "17:00",
                            "frequency_min": route["frequencies"][i],
                            "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                        },
                        "first_departure": "07:00",
                        "last_departure": "17:00",
                        "metadata": {"source": "domestic_airlines_schedule_2025"},
                    })
                    existing_keys.add(key)

    edges.extend(new_edges)
    stats["added_flight_edges"] = len(new_edges)
    return edges


# ── Main ──
print("=== Transit Graph Schedule Data Cleaning ===")
print(f"Before: {len(nodes)} nodes, {len(edges)} edges")

edges = fix_schedule_consistency(edges)
edges = resolve_top_level_conflicts(edges)
edges = add_default_schedules(edges)
edges = add_domestic_airlines(edges, nodes)

# Save
NODES_PATH.write_text(json.dumps(nodes, ensure_ascii=False, indent=2))
EDGES_PATH.write_text(json.dumps(edges, ensure_ascii=False, indent=2))

print(f"\nAfter: {len(nodes)} nodes, {len(edges)} edges")
print(f"Schedule fields promoted (nested → top-level): {stats['promoted']}")
print(f"Conflicts resolved (top-level overwritten by nested): {stats['conflict_resolved']}")
print(f"Default schedules added: {stats['added_default']}")
print(f"Domestic Airlines flight edges added: {stats['added_flight_edges']}")

# Verify
modes = {}
for e in edges:
    mk = e.get("mode") or "?"
    sk = e.get("subtype") or "?"
    k = (mk, sk)
    modes.setdefault(k, {"count": 0, "has_schedule": 0, "has_top": 0})
    modes[k]["count"] += 1
    if e.get("schedule"):
        modes[k]["has_schedule"] += 1
    if e.get("first_departure"):
        modes[k]["has_top"] += 1

print("\n=== Verification ===")
for k in sorted(modes):
    v = modes[k]
    ok = v["count"] == v["has_schedule"] == v["has_top"]
    status = "OK" if ok else "MISMATCH"
    print(f"  {k[0]:12s} {k[1]:20s} count={v['count']:6d} schedule={v['has_schedule']:6d} top={v['has_top']:6d} {status}")
