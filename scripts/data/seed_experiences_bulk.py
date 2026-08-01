#!/usr/bin/env python3
"""
Massive experience expansion: generates 1500+ non-seasonal + 800+ seasonal
experiences across all 69 wilayas using programmatic templates.

Sets source='programmatic', is_verified=False for tracking.
"""

import os
import random
import sys
import uuid
from datetime import date

import psycopg2
from psycopg2.extras import execute_values

DB_DSN = os.getenv("DATABASE_URL", "postgresql://athar:athar_pass@localhost:5434/athar_db")

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi",
    5: "Batna", 6: "Béjaïa", 7: "Biskra", 8: "Béchar",
    9: "Blida", 10: "Bouira", 11: "Tamanrasset", 12: "Tébessa",
    13: "Tlemcen", 14: "Tiaret", 15: "Tizi Ouzou", 16: "Alger",
    17: "Djelfa", 18: "Jijel", 19: "Sétif", 20: "Saïda",
    21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba", 24: "Guelma",
    25: "Constantine", 26: "Médéa", 27: "Mostaganem", 28: "M'Sila",
    29: "Mascara", 30: "Ouargla", 31: "Oran", 32: "El Bayadh",
    33: "Illizi", 34: "Bordj Bou Arréridj", 35: "Boumerdès", 36: "El Tarf",
    37: "Tindouf", 38: "Tissemsilt", 39: "El Oued", 40: "Khenchela",
    41: "Souk Ahras", 42: "Tipaza", 43: "Mila", 44: "Aïn Defla",
    45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa", 48: "Relizane",
    49: "Timimoun", 50: "Béni Abbès", 51: "Aïn Salah", 52: "Aïn Guezzam",
    53: "Touggourt", 54: "Djanet", 55: "El M'Ghair", 56: "El Meniaa",
    57: "Ouled Djellal", 58: "Bordj Badji Mokhtar",
    59: "Aflou", 60: "El Abiodh Sidi Cheikh", 61: "El Aricha",
    62: "El Kantara", 63: "Barika", 64: "Bou Saâda",
    65: "Bir El Ater", 66: "Ksar El Boukhari",
    67: "Ksar Chellala", 68: "Aïn Oussera", 69: "Messaad",
}

SEASON_DATES = {
    "spring": ("2026-03-01", "2026-05-31"),
    "summer": ("2026-06-01", "2026-09-30"),
    "autumn": ("2026-09-01", "2026-11-30"),
    "winter": ("2026-12-01", "2027-02-28"),
}

SEASON_SUFFIX = {
    "spring": " — Printemps", "summer": " — Été",
    "autumn": " — Automne", "winter": " — Hiver",
}

CATEGORIES = ["tour", "hiking", "cultural", "food", "adventure", "wellness"]

CATEGORY_DEFAULTS = {
    "tour": {"price": 2500, "dur": 6, "max_p": 15},
    "hiking": {"price": 1500, "dur": 5, "max_p": 12},
    "cultural": {"price": 1200, "dur": 4, "max_p": 20},
    "food": {"price": 1500, "dur": 3, "max_p": 15},
    "adventure": {"price": 4000, "dur": 8, "max_p": 8},
    "wellness": {"price": 3000, "dur": 4, "max_p": 10},
}

BASE_TEMPLATES = {
    "tour": {
        "titles": [
            "Circuit découverte de {name}",
            "Tour guidé de {name} et ses environs",
            "Visite complète de la wilaya de {name}",
            "Les incontournables de {name}",
            "Circuit culturel à {name}",
            "Balade patrimoine dans {name}",
            "Découverte des merveilles de {name}",
            "Journée découverte à {name}",
            "Tour panoramique de {name}",
            "Circuit historique de {name}",
            "Visite guidée des sites de {name}",
            "Excursion d'une journée à {name}",
        ],
        "desc": [
            "Circuit guidé à travers les sites emblématiques de {name}. Une immersion complète dans le patrimoine, la culture et les paysages de la région.",
            "Découvrez {name} à travers ses monuments historiques, ses marchés animés et ses paysages époustouflants lors d'un circuit guidé.",
            "Explorez les trésors cachés de {name} avec un guide local passionné. Histoire, architecture et traditions au programme.",
            "Parcourez les sites les plus remarquables de {name} lors de cette excursion commentée. Idéal pour une première découverte.",
        ],
    },
    "hiking": {
        "titles": [
            "Randonnée dans les monts de {name}",
            "Balade nature à {name}",
            "Sentier découverte de {name}",
            "Randonnée guidée — {name}",
            "Trek nature autour de {name}",
            "Promenade en forêt à {name}",
            "Randonnée des crêtes de {name}",
            "Sentier des lacs de {name}",
        ],
        "desc": [
            "Randonnée à travers les paysages naturels de {name}. Parcours adapté à tous les niveaux avec un guide local expérimenté.",
            "Partez à la découverte des sentiers sauvages de {name}. Forêts, montagnes et vues panoramiques vous attendent.",
        ],
    },
    "cultural": {
        "titles": [
            "Immersion culturelle à {name}",
            "Découverte des traditions de {name}",
            "Patrimoine et artisanat de {name}",
            "Visite des sites historiques de {name}",
            "Rencontre avec les artisans de {name}",
            "Journée culturelle à {name}",
            "Héritage et traditions de {name}",
            "Exploration des musées de {name}",
            "Circuit des monuments de {name}",
            "Architecture et histoire de {name}",
        ],
        "desc": [
            "Découverte du riche patrimoine culturel de {name}. Visite des sites historiques, rencontre avec les artisans locaux.",
            "Plongez dans l'histoire et la culture de {name} à travers ses monuments, ses traditions et son artisanat unique.",
        ],
    },
    "food": {
        "titles": [
            "Dégustation des spécialités de {name}",
            "Tour gastronomique de {name}",
            "Atelier cuisine traditionnelle de {name}",
            "Marchés et saveurs de {name}",
            "Safari culinaire à {name}",
            "Initiation à la cuisine de {name}",
            "Festival des saveurs de {name}",
            "Route des épices de {name}",
        ],
        "desc": [
            "Voyage culinaire à travers les saveurs de {name}. Dégustation des plats traditionnels et visite des marchés locaux.",
            "Explorez la gastronomie locale de {name} avec un guide culinaire. Cours de cuisine et dégustations au programme.",
        ],
    },
    "adventure": {
        "titles": [
            "Aventure extrême à {name}",
            "Expédition dans les monts de {name}",
            "Défi nature — {name}",
            "Parapente au-dessus de {name}",
            "Spéléologie dans les grottes de {name}",
            "Escalade sur les falaises de {name}",
            "Nuit en bivouac à {name}",
            "Expédition 4x4 dans {name}",
        ],
        "desc": [
            "Une expérience d'aventure inoubliable à {name}. Encadrée par des guides professionnels, équipement fourni.",
            "Repoussez vos limites lors de cette expédition dans les paysages grandioses de {name}. Sensations fortes garanties.",
        ],
    },
    "wellness": {
        "titles": [
            "Détente et bien-être à {name}",
            "Journée spa à {name}",
            "Retraite bien-être dans la nature de {name}",
            "Yoga et méditation à {name}",
            "Bain thermal à {name}",
            "Hammam traditionnel à {name}",
            "Soins naturels à {name}",
        ],
        "desc": [
            "Journée de détente et de soins à {name}. Hammam traditionnel, massage et relaxation en pleine nature.",
            "Offrez-vous une parenthèse bien-être à {name}. Soins traditionnels, bains thermaux et repos au cœur de la nature.",
        ],
    },
}

SEASONAL_TEMPLATES = {
    "spring": {
        "tour": ["Oasis printanières de {name}", "Circuit des vergers en fleurs à {name}", "Route des fleurs sauvages de {name}"],
        "cultural": ["Fête du printemps à {name}", "Célébration de Yennayer à {name}"],
        "food": ["Dégustation des produits de saison à {name}", "Cueillette printanière à {name}"],
        "hiking": ["Randonnée des cimes enneigées — {name}", "Balade printanière à {name}"],
        "adventure": ["VTT dans les sentiers de {name} — Printemps", "Canopy et accrobranche à {name}"],
        "wellness": ["Massage aux huiles essentielles à {name}", "Bain de forêt à {name}"],
    },
    "summer": {
        "tour": ["Excursion balnéaire à {name}", "Circuit côtier de {name}", "Plages et criques de {name}"],
        "cultural": ["Festival d'été de {name}", "Spectacle nocturne à {name}"],
        "food": ["Dégustation de glaces artisanales à {name}", "Barbecue traditionnel à {name}"],
        "hiking": ["Randonnée nocturne à {name}", "Trek d'été dans les monts de {name}"],
        "adventure": ["Kayak et snorkeling à {name}", "Canyoning dans les gorges de {name}"],
        "wellness": ["Bain thermal nocturne à {name}", "Massage relaxant à {name}"],
    },
    "autumn": {
        "tour": ["Circuit des palmeraies de {name}", "Route des vendanges à {name}"],
        "cultural": ["Fête des récoltes à {name}", "Célébration du Mouloud à {name}"],
        "food": ["Dégustation des dattes de {name}", "Atelier confiture artisanale à {name}", "Tour des huiles d'olive de {name}"],
        "hiking": ["Randonnée aux couleurs d'automne — {name}", "Sentier des feuilles mortes à {name}"],
        "adventure": ["Traversée des canyons de {name}", "Raid VTT d'automne à {name}"],
        "wellness": ["Soin au miel et à l'huile d'argan à {name}", "Massage aux pierres chaudes à {name}"],
    },
    "winter": {
        "tour": ["Circuit hivernal de {name}", "Route des ksour de {name}", "Désert en hiver — {name}"],
        "cultural": ["Veillée traditionnelle à {name}", "Célébration du nouvel an à {name}"],
        "food": ["Atelier couscous d'hiver à {name}", "Dégustation de soupes traditionnelles à {name}"],
        "hiking": ["Randonnée sur neige à {name}", "Raquettes à {name}"],
        "adventure": ["Ski et sports d'hiver à {name}", "Nuit en igloo à {name}"],
        "wellness": ["Hammam traditionnel d'hiver à {name}", "Soin au ghassoul à {name}"],
    },
}


def fetch_wilaya_profile(cur):
    """Get per-wilaya POI counts to determine relevant categories."""
    cur.execute("""
        SELECT w.id,
               COUNT(DISTINCT CASE WHEN p.category IN ('beach','mountain','natural','park') THEN p.id END) as nature_pois,
               COUNT(DISTINCT CASE WHEN p.category IN ('cultural','historical','museum','religious') THEN p.id END) as culture_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'beach' THEN p.id END) as beach_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'mountain' THEN p.id END) as mountain_pois,
               COUNT(DISTINCT CASE WHEN p.category = 'historical' THEN p.id END) as historical_pois
        FROM wilayas w
        LEFT JOIN pois p ON p.wilaya_id = w.id
        GROUP BY w.id
        ORDER BY w.id
    """)
    profile = {}
    for row in cur.fetchall():
        wid, nature, culture, beach, mtn, hist = row
        relevant = {"tour": True, "cultural": True, "food": True}
        if mtn > 3 or nature > 10:
            relevant["hiking"] = True
            relevant["adventure"] = True
        if beach > 0:
            relevant["wellness"] = True
            relevant["adventure"] = True
        if culture > 20 or hist > 10:
            relevant["tour"] = True
            relevant["cultural"] = True
        profile[wid] = relevant
    return profile


def generate_non_seasonal(wilaya_profile, existing, rng):
    """Generate 10+ non-seasonal experiences per wilaya."""
    generated = []
    for wid, name in WILAYA_NAMES.items():
        profile = wilaya_profile.get(wid, {"tour": True, "cultural": True, "food": True})
        wanted_cats = [c for c in CATEGORIES if profile.get(c, False)]

        # How many per wilaya? 8-14 based on profile diversity
        base_count = 8 + len([c for c in wanted_cats if c in ("tour", "cultural", "hiking", "adventure")])
        for _ in range(base_count):
            cat = rng.choice(wanted_cats)
            templates = BASE_TEMPLATES[cat]
            title = rng.choice(templates["titles"]).format(name=name)
            desc = rng.choice(templates["desc"]).format(name=name)
            defaults = CATEGORY_DEFAULTS[cat]
            price = max(500, defaults["price"] + rng.randint(-500, 2000))
            dur = max(1, defaults["dur"] + rng.randint(-1, 3))
            max_p = max(2, defaults["max_p"] + rng.randint(-5, 10))
            generated.append((cat, title, wid, desc, f"{name} centre", price, dur, max_p))
    return generated


def generate_seasonal(wilaya_profile, existing_seasonal, rng):
    """Generate 3-6 seasonal per wilaya per season."""
    generated = []
    for wid, name in WILAYA_NAMES.items():
        profile = wilaya_profile.get(wid, {"tour": True, "cultural": True, "food": True})
        for season, (sd, ed) in SEASON_DATES.items():
            season_templates = SEASONAL_TEMPLATES[season]
            wanted_cats = [c for c in CATEGORIES if profile.get(c, False) and c in season_templates]
            if not wanted_cats:
                continue
            # Check existing seasonal for this wilaya+season to avoid duplicates
            existing_key = (wid, season)
            if existing_key in existing_seasonal:
                existing_cats = existing_seasonal[existing_key]
            else:
                existing_cats = set()
            # Pick 3-5 seasonal per wilaya per season
            count = min(rng.randint(3, 5), len(wanted_cats))
            chosen_cats = rng.sample(wanted_cats, min(count, len(wanted_cats)))
            for cat in chosen_cats:
                titles = season_templates[cat]
                title = rng.choice(titles).format(name=name) + SEASON_SUFFIX[season]
                defaults = CATEGORY_DEFAULTS[cat]
                desc = f"Expérience saisonnière à {name} — {season}."
                price = max(500, defaults["price"] + rng.randint(-500, 1000))
                dur = max(1, defaults["dur"] + rng.randint(-1, 2))
                max_p = max(2, defaults["max_p"] + rng.randint(-3, 8))
                generated.append((cat, title, wid, desc, f"{name} centre", price, dur, max_p, season, sd, ed))
    return generated


def main():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # Fetch provider users
    cur.execute("SELECT id FROM users WHERE phone = '+213500000001'")
    guide_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000002'")
    agency_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000003'")
    admin_row = cur.fetchone()
    provider_id = (guide_row or agency_row or admin_row)
    if not provider_id:
        print("ERROR: No provider users found. Run seed_providers.py first.")
        sys.exit(1)
    guide_id = guide_row[0] if guide_row else provider_id[0]
    agency_id = agency_row[0] if agency_row else provider_id[0]

    # Fetch existing wilayas
    cur.execute("SELECT id FROM wilayas")
    existing_wilayas = {row[0] for row in cur.fetchall()}
    print(f"Wilayas in DB: {len(existing_wilayas)}")

    # ---- 1. Count existing ----
    cur.execute("SELECT COUNT(*) FROM experiences")
    current_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM experiences WHERE season IS NULL")
    current_nonseasonal = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM experiences WHERE season IS NOT NULL")
    current_seasonal = cur.fetchone()[0]
    cur.execute("SELECT season, COUNT(*) FROM experiences WHERE season IS NOT NULL GROUP BY season ORDER BY season")
    seasonal_counts = {r[0]: r[1] for r in cur.fetchall()}
    cur.execute("SELECT COUNT(DISTINCT wilaya_id) FROM experiences WHERE season IS NULL")
    ns_wilayas = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT wilaya_id) FROM experiences WHERE season IS NOT NULL")
    s_wilayas = cur.fetchone()[0]
    print(f"\nCurrent: Total={current_total}, Non-seasonal={current_nonseasonal} ({ns_wilayas} wil), Seasonal={current_seasonal} ({s_wilayas} wil)")
    for s, c in seasonal_counts.items():
        print(f"  {s}: {c}")

    # ---- 2. Get wilaya profiles ----
    wilaya_profile = fetch_wilaya_profile(cur)

    # ---- 3. Track existing titles to avoid exact duplicates ----
    cur.execute("SELECT title FROM experiences")
    existing_titles = {row[0].strip().lower() for row in cur.fetchall()}

    # Existing non-seasonal per wilaya
    cur.execute("SELECT wilaya_id, category FROM experiences WHERE season IS NULL")
    existing_ns_by_wilaya = {}
    for wid, cat in cur.fetchall():
        existing_ns_by_wilaya.setdefault(wid, set()).add(cat)

    # Existing seasonal per wilaya+season
    cur.execute("SELECT wilaya_id, season FROM experiences WHERE season IS NOT NULL")
    existing_seasonal = {}
    for wid, season in cur.fetchall():
        existing_seasonal.setdefault((wid, season), set())

    # ---- 4. Build batch ----
    rng = random.Random(42)  # deterministic
    experiences = []
    skipped = 0

    def add_to_batch(cat, title, wid, desc, meeting, price, dur, max_p, is_seasonal=False, season=None, sd=None, ed=None):
        nonlocal skipped
        key = title.strip().lower()
        if key in existing_titles:
            skipped += 1
            return
        if wid not in existing_wilayas:
            return
        provider = guide_id if cat in ("hiking", "adventure") else agency_id
        existing_titles.add(key)
        experiences.append((
            uuid.uuid4(), provider, cat, title, desc, wid,
            meeting, price, dur, max_p, "FR", None, None, "active",
            season, sd, ed,
            "programmatic", None, False, 0,
        ))

    # Non-seasonal
    ns_rows = generate_non_seasonal(wilaya_profile, existing_ns_by_wilaya, rng)
    for row in ns_rows:
        cat, title, wid, desc, meeting, price, dur, max_p = row
        add_to_batch(cat, title, wid, desc, meeting, price, dur, max_p)

    # Seasonal
    s_rows = generate_seasonal(wilaya_profile, existing_seasonal, rng)
    for row in s_rows:
        cat, title, wid, desc, meeting, price, dur, max_p, season, sd, ed = row
        add_to_batch(cat, title, wid, desc, meeting, price, dur, max_p,
                     is_seasonal=True, season=season, sd=sd, ed=ed)

    print(f"\nGenerated: {len(experiences)} new, {skipped} skipped (duplicates)")

    # ---- 5. Bulk insert ----
    insert_sql = """
        INSERT INTO experiences
            (id, provider_id, category, title, description, wilaya_id,
             meeting_point, price_dzd, duration_hours, max_participants,
             language, included, what_to_bring, status,
             season, start_date, end_date,
             source, source_url, is_verified, completion_count)
        VALUES %s
    """

    rows = []
    for e in experiences:
        rows.append((
            str(e[0]), str(e[1]), e[2], e[3], e[4], e[5],
            e[6], e[7], e[8], e[9],
            e[10], e[11], e[12], e[13],
            e[14], e[15], e[16],
            e[17], e[18], e[19], e[20],
        ))

    try:
        execute_values(cur, insert_sql, rows, page_size=200)
        conn.commit()
        print(f"Inserted {len(rows)} new experiences")

        # Final counts
        cur.execute("SELECT COUNT(*) FROM experiences")
        final_total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM experiences WHERE season IS NULL")
        final_ns = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM experiences WHERE season IS NOT NULL")
        final_s = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM experiences WHERE source = 'programmatic'")
        prog_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM experiences WHERE is_verified = true")
        verified = cur.fetchone()[0]
        cur.execute("SELECT season, COUNT(*) FROM experiences WHERE season IS NOT NULL GROUP BY season ORDER BY season")
        print("\n=== Final counts ===")
        for r in cur.fetchall():
            print(f"  {r[0]:8s}: {r[1]}")
        cur.execute("SELECT COUNT(DISTINCT wilaya_id) FROM experiences WHERE season IS NULL")
        print(f"  Non-seasonal wilayas: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(DISTINCT wilaya_id) FROM experiences WHERE season IS NOT NULL")
        print(f"  Seasonal wilayas: {cur.fetchone()[0]}")
        print(f"  Total: {final_total} (+{final_total - current_total})")
        print(f"  Non-seasonal: {final_ns} (+{final_ns - current_nonseasonal})")
        print(f"  Seasonal: {final_s} (+{final_s - current_seasonal})")
        print(f"  Source=programmatic: {prog_count}")
        print(f"  Verified: {verified}")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
