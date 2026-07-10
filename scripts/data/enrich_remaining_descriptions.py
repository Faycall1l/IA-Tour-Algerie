#!/usr/bin/env python3
"""Generate descriptions for the remaining ~10K POIs directly from osm_tags JSONB."""

import os
import sys

import sqlalchemy as sa
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://athar:athar_pass@localhost:5432/athar_db",
)

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

CATEGORY_FALLBACKS = {
    "historical": "Site historique algérien",
    "natural": "Site naturel à découvrir",
    "cultural": "Patrimoine culturel algérien",
    "religious": "Lieu religieux",
    "museum": "Musée",
    "beach": "Plage",
    "mountain": "Sommet montagneux",
    "park": "Parc / espace vert",
    "market": "Marché local",
    "restaurant": "Restauration sur place",
    "cafe": "Café / salon de thé",
}


def generate_desc_from_row(row):
    parts = []
    subtype = row.get("subtype") or ""
    osm_tags = row.get("osm_tags") or {}
    name = row.get("name") or ""
    category = row.get("category") or ""
    commune = row.get("commune") or ""

    if "(non nommé)" in name or name.lower().startswith("unknown"):
        return None

    label = TYPE_LABELS.get(subtype)
    if label:
        parts.append(label)
    if commune:
        parts.append(f"à {commune}")

    civ = osm_tags.get("historic:civilization") or osm_tags.get("historic_civilization")
    period = osm_tags.get("historic:period") or osm_tags.get("historic:era")
    if civ:
        parts.append(f"Civilisation {civ}")
    if period:
        parts.append(f"Période {period}")

    ele = osm_tags.get("ele")
    if ele and subtype == "peak":
        try:
            parts.append(f"Altitude {int(float(ele))}m")
        except ValueError:
            parts.append(f"Altitude {ele}m")

    osm_desc = osm_tags.get("description") or osm_tags.get("note")
    if osm_desc and len(osm_desc) > 5:
        parts.append(osm_desc)
    else:
        fallback = CATEGORY_FALLBACKS.get(category)
        if not civ and not period and fallback:
            parts.append(fallback)

    opening = osm_tags.get("opening_hours") or row.get("opening_hours") or ""
    if opening:
        parts.append(f"Horaires: {opening}")

    desc = " - ".join(parts) if parts else None
    if not desc:
        return None
    if len(desc) > 500:
        desc = desc[:497] + "..."
    return desc


def main():
    print("=== Enrich remaining descriptions from osm_tags ===\n")

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT id, name, category, subtype, commune, opening_hours, osm_tags
                FROM pois
                WHERE (description IS NULL OR description = '')
                  AND (name NOT LIKE '%(non nommé)%' AND name NOT ILIKE 'unknown%')
            """)
        ).mappings().fetchall()
        print(f"POIs needing description (named): {len(rows)}")

    updated = 0
    skipped = 0
    with engine.begin() as conn:
        for i, row in enumerate(rows):
            desc = generate_desc_from_row(dict(row))
            if desc:
                conn.execute(
                    text("UPDATE pois SET description = :desc WHERE id = :pid"),
                    {"desc": desc, "pid": row["id"]},
                )
                updated += 1
            else:
                skipped += 1
            if (i + 1) % 500 == 0:
                print(f"  {i+1}/{len(rows)} processed ({updated} updated, {skipped} skipped)", end="\r")
                sys.stdout.flush()

    print(f"\n\nResults: {updated} updated, {skipped} skipped (no tags to generate from)")

    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(*) FROM pois")).scalar()
        with_desc = conn.execute(
            text("SELECT COUNT(*) FROM pois WHERE description IS NOT NULL AND description != ''")
        ).scalar()

    print(f"\nFinal: {with_desc}/{total} ({with_desc/total*100:.1f}%) have descriptions")
    print("Done!")


if __name__ == "__main__":
    main()
