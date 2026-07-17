"""
Seed price calendar data for experiences and stays.
Generates 90 days of pricing for each entity with seasonal variation.
Run after all experiences/stays are seeded.
"""

import sys
import uuid
from datetime import date, timedelta

import psycopg2

DB_DSN = "postgresql://athar:athar_pass@localhost:5432/athar_db"

# ── Configuration ─────────────────────────────────────────────
SUMMER_PEAK = (date(2026, 7, 1), date(2026, 8, 31))  # peak pricing
SHOULDER = (date(2026, 6, 1), date(2026, 9, 30))      # high-ish
LOW = (date(2026, 10, 1), date(2026, 12, 31))         # off-season

DAYS_AHEAD = 90
START = date.today()
END = START + timedelta(days=DAYS_AHEAD)

WEEKEND = {5, 6}  # Friday/Saturday in Algeria


def price_variation(base: float, season_factor: float, day_of_week: int) -> float:
    """Apply ±20% seasonal + ±10% weekend adjustments."""
    weekend_factor = 1.10 if day_of_week in WEEKEND else 1.0
    return round(base * season_factor * weekend_factor, -1)  # round to nearest 10 DZD


def generate_stay_prices(stay: dict) -> list[tuple]:
    """Generate 90 days of pricing for a stay."""
    rows = []
    base = stay["price_per_night_dzd"]
    sid = stay["id"]
    for i in range(DAYS_AHEAD):
        d = START + timedelta(days=i)
        if SUMMER_PEAK[0] <= d <= SUMMER_PEAK[1]:
            factor = 1.20
        elif SHOULDER[0] <= d <= SHOULDER[1]:
            factor = 1.05
        else:
            factor = 0.85
        price = price_variation(base, factor, d.weekday())
        max_spots = max(1, (stay.get("total_rooms") or 10))
        avail = int(max_spots * (0.9 if d.weekday() in WEEKEND else 0.6))
        rows.append((uuid.uuid4(), sid, "stay", d, price, max(avail, 1)))
    return rows


def generate_experience_prices(exp: dict) -> list[tuple]:
    """Generate 90 days of pricing for an experience."""
    rows = []
    base = exp.get("price_dzd") or 1500
    eid = exp["id"]
    max_pax = exp.get("max_participants") or 10
    for i in range(DAYS_AHEAD):
        d = START + timedelta(days=i)
        if SUMMER_PEAK[0] <= d <= SUMMER_PEAK[1]:
            factor = 1.15
        elif SHOULDER[0] <= d <= SHOULDER[1]:
            factor = 1.0
        else:
            factor = 0.90
        price = price_variation(base, factor, d.weekday())
        avail = int(max_pax * (0.8 if d.weekday() in WEEKEND else 0.4))
        rows.append((uuid.uuid4(), eid, "experience", d, price, max(avail, 1)))
    return rows


def main():
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    # Fetch stays
    cur.execute("SELECT id, price_per_night_dzd, total_rooms FROM stays")
    stays = [
        {"id": r[0], "price_per_night_dzd": r[1], "total_rooms": r[2]}
        for r in cur.fetchall()
    ]
    print(f"📦 Found {len(stays)} stays")

    # Fetch experiences
    cur.execute("SELECT id, price_dzd, max_participants FROM experiences WHERE status = 'active'")
    exps = [
        {"id": r[0], "price_dzd": r[1], "max_participants": r[2]}
        for r in cur.fetchall()
    ]
    print(f"📦 Found {len(exps)} active experiences")

    # Generate
    all_rows = []
    for s in stays:
        all_rows.extend(generate_stay_prices(s))
    for e in exps:
        all_rows.extend(generate_experience_prices(e))

    print(f"📊 Generated {len(all_rows)} price entries")

    # Delete existing data
    cur.execute("DELETE FROM price_calendar")
    conn.commit()

    # Batch insert in chunks
    insert_sql = """
        INSERT INTO price_calendar
            (id, entity_id, entity_type, date, price_dzd, available_spots)
        VALUES (%s, %s::uuid, %s, %s::date, %s, %s)
    """
    chunk_size = 1000
    for i in range(0, len(all_rows), chunk_size):
        chunk = all_rows[i:i + chunk_size]
        rows_data = [(str(r[0]), str(r[1]), r[2], r[3].isoformat(), r[4], r[5]) for r in chunk]
        cur.executemany(insert_sql, rows_data)
    conn.commit()

    # Verify
    cur.execute("SELECT entity_type, COUNT(*) FROM price_calendar GROUP BY entity_type")
    for row in cur.fetchall():
        print(f"  ✅ {row[0]}: {row[1]:,} entries")

    cur.execute("SELECT COUNT(*) FROM price_calendar")
    total = cur.fetchone()[0]
    print(f"\n🎯 Total price calendar entries: {total:,}")

    cur.close()
    conn.close()
    print("✅ Price calendar seeded successfully")


if __name__ == "__main__":
    main()
