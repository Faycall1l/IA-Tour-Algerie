#!/usr/bin/env python3
"""Prune artisans to verifiable businesses only.

Keeps an artisan only if it has BOTH:
  - a real business-looking name (not a bare first name, not a generic trade
    word like "couturier"/"Menuisier"/"Bijouterie"), AND
  - at least one findable contact field (address, commune, phone, website, or
    opening hours).

Drops the ~155 first-name-only / generic-word records that a user cannot find
(real OSM nodes, but effectively nameless). Updates the canonical JSON
(app/data/osm_artisans.json) and the DB. Dry-run with --dry-run.
"""

import argparse
import json
import re
import sys

import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

JSON_PATH = "/Users/faycalamrouche/Desktop/ATHAR/Athar/app/data/osm_artisans.json"

GENERIC_WORDS = [
    "bijouterie", "artisanat", "atelier", "couturier", "coiffeur", "souvenir",
    "boutique", "shop", "magasin", "menuiserie", "menuisier", "cordonnier",
    "tissage", "poterie", "poteries", "cuir", "bois", "bijoux", "orfevre",
    "ferronnerie", "tailleur", "broderie", "calligraphie", "ceramique",
    "mosaique", "tannerie", "vannerie", "bijoutier", "sculpteur", "marbre",
    "soudeur", "horloger", "horlogerie", "platrier", "plombier", "bijoutier",
    "boulanger", "pâtissier", "الخياط", "خياط", "خياطة", "حداد", "لحام",
    "خراطة", "نجار", "محفوظ",
]

# Terms that mark a name as NOT a findable artisan business: bare trade words,
# infrastructure, markets, repair services, generic nouns.
NON_ARTISAN = [
    "stade", "stadium", "marché", "market", "souk", "bazar", "reparation",
    "reparations", "navale", "naval", "vitrerie", "vitre", "miroire", "meuble",
    "meubles", "vente", "librairie", "reliure", "plot", "service", "garden",
    "park", "الملعب", "السوق", "حديقة", "مكتبة", "بيع", "منزل", "عيادة",
    "مستشفى", "مدرسة",
]

# A business-looking name should contain at least one of these.
BUSINESS_HINT = [
    "bijouterie", "bijoux", "jewelry", "jewels", "menuis", "cordonni",
    "ceramique", "poterie", "couture", "couturi", "textile", "caftan",
    "ferronnerie", "artisanat", "artisan", "vitre", "vitrerie", "الخياط",
    "خياطة", "خياط", "مجوهرات", "مجوهر", "صائغ", "صياغة", "ذهب", "الخزف",
    "خزف", "نجار", "نجارة", "ألمنيوم", "حداد", "لحام", "الأحذية", "leather",
    "فساتين", "صانع", "ورشة", "الأناقة", "السعادة", "المستقبل",
]

# Street/address words => a name that is really an address.
ADDRESS_WORDS = [
    "شارع", "avenue", "boulevard", "rue ", "rue ", "cité", "حي", "حي ",
    "route ", "الطريق", "zaabet", "zaabet ", "ميلود",
]

AR_NAME_LOOKALIKE = re.compile(r"^[\u0600-\u06ff]+$")
AR_WORD = re.compile(r"^[\u0600-\u06ff]+$")
LATIN_WORD = re.compile(r"^[a-zà-ÿ']+$")


def classify(name: str) -> str:
    low = name.strip().lower()
    words = [w for w in re.split(r"[^a-z0-9\u0600-\u06ff']+", low) if w]
    no_words = len(words)
    has_biz = any(h in low for h in BUSINESS_HINT)

    # Address typed as a name (starts with/contains a street word, no biz hint).
    if any(a in low for a in ADDRESS_WORDS) and not has_biz:
        return "non-artisan"

    # Clear non-artisan terms (markets, stadiums, repairs, shops).
    if any(g in low for g in NON_ARTISAN):
        return "non-artisan"

    # Generic trade word (with at most a trailing qualifier): not findable.
    if no_words <= 2 and any(g in low for g in GENERIC_WORDS) and not has_biz:
        return "generic-word"

    # Bare person name: 1-2 short words (latin or arabic), no business hint.
    if no_words <= 2 and not has_biz:
        if all(
            (LATIN_WORD.fullmatch(w) and len(w) < 12) or AR_WORD.fullmatch(w)
            for w in words
        ):
            return "person-name"

    # Bare first name / single short latin or arabic word: not findable.
    if no_words == 1 and len(words[0]) < 11 and (
        re.fullmatch(r"[a-z]+", words[0]) or AR_NAME_LOOKALIKE.fullmatch(words[0])
    ):
        return "first-name-only"

    return "business-name"


def keep(rec: dict) -> tuple[bool, str]:
    kind = classify(rec.get("name", ""))
    has_contact = any(
        rec.get(f) for f in ("address", "commune", "phone", "website", "opening_hours")
    )
    if kind != "business-name":
        return False, kind
    if not has_contact:
        return False, "no-contact"
    return True, kind


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = json.load(open(JSON_PATH))
    kept, dropped = [], []
    for rec in records:
        ok, reason = keep(rec)
        (kept if ok else dropped).append((rec, reason))

    print(f"total: {len(records)}")
    print(f"KEEP: {len(kept)}  DROP: {len(dropped)}")
    print("drop reasons:", {r: sum(1 for _, x in dropped if x == r) for r in set(x for _, x in dropped)})

    if args.dry_run:
        print("\n[DRY-RUN] dropping (sample):")
        for rec, reason in dropped[:15]:
            print(f"  [{reason:14}] {rec['name']!r} {rec['craft_type']:12} {rec.get('address') or rec.get('commune') or ''}")
        print(f"\n[DRY-RUN] keeping (sample):")
        for rec, _ in kept[:15]:
            print(f"  {rec['name']!r} {rec['craft_type']:12} {rec.get('address') or rec.get('commune') or rec.get('phone') or ''}")
        return

    # Update canonical JSON in place.
    kept_records = [rec for rec, _ in kept]
    json.dump(kept_records, open(JSON_PATH, "w"), ensure_ascii=False, indent=2)
    print(f"JSON updated: {JSON_PATH} ({len(kept_records)} records)")

    # Sync DB: delete artisan rows whose (name, lat, lng) match a dropped record.
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    cur = conn.cursor()
    deleted = 0
    for rec, reason in dropped:
        cur.execute(
            """
            DELETE FROM artisan_transit_access
            WHERE artisan_id IN (
                SELECT id FROM artisans
                WHERE name = %s AND round(latitude::numeric, 4) = round(%s::numeric, 4)
                  AND round(longitude::numeric, 4) = round(%s::numeric, 4)
            )
            """,
            (rec["name"], rec["latitude"], rec["longitude"]),
        )
        cur.execute(
            """
            DELETE FROM artisans
            WHERE name = %s AND round(latitude::numeric, 4) = round(%s::numeric, 4)
              AND round(longitude::numeric, 4) = round(%s::numeric, 4)
            """,
            (rec["name"], rec["latitude"], rec["longitude"]),
        )
        deleted += cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    print(f"DB: deleted {deleted} artisans (backup kept in git history of osm_artisans.json)")


if __name__ == "__main__":
    sys.exit(main())
