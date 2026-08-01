#!/usr/bin/env python3
"""Enrich POI descriptions from Wikidata and OSM tags.

Two-phase approach:
  1. Fetch descriptions from Wikidata for POIs with wikidata tag (187 POIs)
  2. Generate descriptions from OSM tags for all other POIs
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent.parent.parent
POI_SRC = ROOT / "app" / "data" / "poi_nodes_enriched.json"
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5434/athar_db",
)

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

TYPE_LABELS = {
    "archaeological_site": "Site archéologique",
    "monument": "Monument historique",
    "memorial": "Mémorial",
    "ruins": "Ruines historiques",
    "castle": "Château historique",
    "fort": "Fort historique",
    "battlefield": "Champ de bataille historique",
    "museum": "Musée",
    "artwork": "Œuvre d'art",
    "attraction": "Attraction touristique",
    "viewpoint": "Point de vue panoramique",
    "peak": "Sommet",
    "beach": "Plage",
    "cave": "Grotte",
    "waterfall": "Cascade",
    "volcano": "Volcan",
    "bay": "Baie",
    "park": "Parc",
    "garden": "Jardin",
    "nature_reserve": "Réserve naturelle",
    "restaurant": "Restaurant",
    "cafe": "Café",
    "fast_food": "Restauration rapide",
    "pub": "Pub",
    "bar": "Bar",
    "place_of_worship": "Lieu de culte",
    "library": "Bibliothèque",
    "theatre": "Théâtre",
    "cinema": "Cinéma",
    "supermarket": "Supermarché",
    "mall": "Centre commercial",
    "stadium": "Stade",
    "sports_centre": "Centre sportif",
    "marina": "Marina",
    "lighthouse": "Phare",
    "tower": "Tour",
    "observatory": "Observatoire",
    "souvenir_shop": "Boutique de souvenirs",
    "gift_shop": "Magasin de cadeaux",
}


def fetch_wikidata_batch(wikidata_ids):
    """Batch fetch descriptions from Wikidata."""
    if not wikidata_ids:
        return {}
    ids_str = "|".join(wikidata_ids)
    params = {
        "action": "wbgetentities",
        "ids": ids_str,
        "props": "descriptions|labels",
        "languages": "fr|en|ar",
        "format": "json",
    }
    url = f"{WIKIDATA_API}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ATHAR-OS/1.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
    except Exception as e:
        print(f"  Wikidata error: {e}")
        return {}
    results = {}
    for qid, entity in data.get("entities", {}).items():
        desc = None
        for lang in ("fr", "en", "ar"):
            if lang in entity.get("descriptions", {}):
                desc = entity["descriptions"][lang]["value"]
                break
        if desc:
            results[qid] = desc
    return results


def generate_desc(poi):
    """Generate description from OSM tags."""
    tags = poi.get("tags", {})
    subtype = poi.get("subtype", "")
    parts = []

    label = TYPE_LABELS.get(subtype)
    city = poi.get("commune") or tags.get("addr:city")
    civ = tags.get("historic:civilization")
    period = tags.get("historic:period") or tags.get("historic:era")
    ele = tags.get("ele")
    osm_desc = tags.get("description")
    opening = poi.get("opening_hours")
    website = poi.get("website")

    if label:
        parts.append(f"{label}")
    if city:
        parts.append(f"à {city}")
    if civ:
        parts.append(f"Civilisation {civ}")
    if period:
        parts.append(f"Période {period}")
    if ele and subtype == "peak":
        try:
            parts.append(f"Altitude {int(float(ele))}m")
        except ValueError:
            parts.append(f"Altitude {ele}m")
    if osm_desc:
        parts.append(osm_desc)
    else:
        if poi.get("category") == "dining":
            parts.append("Restauration sur place")
        elif poi.get("category") == "nature":
            parts.append("Site naturel à découvrir")
        elif poi.get("category") == "culture":
            parts.append("Patrimoine culturel algérien")
        elif poi.get("category") == "historical":
            if not civ and not period:
                parts.append("Site historique algérien")
        elif poi.get("category") == "accommodation":
            parts.append("Hébergement touristique")
    if opening:
        parts.append(f"Horaires: {opening}")

    desc = " - ".join(parts) if parts else None
    if not desc:
        return None
    if len(desc) > 500:
        desc = desc[:497] + "..."
    return desc


def main():
    print("=== Enrich POI descriptions ===\n")

    if not POI_SRC.exists():
        print(f"ERROR: {POI_SRC} not found")
        sys.exit(1)

    pois = json.loads(POI_SRC.read_text())

    # Build lookup: (name, wilaya_id) → poi
    poi_lookup = {}
    for p in pois:
        n = p.get("name", "")
        w = p.get("wilaya_id")
        if n and w and "(non nommé)" not in n:
            poi_lookup[(n, w)] = p

    engine = create_engine(DATABASE_URL)

    # ── Phase 1: Wikidata ──
    wd_pois = [p for p in pois if p.get("tags", {}).get("wikidata")]
    print(f"Phase 1: Wikidata ({len(wd_pois)} POIs)")

    wd_map = {}
    for i in range(0, len(wd_pois), 50):
        batch = wd_pois[i:i+50]
        qids = [p["tags"]["wikidata"] for p in batch]
        result = fetch_wikidata_batch(qids)
        wd_map.update(result)
        time.sleep(0.3)

    wd_updated = 0
    with engine.begin() as conn:
        for p in wd_pois:
            qid = p["tags"]["wikidata"]
            if qid in wd_map:
                desc = f"{wd_map[qid]} [Source: Wikidata]"
                n, w = p.get("name", ""), p.get("wilaya_id")
                if n and w:
                    conn.execute(
                        text("UPDATE pois SET description = :desc WHERE name = :name AND wilaya_id = :wid AND (description IS NULL OR description = '')"),
                        {"desc": desc, "name": n, "wid": w},
                    )
                    wd_updated += 1

    print(f"  Wikidata updates: {wd_updated}")

    # ── Phase 2: Tag-based ──
    print(f"\nPhase 2: Tag-based descriptions")

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, name, wilaya_id FROM pois WHERE description IS NULL OR description = ''")
        ).fetchall()
        print(f"  POIs needing description: {len(rows)}")

        updated = 0
        for row in rows:
            pid, name, wid = row
            p = poi_lookup.get((name, wid))
            if not p:
                continue
            desc = generate_desc(p)
            if desc:
                conn.execute(
                    text("UPDATE pois SET description = :desc WHERE id = :pid"),
                    {"desc": desc, "pid": pid},
                )
                updated += 1
                if updated % 10000 == 0:
                    print(f"    {updated}/{len(rows)}", end="\r")
                    sys.stdout.flush()

    print(f"  Tag-based updates: {updated}")

    # Stats
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM pois")).scalar()
        with_desc = conn.execute(
            text("SELECT COUNT(*) FROM pois WHERE description IS NOT NULL AND description != ''")
        ).scalar()

    print(f"\n=== Results ===")
    print(f"Total POIs: {total}")
    print(f"With description: {with_desc}")
    print(f"Rate: {with_desc/total*100:.1f}%")
    print("Done!")


if __name__ == "__main__":
    main()
