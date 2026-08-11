#!/usr/bin/env python3
"""Insert real OSM route=bus relations from the local Geofabrik PBF into the DB.

Append-only (no TRUNCATE). Extracts ordered stop sequences for route=bus
relations that have stop NODE members (not way geometry), and seeds one
transport_line per relation plus its line_stops. Stations are matched to
existing rows by rounded coordinates + station_type=bus, else created.

Targets the routes missing from the DB:
  - Batna ligne 03 (17 stops)          — Batna had no bus coverage
  - Sétif ETUS 101 / 104 / 106 aller/retour (20–109 stops)
"""

import json
import math
import os
import re
import uuid

import osmium
from sqlalchemy import create_engine, text

from app.core.config import settings

DATABASE_URL = settings.database.url.replace("+asyncpg", "")
PBF = "scripts/data/raw/osm/algeria-latest.osm.pbf"
STOP_CACHE = "/var/folders/_f/5f5skv_d26v8ffs4fs8bjq900000gn/T/opencode/batna_setif.json"
REL_IDS = {18591051, 14596722, 14608521, 14616622, 14618940}


def haversine_km(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * 6371 * math.asin(min(1, math.sqrt(a)))


def collect_relations():
    class RelHandler(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.rels = {}

        def relation(self, r):
            if r.id in REL_IDS:
                self.rels[r.id] = dict(r.tags)

    relh = RelHandler()
    relh.apply_file(PBF)
    return relh.rels


def collect_stop_names():
    """Return {osm_node_id: (name, name_ar, name_fr)} for the cached stops."""
    cache = json.load(open(STOP_CACHE))
    wanted = set()
    for info in cache.values():
        for s in info["stops"]:
            wanted.add(s["id"])
    names = {}

    class NodeHandler(osmium.SimpleHandler):
        def node(self, n):
            if n.id in wanted and n.tags.get("name"):
                names[n.id] = (
                    n.tags.get("name", ""),
                    n.tags.get("name:ar", ""),
                    n.tags.get("name:fr", ""),
                )

    h = NodeHandler()
    h.apply_file(PBF)
    return names


def main():
    data = json.load(open(STOP_CACHE))
    tags = collect_relations()
    stop_names = collect_stop_names()
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        existing_bus = {}
        for r in conn.execute(
            text("SELECT id, latitude, longitude FROM stations WHERE station_type='bus'")
        ):
            existing_bus[(round(r[1], 4), round(r[2], 4))] = r[0]
        existing_lines = set(
            conn.execute(text("SELECT name FROM transport_lines")).scalars()
        )
        centers = {
            row[0]: (row[1], row[2])
            for row in conn.execute(text("SELECT id, latitude, longitude FROM wilayas"))
        }

        def wilaya_for(lat, lon):
            best = min(
                centers.items(),
                key=lambda kv: haversine_km(lat, lon, kv[1][0], kv[1][1]),
            )
            return best[0]

        for rid, info in data.items():
            stops = info["stops"]
            if len(stops) < 2:
                print(f"relation {rid}: skip ({len(stops)} stops)")
                continue
            tag = tags.get(int(rid), {})
            name = tag.get("name") or ""
            ref = tag.get("ref") or ""
            op = tag.get("operator") or tag.get("network") or "Various"
            # prefer the descriptive relation name over the bare ref so that
            # e.g. Sétif "ETUS SETIF 104" is distinguishable from "101"
            line_name = name or f"Ligne {ref}"
            full_name = f"Bus {line_name}"[:200]
            if full_name in existing_lines:
                print(f"relation {rid}: '{full_name}' already in DB, skip")
                continue

            mode = tag.get("route") or "bus"
            line_id = uuid.uuid4()
            total_km = sum(
                haversine_km(stops[i]["lat"], stops[i]["lon"], stops[i + 1]["lat"], stops[i + 1]["lon"])
                for i in range(len(stops) - 1)
            )
            conn.execute(
                text(
                    """INSERT INTO transport_lines
                       (id, name, operator, mode, distance_km, description, is_active)
                       VALUES (:id, :name, :op, :mode, :dist, :desc, true)"""
                ),
                {
                    "id": line_id,
                    "name": full_name,
                    "op": (op or "Various")[:30],
                    "mode": mode[:20],
                    "dist": round(total_km, 2),
                    "desc": f"{len(stops)} arrêts (OSM route={rid})"[:500],
                },
            )

            dist_from_start = 0.0
            time_from_start = 0
            for i, s in enumerate(stops):
                if i > 0:
                    seg = haversine_km(
                        stops[i - 1]["lat"], stops[i - 1]["lon"], s["lat"], s["lon"]
                    )
                    dist_from_start += seg
                    time_from_start += max(1, round(seg * 2.0))
                key = (round(s["lat"], 4), round(s["lon"], 4))
                station_id = existing_bus.get(key)
                if station_id is None:
                    station_id = uuid.uuid4()
                    sn = stop_names.get(s["id"])
                    if sn:
                        sname = sn[0]
                        sname_ar = sn[1]
                    else:
                        sname = f"Arrêt {line_name} {i + 1}"
                        sname_ar = ""
                    conn.execute(
                        text(
                            """INSERT INTO stations
                               (id, name, name_ar, station_type, wilaya_id, latitude, longitude, operator, is_active)
                               VALUES (:id, :n, :nar, 'bus', :w, :la, :lo, :op, true)"""
                        ),
                        {
                            "id": station_id,
                            "n": sname[:200],
                            "nar": sname_ar[:200],
                            "w": wilaya_for(s["lat"], s["lon"]),
                            "la": s["lat"],
                            "lo": s["lon"],
                            "op": (op or "Various")[:30],
                        },
                    )
                    existing_bus[key] = station_id
                conn.execute(
                    text(
                        """INSERT INTO line_stops
                           (id, line_id, station_id, stop_order, distance_from_start_km, travel_time_from_start_min)
                           VALUES (:lsid, :lid, :sid, :ord, :dist, :time)"""
                    ),
                    {
                        "lsid": uuid.uuid4(),
                        "lid": line_id,
                        "sid": station_id,
                        "ord": i,
                        "dist": round(dist_from_start, 2),
                        "time": time_from_start,
                    },
                )
            print(
                f"relation {rid}: '{full_name}' — {len(stops)} stops, "
                f"{round(total_km, 2)} km (operator {op})"
            )

    print("done")


if __name__ == "__main__":
    main()
