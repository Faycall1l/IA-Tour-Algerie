#!/usr/bin/env python3
"""Add pricing data to stays/POIs and seed events/festivals.

Deterministic: prices are derived from the record id hash (stable across
runs), never from RANDOM(). Event seeding is idempotent — the EVENTS list
is the canonical set and is re-synced on every run.
"""

import hashlib
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

# Estimated stay pricing by property type (DZD/night)
STAY_PRICES = {
    "hotel":       (3000, 15000),  # budget–luxe
    "guesthouse":  (2000, 8000),
    "hostel":      (800, 3000),
    "eco_lodge":   (2500, 12000),
    "riad":        (4000, 20000),
    "apartment":   (3000, 10000),
}

# Estimated POI entry fees by category (DZD)
POI_ENTRY_FEES = {
    "museum":     (200, 500),
    "historical": (0, 200),
    "natural":    (0, 100),
    "cultural":   (0, 150),
    "beach":      (0, 0),
    "park":       (0, 100),
    "mountain":   (0, 0),
    "religious":  (0, 0),
}

# Major Algerian festivals and events
EVENTS = [
    # (title_fr, wilaya_id, month, category, description)
    ("Festival International du Film Arabe", 16, 8, "cultural", "Festival international du film arabe à Oran, événement majeur du cinéma maghrébin"),
    ("Festival International de la Musique Symphonique", 16, 7, "cultural", "Festival de musique classique et symphonique d'Alger"),
    ("Festival Culturel Panafricain d'Alger", 16, 7, "cultural", "Grand festival panafricain célébrant les arts et la culture du continent"),
    ("Festival National du Film Amazigh", 6, 9, "cultural", "Festival dédié au cinéma amazigh à Béjaïa"),
    ("Festival International de la Calligraphie Arabe", 16, 6, "cultural", "Exposition et concours de calligraphie arabe à Alger"),
    ("Hoggar Festival", 11, 1, "cultural", "Festival des arts et traditions du Hoggar à Tamanrasset"),
    ("Festival des Nomades", 11, 12, "cultural", "Festival des cultures nomades dans le Sahara algérien"),
    ("Ghardaïa Spring Festival", 47, 3, "cultural", "Festival du printemps célébrant la culture mozabite à Ghardaïa"),
    ("Timgad International Festival", 5, 7, "cultural", "Festival international de musique au théâtre antique de Timgad"),
    ("Cherchell International Festival", 42, 8, "cultural", "Festival d'art et de culture au théâtre romain de Cherchell"),
    ("Djemila International Festival", 19, 8, "cultural", "Festival de musique et danse au site romain de Djemila (Sétif)"),
    ("Tlemcen Cultural Festival", 13, 5, "cultural", "Festival de la culture et des arts de Tlemcen"),
    ("Festival du CSP", 23, 6, "cultural", "Festival culturel et sportif d'Annaba"),
    ("Constantine International Festival", 25, 4, "cultural", "Festival international des arts de Constantine, capitale de la culture"),
    ("Souk Ahras Festival", 41, 7, "cultural", "Festival des arts populaires de Souk Ahras"),
    ("Festival de la Grappe à Bouira", 10, 9, "food", "Festival des vendanges et du raisin de Bouira"),
    ("Festival de la Cerise de Larbaâ Nath Irathen", 15, 6, "food", "Festival de la cerise en Kabylie (Tizi Ouzou)"),
    ("Festival de l'Orange de Boufarik", 9, 2, "food", "Festival des agrumes de Boufarik (Blida)"),
    ("Festival de la Datte de Tolga", 7, 10, "food", "Festival des dattes de Tolga (Biskra)"),
    ("Festival de l'Huile d'Olive de Kabylie", 15, 11, "food", "Festival de l'huile d'olive en Kabylie"),
    ("Sahara International Marathon", 11, 2, "adventure", "Marathon international du Sahara à Tamanrasset"),
    ("Rallye des Sables", 47, 3, "adventure", "Rallye-raid dans le désert du M'zab (Ghardaïa)"),
    ("Trek du Hoggar", 11, 11, "hiking", "Randonnée trekking de plusieurs jours dans le massif du Hoggar"),
    ("Trek du Tassili n'Ajjer", 33, 10, "hiking", "Randonnée trekking dans le parc national du Tassili (Illizi)"),
    ("Cuisine Algérienne Week", 16, 5, "food", "Semaine de la gastronomie algérienne avec ateliers et dégustations"),
    ("Festival des Danses Populaires", 31, 7, "cultural", "Festival de danses et musiques traditionnelles oranaises"),
    ("Journées du Patrimoine Algérien", 16, 5, "cultural", "Journées portes ouvertes des sites historiques et musées à travers l'Algérie"),
    ("Exposition Internationale de l'Artisanat", 16, 12, "cultural", "Exposition d'artisanat traditionnel algérien au SAFEX (Alger)"),
    ("Tassili Night Festival", 33, 12, "cultural", "Festival d'astronomie et nuit des étoiles dans le Tassili (Djanet)"),
    ("Fête du Tapis de Khenchela", 40, 6, "cultural", "Exposition et vente de tapis traditionnels berbères à Khenchela"),
    ("Atlas International Mountain Festival", 14, 5, "adventure", "Festival des sports de montagne dans l'Atlas saharien (Tiaret)"),
    ("Festival du Mouton de Béni Abbès", 50, 11, "cultural", "Festival des traditions pastorales à Béni Abbès"),
    ("Festival de la Mer et de la Plage", 27, 7, "beach", "Festival des sports nautiques et activités balnéaires à Mostaganem"),
    ("Journées Cinématographiques de Béjaïa", 6, 9, "cultural", "Festival de courts-métrages amazighs et méditerranéens"),
    ("Festival International des Arts de la Rue", 16, 6, "cultural", "Festival d'arts de rue et spectacles urbains à Alger"),
    ("Souk El Guerza", 21, 8, "cultural", "Marché artisanal traditionnel et festival folklorique de Skikda"),
    ("Regatta Internationale d'Alger", 16, 5, "adventure", "Régate de voile internationale dans la baie d'Alger"),
    ("Cyclotourisme de l'Atlas Blidéen", 9, 4, "adventure", "Randonnée cyclotourisme dans les montagnes de Blida (Chréa)"),
    ("Randonnée des Gorges de Koudiat Acerdoune", 10, 5, "hiking", "Randonnée guidée dans les gorges spectaculaires de Bouira"),
    ("Plongée sous-marine à Tipaza", 42, 6, "adventure", "Sorties de plongée sous-marine aux ruines romaines immergées de Tipaza"),
]


def _deterministic_value(record_id, low, high):
    """Deterministic int in [low, high] derived from the record id."""
    digest = int(hashlib.md5(str(record_id).encode()).hexdigest(), 16)
    return low + (digest % (high - low + 1))


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    print("=== Pricing & Events Enrichment ===\n")

    # ---- 1. Stay pricing ----
    print("--- Stay Pricing ---")
    for ptype, (low, high) in STAY_PRICES.items():
        cur.execute(
            "SELECT id FROM stays WHERE property_type = %s AND (price_per_night_dzd IS NULL OR price_per_night_dzd = 0)",
            (ptype,),
        )
        ids = [r[0] for r in cur.fetchall()]
        for pid in ids:
            cur.execute(
                "UPDATE stays SET price_per_night_dzd = %s WHERE id = %s",
                (_deterministic_value(pid, low, high), pid),
            )
        print(f"  {ptype}: {len(ids)} stays priced ({low}-{high} DZD)")

    conn.commit()

    # ---- 2. POI entry fees ----
    print("\n--- POI Entry Fees ---")
    for cat, (low, high) in POI_ENTRY_FEES.items():
        if low == 0 and high == 0:
            cur.execute("""
                UPDATE pois SET entry_fee_dzd = 0
                WHERE category = %s AND (entry_fee_dzd IS NULL)
            """, (cat,))
            rows = cur.rowcount
        else:
            cur.execute(
                "SELECT id FROM pois WHERE category = %s AND (entry_fee_dzd IS NULL OR entry_fee_dzd = 0)",
                (cat,),
            )
            ids = [r[0] for r in cur.fetchall()]
            for pid in ids:
                cur.execute(
                    "UPDATE pois SET entry_fee_dzd = %s WHERE id = %s",
                    (_deterministic_value(pid, low, high), pid),
                )
            rows = len(ids)
        print(f"  {cat}: {rows} POIs priced ({low}-{high} DZD)")

    conn.commit()

    # ---- 3. Events table ----
    print("\n--- Events/Festivals ---")
    # Check if events table exists
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables WHERE table_name = 'events'
        )
    """)
    exists = cur.fetchone()[0]

    if not exists:
        cur.execute("""
            CREATE TABLE events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(200) NOT NULL,
                wilaya_id INTEGER REFERENCES wilayas(id) NOT NULL,
                category VARCHAR(50) NOT NULL,
                description TEXT,
                month INTEGER NOT NULL CHECK (month >= 1 AND month <= 12),
                duration_days INTEGER DEFAULT 1,
                is_recurring BOOLEAN DEFAULT TRUE,
                photo_url VARCHAR(500),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("CREATE INDEX ix_events_month ON events(month)")
        print("  Created events table")
        conn.commit()

    # Drop legacy duplicate index (schema model owns ix_events_wilaya_id)
    cur.execute("DROP INDEX IF EXISTS ix_events_wilaya")
    conn.commit()

    # Sync: EVENTS is the canonical list — wipe and re-insert for idempotency
    cur.execute("DELETE FROM events")
    count = 0
    for title, wid, month, category, desc in EVENTS:
        cur.execute(
            "INSERT INTO events (title, wilaya_id, month, category, description) VALUES (%s, %s, %s, %s, %s)",
            (title, wid, month, category, desc),
        )
        count += cur.rowcount

    conn.commit()
    print(f"  Inserted {count} events")

    # ---- 4. Verify results ----
    print("\n--- Summary ---")
    cur.execute("SELECT COUNT(*) FROM stays WHERE price_per_night_dzd > 0")
    print(f"  Stays with real pricing: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM pois WHERE entry_fee_dzd IS NOT NULL")
    print(f"  POIs with entry fees: {cur.fetchone()[0]}")
    cur.execute("SELECT COUNT(*) FROM events")
    print(f"  Events in DB: {cur.fetchone()[0]}")

    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
