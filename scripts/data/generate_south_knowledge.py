"""Generate the south-Algeria agent knowledge base from the live DB.

Produces `app/agents/data/south_knowledge.json` — a compact, entirely
DB-derived briefing per southern wilaya (how to reach it, real stays,
real restaurants, featured POIs) plus desert-wide operator/facts notes.

Grounding rule: every value comes from the database (transport_lines,
stations, stays, pois). Nothing is fabricated; southern food gaps (e.g.
Djanet has 2 named restaurants) reflect genuine absence in all real sources.

Usage:
    python -m scripts.data.generate_south_knowledge [--dry-run] [--out PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.data.enrich_photos_diverse_v2 import DB_CONFIG  # noqa: E402
from scripts.data.enrich_photos_diverse_v2 import SOUTHERN_WILAYAS  # noqa: E402

log = logging.getLogger("gen-south-kb")

DEFAULT_OUT = ROOT / "app/agents/data/south_knowledge.json"

SOUTH_NAMES = {
    1: "Adrar",
    8: "Béchar",
    11: "Tamanrasset",
    30: "Ouargla",
    33: "Illizi",
    37: "Tindouf",
    47: "Ghardaïa",
    49: "Timimoun",
    50: "Bordj Badji Mokhtar",
    52: "Béni Abbès",
    53: "In Salah",
    56: "Djanet",
    58: "El Meniaa",
}

INTRO = (
    "Deep-south wilayas have NO train access — SNTF stops in the north. "
    "Reach them by Air Algérie flight from Alger, or by long-distance "
    "shared taxi (most lines run 05:00–23:00 every 30 min). Desert travel "
    "is seasonal (Oct–Apr best); stays skew to auberges de jeunesse "
    "(≈2 500 DZD/night) and small hotels (4 000–6 000 DZD)."
)

OPERATOR_NOTES = {
    "air_algerie": "Contact Center +213 21 98 63 63 (short code 3302); wilaya agencies in Adrar, Tamanrasset, Ouargla, Ghardaïa, Béchar, Djanet, In Salah.",
    "taxis": "Shared taxis leave when full; confirm price before boarding. Most southern inter-city taxi lines run 05:00–23:00, every 30 min.",
}


def _clean(name: str | None) -> str | None:
    if not name:
        return None
    name = name.strip()
    if not name or "non nommé" in name.lower():
        return None
    name = re.sub(r"^(?:Taxi\s+)+", "Taxi ", name)
    return name


def _dedupe(items: list) -> list:
    seen: set[str] = set()
    out = []
    for it in items:
        key = it["name"] if isinstance(it, dict) else it
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def fetch_wilaya_data(cur, wilaya_id: int) -> dict:
    def lines(mode: str) -> list[str]:
        cur.execute(
            "SELECT DISTINCT l.name FROM transport_lines l "
            "JOIN line_stops ls ON ls.line_id = l.id "
            "JOIN stations st ON st.id = ls.station_id "
            "WHERE l.mode = %s AND st.wilaya_id = %s "
            "AND l.name IS NOT NULL AND l.name != '' "
            "ORDER BY l.name",
            (mode, wilaya_id),
        )
        return [_clean(r[0]) for r in cur.fetchall() if _clean(r[0])]

    cur.execute(
        "SELECT name, price_per_night_dzd FROM stays "
        "WHERE wilaya_id = %s AND name IS NOT NULL "
        "ORDER BY price_per_night_dzd NULLS LAST, name LIMIT 3",
        (wilaya_id,),
    )
    stays = _dedupe(
        [
            {"name": n, "price_dzd": p}
            for n, p in cur.fetchall()
            if _clean(n) is not None
        ]
    )

    cur.execute(
        "SELECT name FROM pois WHERE wilaya_id = %s AND category = 'restaurant' "
        "AND name IS NOT NULL AND name !~ 'non nommé' "
        "ORDER BY is_featured DESC, name LIMIT 3",
        (wilaya_id,),
    )
    restaurants = _dedupe(
        [n for (n,) in cur.fetchall() if _clean(n) is not None]
    )

    cur.execute(
        "SELECT name FROM pois WHERE wilaya_id = %s AND is_featured "
        "AND name IS NOT NULL AND name !~ 'non nommé' ORDER BY name LIMIT 3",
        (wilaya_id,),
    )
    featured = _dedupe([n for (n,) in cur.fetchall() if _clean(n) is not None])

    cur.execute(
        "SELECT count(*) FROM pois WHERE wilaya_id = %s", (wilaya_id,)
    )
    poi_count = cur.fetchone()[0]

    return {
        "id": wilaya_id,
        "name": SOUTH_NAMES[wilaya_id],
        "flights": lines("flight"),
        "buses": lines("bus"),
        "taxis": lines("taxi"),
        "stays": stays,
        "restaurants": restaurants,
        "featured": featured,
        "poi_count": poi_count,
    }


def generate(conn, dry_run: bool, out: Path) -> dict:
    cur = conn.cursor()
    wilayas = {}
    for wid in sorted(SOUTHERN_WILAYAS):
        wilayas[str(wid)] = fetch_wilaya_data(cur, wid)
    doc = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "intro": INTRO,
        "operator_notes": OPERATOR_NOTES,
        "wilayas": wilayas,
    }
    if not dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        doc = generate(conn, args.dry_run, args.out)
        total_stays = sum(len(w["stays"]) for w in doc["wilayas"].values())
        log.info(
            "wrote %d southern wilayas (%d stays listed) to %s",
            len(doc["wilayas"]),
            total_stays,
            args.out if not args.dry_run else "(dry-run)",
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
