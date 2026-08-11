"""Connect orphaned stations to the transit network via walking transfers.

231 stations in `stations` have no `line_stops` (202 bus, 19 train, 6 tram,
2 taxi, 1 ferry, 1 virtual_hub) — they are unreachable in the DB-based
routing graph (`TransitGraph.load`), because routing edges only exist between
consecutive stops of a line.

This script inserts walking-transfer edges (`transfers` table) from each
orphan station to its nearest *served* station (one that belongs to ≥1 line)
using a grid-based spatial index over the served stations. Walking time is
estimated at 80 m/min (4.8 km/h), capped so absurd cross-country walks are
dropped (default max 5 km — a longer walk is not a useful routing transfer).

Idempotent: the transfers table has a unique index on the unordered
station pair, so re-runs are no-ops (INSERT ... ON CONFLICT DO NOTHING).
Reports written to scripts/data/reports/connect_orphans_{dryrun,run,verify}.txt
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings

REPORT_DIR = Path("scripts/data/reports")
DATABASE_URL = settings.database.url.replace("+asyncpg", "")
WALKING_M_PER_MIN = 80.0
MAX_WALK_KM = 5.0
GRID_CELL_KM = 1.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _cell(lat: float, lng: float, cell_deg: float) -> tuple[int, int]:
    return (int(lat / cell_deg), int(lng / cell_deg))


def _ring_cells(r: int):
    """Cells at Chebyshev distance exactly r from the origin (perimeter only)."""
    if r <= 0:
        yield (0, 0)
        return
    for x in range(-r, r + 1):
        yield (x, -r)
        yield (x, r)
    for y in range(-r + 1, r):
        yield (-r, y)
        yield (r, y)


class GridIndex:
    """Grid-based spatial index over the served stations."""

    def __init__(self, served: list[dict], cell_deg: float) -> None:
        self.cell_deg = cell_deg
        self.grid: dict[tuple[int, int], list[dict]] = {}
        for s in served:
            self.grid.setdefault(_cell(s["latitude"], s["longitude"], cell_deg), []).append(s)

    def nearest(self, lat: float, lng: float, max_km: float) -> dict | None:
        c = _cell(lat, lng, self.cell_deg)
        best, best_d = None, float("inf")
        km_per_cell = self.cell_deg * 111.0
        # +1 ring: cells are ~90 km/deg east-west at Algeria's latitude, so a
        # square ring under-estimates east-west reach slightly. The strict
        # best_d <= max_km check below keeps the returned edge honest.
        max_r = int(max_km / km_per_cell) + 1
        for r in range(max_r + 1):
            if r * km_per_cell > best_d:
                break
            for dx, dy in _ring_cells(r):
                for s in self.grid.get((c[0] + dx, c[1] + dy), []):
                    d = _haversine_km(lat, lng, s["latitude"], s["longitude"])
                    if d < best_d:
                        best, best_d = s, d
        if best is not None and best_d <= max_km:
            return best
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Connect orphan stations via walking transfers")
    parser.add_argument("--dryrun", action="store_true", help="Report only, no writes")
    parser.add_argument("--max-walk-km", type=float, default=MAX_WALK_KM)
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    pairs: list[tuple[dict, dict, float, float]] = []  # (orphan, target, km, min)
    with engine.begin() as conn:
        stations = conn.execute(
            text("SELECT id, name, station_type, latitude, longitude FROM stations")
        ).fetchall()
        served_ids = {
            r[0]
            for r in conn.execute(
                text("SELECT DISTINCT station_id FROM line_stops")
            ).fetchall()
        }
        served = [dict(s._mapping) for s in stations if s.id in served_ids]
        orphans = [dict(s._mapping) for s in stations if s.id not in served_ids]

        index = GridIndex(served, GRID_CELL_KM / 111.0)
        unmatched = 0
        for o in orphans:
            target = index.nearest(o["latitude"], o["longitude"], args.max_walk_km)
            if target is None:
                unmatched += 1
                continue
            km = _haversine_km(
                o["latitude"], o["longitude"], target["latitude"], target["longitude"]
            )
            pairs.append((o, target, km, km * 1000.0 / WALKING_M_PER_MIN))

        print(f"Served stations: {len(served)}")
        print(f"Orphan stations: {len(orphans)}")
        print(f"Transfers to create: {len(pairs)} (unmatched: {unmatched})")

        if not args.dryrun:
            for o, t, km, minutes in pairs:
                conn.execute(
                    text(
                        """
                        INSERT INTO transfers
                          (id, from_station_id, to_station_id, distance_m,
                           walking_time_min, source)
                        VALUES (:id, :a, :b, :d, :m, 'orphan_connect')
                        ON CONFLICT DO NOTHING
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "a": o["id"],
                        "b": t["id"],
                        "d": round(km * 1000.0, 1),
                        "m": round(minutes, 1),
                    },
                )
            print(f"Inserted {len(pairs)} transfers")

    # Reports
    by_type: dict[str, int] = {}
    total_min = 0.0
    for o, _t, _km, minutes in pairs:
        by_type[o["station_type"]] = by_type.get(o["station_type"], 0) + 1
        total_min += minutes
    report = REPORT_DIR / f"connect_orphans_{'dryrun' if args.dryrun else 'run'}.txt"
    report.write_text(
        json.dumps(
            {
                "served_stations": len(served),
                "orphan_stations": len(orphans),
                "transfers_created": len(pairs),
                "unmatched": unmatched,
                "by_orphan_type": by_type,
                "avg_walking_min": round(total_min / len(pairs), 1) if pairs else None,
                "sample": [
                    {
                        "orphan": o["name"] or f"({o['station_type']})",
                        "to": t["name"],
                        "walk_km": round(km, 2),
                        "walk_min": round(minutes, 1),
                    }
                    for o, t, km, minutes in pairs[:8]
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
