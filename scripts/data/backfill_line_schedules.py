"""Backfill `transport_lines.schedule_info` / `pricing_info` from the transit graph.

The authoritative schedule data lives on the transit edges
(`app/data/transit_edges_enriched.json`, 34,921 edges — every edge carries
`first_departure`, `last_departure`, `frequency_min` and `pricing`), but the
`transport_lines` DB rows were seeded without those two JSON columns (they
are all NULL).

This script re-derives the per-line schedule/pricing exactly the way
`organize_transport.py` Phase 4 grouped edges into lines (by `line_id`), maps
each derived line to its `transport_lines` row, and writes back:

  schedule_info = {
    "first_departure": <earliest first_departure across the line's edges>,
    "last_departure":  <latest last_departure>,
    "frequency_min":   <range or single value>,
    "has_schedule": true,
  }
  pricing_info = {
    "per_person": <dominant per_person price in DZD>,
    "min_dzd": <min> | "max_dzd": <max>,
    "currency": "DZD",
  }

Mapping edge-line -> DB line:
  1. Exact: `{mode.title()} {line_name}` (the name construction used by
     organize_transport.py Phase 7), normalized (case/accents/whitespace).
  2. Fallback: stop-set overlap — DB line whose station names best match the
     edge endpoints' station names (Jaccard over normalized names).

Idempotent: re-running updates in place. Reports written to
`scripts/data/reports/backfill_schedules_{dryrun,run,verify,qa}.txt`.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings

EDGES_PATH = Path("app/data/transit_edges_enriched.json")
NODES_PATH = Path("app/data/transit_nodes_enriched.json")
REPORT_DIR = Path("scripts/data/reports")
DATABASE_URL = settings.database.url.replace("+asyncpg", "")
LINE_MODES = {"bus", "train", "tram", "metro", "cablecar", "ferry", "flight", "taxi"}


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value).lower())
    value = re.sub(r"[\u0300-\u036f]", "", value)
    value = re.sub(r"[’']", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _group_edges_by_line(edges: list[dict]) -> dict[str, dict]:
    """Re-derive the per-line index the way organize_transport.py Phase 4 did."""
    lines: dict[str, dict] = {}
    transport_edges = [
        e for e in edges if e.get("mode") in LINE_MODES and e.get("line_id")
    ]
    for e in transport_edges:
        lid = e["line_id"]
        tl = lines.setdefault(
            lid,
            {
                "line_id": lid,
                "line_name": "",
                "mode": "",
                "operator": "",
                "stop_names": [],
                "edges": 0,
                "distance_km": 0,
                "duration_min": 0,
            },
        )
        if not tl["line_name"]:
            tl["line_name"] = e.get("line_name", "")
            tl["mode"] = e.get("mode", "")
            tl["operator"] = e.get("operator", "")
        tl["stop_names"].append(e.get("from_name") or e.get("from_node_id"))
        tl["stop_names"].append(e.get("to_name") or e.get("to_node_id"))
        tl["edges"] += 1
        tl["distance_km"] += e.get("distance_km", 0)
        tl["duration_min"] += e.get("duration_min", 0)
    return lines


def _edge_schedules(edges: list[dict]) -> dict:
    firsts = [
        e["first_departure"]
        for e in edges
        if e.get("first_departure")
    ]
    lasts = [e["last_departure"] for e in edges if e.get("last_departure")]
    freqs = [int(e["frequency_min"]) for e in edges if e.get("frequency_min")]
    if not (firsts or freqs):
        return {}
    return {
        "first_departure": min(firsts) if firsts else None,
        "last_departure": max(lasts) if lasts else None,
        "frequency_min": (
            {"min": min(freqs), "max": max(freqs)} if len(freqs) > 1 else freqs[0]
        ),
        "has_schedule": True,
    }


def _edge_pricing(edges: list[dict]) -> dict | None:
    prices = []
    fare_types: set[str] = set()
    for e in edges:
        p = e.get("pricing") or {}
        if isinstance(p, dict):
            if p.get("per_person"):
                prices.append(float(p["per_person"]))
                fare_types.add("per_person")
            elif p.get("single"):
                prices.append(float(p["single"]))
                fare_types.add("single")
            elif p.get("estimated_total"):
                prices.append(float(p["estimated_total"]))
                fare_types.add("estimated_total")
            if p.get("economy_min"):
                prices.append(float(p["economy_min"]))
                fare_types.add("economy")
                if p.get("economy_max"):
                    prices.append(float(p["economy_max"]))
        elif isinstance(p, (int, float)) and p:
            prices.append(float(p))
    if not prices:
        return None
    most_common = Counter(prices).most_common(1)[0][0]
    return {
        "per_person": most_common,
        "min_dzd": min(prices),
        "max_dzd": max(prices),
        "currency": "DZD",
        "fare_type": sorted(fare_types),
    }


def _candidate_names(line: dict) -> list[str]:
    mode = line["mode"]
    lname = line["line_name"]
    cands = []
    for base in (lname, line["line_id"]):
        if not base:
            continue
        cands.append(f"{mode.title()} {base}")
        cands.append(base)
    return [c for c in cands if c.strip()]


def build_name_index(conn) -> dict[str, int]:
    """Map normalized DB line name -> line id, keeping the shortest name."""
    index: dict[str, int] = {}
    rows = conn.execute(
        text("SELECT id, name, mode FROM transport_lines")
    ).fetchall()
    for lid, name, mode in rows:
        key = _norm(name)
        if key and key not in index:
            index[key] = lid
    return index


def load_stop_sets(conn) -> dict[str, set]:
    """DB line id -> normalized station names (via line_stops/line stops)."""
    rows = conn.execute(
        text(
            """
            SELECT ls.line_id, s.name
            FROM line_stops ls
            JOIN stations s ON s.id = ls.station_id
            """
        )
    ).fetchall()
    by_line: dict[str, set] = defaultdict(set)
    for line_id, sname in rows:
        n = _norm(sname)
        if n:
            by_line[str(line_id)].add(n)
    return by_line


def _best_stop_overlap(line: dict, stop_sets: dict[str, set]) -> tuple[str, float] | None:
    edge_stops = {_norm(n) for n in line["stop_names"] if n}
    if not edge_stops:
        return None
    best_lid, best_score = None, 0.0
    for lid, stops in stop_sets.items():
        inter = len(edge_stops & stops)
        if inter >= 2:  # require at least 2 shared stops
            score = inter / (len(edge_stops) + len(stops) - inter)
            if score > best_score:
                best_lid, best_score = lid, score
    return (best_lid, best_score) if best_lid else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill line schedules/pricing")
    parser.add_argument("--dryrun", action="store_true", help="Report only, no writes")
    args = parser.parse_args()

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    edges = json.loads(EDGES_PATH.read_text(encoding="utf-8"))
    nodes = json.loads(NODES_PATH.read_text(encoding="utf-8"))
    node_names = {
        n["node_id"]: n.get("name", "")
        for n in nodes
        if isinstance(n, dict) and n.get("node_id")
    }
    for e in edges:
        if not e.get("from_name"):
            e["from_name"] = node_names.get(e.get("from_node_id"), "")
        if not e.get("to_name"):
            e["to_name"] = node_names.get(e.get("to_node_id"), "")

    lines = _group_edges_by_line(edges)
    by_lid: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        if e.get("line_id") and e["line_id"] in lines:
            by_lid[e["line_id"]].append(e)

    engine = create_engine(DATABASE_URL)
    updates = []  # (line_id, schedule_info, pricing_info)
    with engine.begin() as conn:
        name_index = build_name_index(conn)
        stop_sets = load_stop_sets(conn)

        for lid, line in lines.items():
            line_edges = by_lid[lid]
            sched = _edge_schedules(line_edges)
            pricing = _edge_pricing(line_edges)
            if not sched and not pricing:
                continue

            db_lid = name_index.get(_norm(line["line_name"]))
            match_method = "name"
            if db_lid is None:
                for cand in _candidate_names(line):
                    db_lid = name_index.get(_norm(cand))
                    if db_lid:
                        break
            if db_lid is None:
                overlap = _best_stop_overlap(line, stop_sets)
                if overlap:
                    db_lid, _score = overlap
                    match_method = "stops"
            if db_lid is None:
                continue

            updates.append((db_lid, sched, pricing, match_method))

        name_matched = sum(1 for u in updates if u[3] == "name")
        stop_matched = sum(1 for u in updates if u[3] == "stops")
        total_edges = sum(1 for _ in edges)
        print(f"Edge lines grouped: {len(lines)}")
        print(f"Matched to DB lines: {len(updates)} (name={name_matched}, stops={stop_matched})")
        print(f"Total edges: {total_edges}")

        if not args.dryrun:
            for db_lid, sched, pricing, _m in updates:
                conn.execute(
                    text(
                        "UPDATE transport_lines SET schedule_info=:s, pricing_info=:p "
                        "WHERE id=:id"
                    ),
                    {"s": json.dumps(sched) if sched else None,
                     "p": json.dumps(pricing) if pricing else None,
                     "id": db_lid},
                )
            print(f"Updated {len(updates)} lines")

    # Reports
    report = REPORT_DIR / f"backfill_schedules_{'dryrun' if args.dryrun else 'run'}.txt"
    report.write_text(
        json.dumps(
            {
                "edge_lines": len(lines),
                "matched": len(updates),
                "by_method": {"name": name_matched, "stops": stop_matched},
        "sample": [
            {
                "line_name": lines[l]["line_name"],
                "schedule": _edge_schedules(by_lid[l]),
                "pricing": _edge_pricing(by_lid[l]),
            }
            for l in list(lines)[:5]
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
