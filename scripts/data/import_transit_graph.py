#!/usr/bin/env python3
"""Import the full multi-modal transit graph into the database.

Merges:
  - transit_nodes.json / transit_edges.json (from scraper engine)
  - sntf_seed_complete.json (detailed SNTF lines & stations)

Usage:
  python scripts/import_transit_graph.py [--dry-run]
"""

import json
import uuid
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from app.models.station import Station, TransportLine, LineStop
from app.database import SessionLocal

LINE_COLORS = {
    "train": "#E53935",
    "metro": "#1E88E5",
    "tram": "#43A047",
    "bus": "#FB8C00",
    "airport": "#8E24AA",
    "ferry": "#00ACC1",
    "cable_car": "#9C27B0",
}

# Manual station aliases to help cross-referencing
ALIASES: dict[str, list[str]] = {
    "alger agha": ["alger gare agha", "alger aga"],
    "alger gare agha": ["alger agha"],
    "oran": ["oran gare"],
    "oran gare": ["oran"],
    "constantine": ["constantine gare"],
    "constantine gare": ["constantine"],
    "annaba": ["annaba gare"],
    "annaba gare": ["annaba"],
    "setif": ["setif gare", "sétif gare", "sétif"],
    "sétif": ["setif gare", "setif", "sétif gare"],
    "bejaia": ["bejaia gare", "béjaïa gare", "béjaïa"],
    "béjaïa": ["bejaia gare", "bejaia", "béjaïa gare"],
    "tlemcen": ["tlemcen gare"],
    "tlemcen gare": ["tlemcen"],
    "blida": ["blida gare"],
    "batna": ["batna gare"],
    "biskra": ["biskra gare"],
    "skikda": ["skikda gare"],
    "sidi bel abbes": ["sidi bel abbès gare", "sidi bel abbès", "sidi bel abbes gare", "sidi bel abbès gare"],
    "sidi bel abbès": ["sidi bel abbes gare", "sidi bel abbes", "sidi bel abbès gare"],
    "chlef": ["chlef gare"],
    "ain defla": ["ain defla gare", "aïn defla"],
    "boumerdes": ["boumerdès", "boumerdes gare"],
    "boumerdès": ["boumerdes", "boumerdes gare"],
    "thenia": ["thénia", "thenia gare"],
    "thénia": ["thenia", "thenia gare"],
    "bouira": ["bouira gare"],
    "lakhdaria": ["lakhdaria gare"],
    "mostaganem": ["mostaganem gare"],
    "ouargla": ["ouargla gare"],
    "sidi abd allah": ["sidi abdallah"],
    "aeroport houari boumediene": ["aeroport alger", "aeroport"],
    "place des martyrs": ["place des martyrs metro", "place des martyrs tram"],
    "el harrach centre": ["el harrach centre metro"],
    "el harrach gare": ["el harrach gare metro", "el harrach gare tram"],
    "les fusillés": ["les fusilles", "les fusillés tram", "les fusilles tram"],
    "tafourah": ["tafourah grande poste", "grande poste"],
    "1er mai": ["1er mai tram", "1er mai metro"],
}


def _norm(name: str) -> str:
    n = name.lower()
    for ch in "()'-,.":
        n = n.replace(ch, " ")
    for ch in "éèêëàâäùûüôöîïç":
        rep = {"é": "e", "è": "e", "ê": "e", "ë": "e",
               "à": "a", "â": "a", "ä": "a",
               "ù": "u", "û": "u", "ü": "u",
               "ô": "o", "ö": "o",
               "î": "i", "ï": "i",
               "ç": "c"}[ch]
        n = n.replace(ch, rep)
    return " ".join(n.split()).strip()


def _station_keys(name: str) -> list[str]:
    """Generate all possible lookup keys for a station name."""
    base = _norm(name)
    keys = {base}

    # Remove 'gare' prefix/suffix variants
    parts = base.split()
    without_gare = [p for p in parts if p != "gare"]
    if len(without_gare) != len(parts):
        keys.add(" ".join(without_gare))

    # Add manual aliases
    if base in ALIASES:
        for a in ALIASES[base]:
            keys.add(_norm(a))

    return list(keys)


def main(dry_run: bool = False) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Importing multi-modal transit graph...\n")

    # ── Load data files ──
    enriched_nodes_path = ROOT / "app" / "data" / "transit_nodes_enriched.json"
    enriched_edges_path = ROOT / "app" / "data" / "transit_edges_enriched.json"
    using_enriched = enriched_nodes_path.exists()

    if using_enriched:
        with open(enriched_nodes_path) as f:
            scraper_nodes: list[dict] = json.load(f)
        with open(enriched_edges_path) as f:
            scraper_edges: list[dict] = json.load(f)
        print(f"  Using enriched data: {len(scraper_nodes)} nodes, {len(scraper_edges)} edges")
    else:
        with open(ROOT / "app" / "data" / "transit_nodes.json") as f:
            scraper_nodes = json.load(f)
        with open(ROOT / "app" / "data" / "transit_edges.json") as f:
            scraper_edges = json.load(f)
        print(f"  Using basic scraper data: {len(scraper_nodes)} nodes, {len(scraper_edges)} edges")

    if not using_enriched:
        with open(ROOT / "app" / "data" / "sntf_seed_complete.json") as f:
            sntf_data = json.load(f)
    else:
        sntf_data = {"stations": [], "lines": []}

    # ── Build unified station list ──
    stations: list[dict] = []
    station_name_map: dict[str, str] = {}  # norm_key -> display_name
    node_id_to_name: dict[str, str] = {}  # scraper node_id -> display name

    def add_station(name: str, lat: float | None, lng: float | None,
                    stype: str, operator: str, wilaya: int | None,
                    node_id: str | None = None) -> bool:
        if lat is None or lng is None or (lat == 0.0 and lng == 0.0):
            return False
        keys = _station_keys(name)
        for k in keys:
            if k in station_name_map:
                if node_id:
                    # Still track which node_id this existing station matches
                    existing_name = station_name_map[k]
                    node_id_to_name[node_id] = existing_name
                return False  # duplicate
        # Register all keys
        for k in keys:
            station_name_map[k] = name
        if node_id:
            node_id_to_name[node_id] = name
        stations.append({
            "name": name, "lat": lat, "lng": lng,
            "type": stype, "operator": operator, "wilaya": wilaya or 16,
        })
        return True

    # Step 1: scraper nodes
    cnt_scraper = 0
    for n in scraper_nodes:
        if add_station(n["name"], n.get("latitude"), n.get("longitude"),
                       n.get("type", "train"), n.get("operator", "SNTF"),
                       n.get("wilaya_id"),
                       node_id=n.get("node_id")):
            cnt_scraper += 1
    print(f"  Scraper stations: {cnt_scraper} new / {len(scraper_nodes)} total")

    # Step 2: additional SNTF seed stations
    cnt_seed = 0
    for s in sntf_data["stations"]:
        name = s.get("name_clean", s.get("name", "")).strip()
        if name and add_station(name, s.get("lat"), s.get("lng"),
                                "train", "SNTF", s.get("wilaya_id")):
            cnt_seed += 1
    print(f"  SNTF seed stations (additional): {cnt_seed}")
    print(f"  Total stations: {len(stations)}")
    print(f"  node_id mappings: {len(node_id_to_name)}")
    types = Counter(s["type"] for s in stations)
    print(f"  By type: {dict(types)}")

    if dry_run:
        return

    # ── DB import ──
    db = SessionLocal()
    try:
        db.execute(text("DELETE FROM line_stops"))
        db.execute(text("DELETE FROM transport_lines"))
        db.execute(text("DELETE FROM stations"))
        db.commit()
        print("  Cleared existing transport data")

        # ── Insert stations ──
        station_lookup: dict[str, uuid.UUID] = {}
        station_id_by_name: dict[str, uuid.UUID] = {}

        for s in stations:
            sid = uuid.uuid4()
            st = Station(
                id=sid,
                name=s["name"],
                station_type=s["type"],
                operator=s["operator"],
                latitude=s["lat"],
                longitude=s["lng"],
                wilaya_id=s["wilaya"],
                is_active=True,
            )
            db.add(st)
            for k in _station_keys(s["name"]):
                station_lookup[k] = sid
            station_id_by_name[s["name"]] = sid

        db.flush()
        print(f"  Inserted {len(stations)} stations")

        # ── Find station ID helper ──
        def _sid(name: str) -> uuid.UUID | None:
            for k in _station_keys(name):
                if k in station_lookup:
                    return station_lookup[k]
            return None

        # ── Process scraper edges into lines ──
        edge_groups: dict[str, dict] = {}
        unmatched_edges = 0

        for e in scraper_edges:
            line_name = e.get("line_name", "")
            op = e.get("operator", "")
            mode = e.get("mode", "train")
            color = e.get("color") or LINE_COLORS.get(mode, "#666")

            from_nid = e.get("from_node_id", "")
            to_nid = e.get("to_node_id", "")

            # Look up station by node_id -> name -> DB
            from_name = node_id_to_name.get(from_nid, "")
            to_name = node_id_to_name.get(to_nid, "")

            if not from_name or not to_name:
                unmatched_edges += 1
                continue

            fsid = _sid(from_name)
            tsid = _sid(to_name)
            if not fsid or not tsid:
                unmatched_edges += 1
                continue

            key = f"{mode}|{op}|{line_name}"
            if key not in edge_groups:
                edge_groups[key] = {
                    "name": line_name, "mode": mode, "operator": op, "color": color,
                    "stops": {}, "edges": [],
                }
            eg = edge_groups[key]
            eg["edges"].append((fsid, tsid))
            eg["stops"][fsid] = from_name
            eg["stops"][tsid] = to_name

        if unmatched_edges:
            print(f"  Unmatched scraper edges: {unmatched_edges}")

        # Create TransportLines from scraper edges
        scraper_lines_created = 0
        scraper_stops_created = 0

        for eg in edge_groups.values():
            tl = TransportLine(
                id=str(uuid.uuid4()),
                name=eg["name"],
                operator=eg["operator"] or eg["mode"].upper(),
                mode=eg["mode"],
                color=eg["color"],
                description=f"{eg['mode']}: {eg['name']}",
                is_active=True,
            )
            db.add(tl)
            db.flush()
            line_id = tl.id
            scraper_lines_created += 1

            ordered: list[uuid.UUID] = []
            seen = set()
            for fsid, tsid in eg["edges"]:
                if fsid not in seen:
                    ordered.append(fsid)
                    seen.add(fsid)
                if tsid not in seen:
                    ordered.append(tsid)
                    seen.add(tsid)

            for idx, sid in enumerate(ordered, 1):
                db.add(LineStop(
                    id=str(uuid.uuid4()),
                    line_id=line_id,
                    station_id=sid,
                    stop_order=idx,
                ))
                scraper_stops_created += 1

        print(f"  Scraper lines: {scraper_lines_created}, stops: {scraper_stops_created}")

        # ── SNTF seed lines ──
        sntf_lines_created = 0
        sntf_stops_created = 0
        sntf_stops_skipped = 0

        for ld in sntf_data["lines"]:
            tl = TransportLine(
                id=str(uuid.uuid4()),
                name=ld["name"],
                operator=ld.get("operator", "SNTF"),
                mode=ld.get("mode", "train"),
                color=ld.get("color", "#E53935"),
                description=ld.get("description", f"SNTF: {ld['name']}"),
                distance_km=ld.get("distance_km"),
                is_active=True,
            )
            db.add(tl)
            db.flush()
            line_id = tl.id
            sntf_lines_created += 1

            for order, stop_name in enumerate(ld["stops"]):
                sid = _sid(stop_name)
                if not sid:
                    sntf_stops_skipped += 1
                    if sntf_stops_skipped <= 10:
                        print(f"    WARNING: stop '{stop_name}' not found for line '{ld['name']}'")
                    continue
                db.add(LineStop(
                    id=str(uuid.uuid4()),
                    line_id=line_id,
                    station_id=sid,
                    stop_order=order + 1,
                ))
                sntf_stops_created += 1

        print(f"  SNTF seed lines: {sntf_lines_created}, stops: {sntf_stops_created}, skipped: {sntf_stops_skipped}")

        db.commit()

        # ── Final summary ──
        total_lines = scraper_lines_created + sntf_lines_created
        total_stops = scraper_stops_created + sntf_stops_created
        print(f"\n{'='*50}")
        print(f"IMPORT COMPLETE")
        print(f"{'='*50}")
        print(f"  Stations: {len(stations)}")
        print(f"  Lines: {total_lines}")
        print(f"  Line stops: {total_stops + 1}")
        print(f"  Types: {dict(types)}")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
