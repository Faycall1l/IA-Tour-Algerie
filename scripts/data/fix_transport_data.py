"""Fix transport data quality: train stops, wilaya connectivity flags.

Phase 1a: Fix has_train_route / has_direct_flight flags
Phase 1b: Fix train line stops mapped to wrong station types

Reads SNTF train lines → finds stops on non-train stations → remaps to nearest
real SNTF station in same wilaya. Updates wilaya_distances flags based on actual
line connectivity.
"""
import math
from collections import defaultdict

from sqlalchemy import create_engine, text

engine = create_engine("postgresql://athar:athar_pass@localhost:5432/athar_db")


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


with engine.connect() as conn:
    # ============================================================
    # PHASE 1b: Fix train line stops mapped to wrong stations
    # ============================================================
    print("=" * 60)
    print("PHASE 1b: Fixing train line stops...")
    print("=" * 60)

    # Load all SNTF train stations for lookup
    r = conn.execute(text("SELECT id, name, wilaya_id, latitude, longitude FROM stations WHERE operator = 'SNTF'"))
    sntf_stations = {}
    for row in r:
        wid = row[2]
        if wid not in sntf_stations:
            sntf_stations[wid] = []
        sntf_stations[wid].append({
            "id": row[0], "name": row[1], "wilaya_id": wid,
            "lat": row[3], "lon": row[4],
        })

    # Find bad train stops
    r = conn.execute(text("""
        SELECT ls.id as ls_id, ls.line_id, ls.stop_order, ls.station_id,
               s.name as station_name, s.wilaya_id, s.latitude as s_lat, s.longitude as s_lon,
               tl.name as line_name
        FROM line_stops ls
        JOIN stations s ON ls.station_id = s.id
        JOIN transport_lines tl ON ls.line_id = tl.id
        WHERE tl.mode = 'train' AND s.station_type != 'train'
    """))
    bad_stops = [dict(row._mapping) for row in r]
    print(f"Found {len(bad_stops)} train stops on non-train stations")

    fixed = 0
    unmapped = 0
    for stop in bad_stops:
        wid = stop["wilaya_id"]
        candidates = sntf_stations.get(wid, [])
        if not candidates:
            print(f"  SKIP (no SNTF in wilaya {wid}): {stop['line_name'][:40]} → {stop['station_name']}")
            unmapped += 1
            continue

        # Find nearest SNTF station
        best = min(candidates, key=lambda c: haversine(stop["s_lat"], stop["s_lon"], c["lat"], c["lon"]))
        dist = haversine(stop["s_lat"], stop["s_lon"], best["lat"], best["lon"])

        if dist > 80:
            print(f"  WARN (too far {dist:.0f}km): {stop['line_name'][:40]} → {stop['station_name']} → {best['name']}")
            unmapped += 1
            continue

        # Update the line_stop to point to the correct SNTF station
        conn.execute(text("UPDATE line_stops SET station_id = :new_id WHERE id = :ls_id"),
                     {"new_id": best["id"], "ls_id": stop["ls_id"]})
        fixed += 1
        if fixed <= 10 or fixed % 10 == 0:
            print(f"  FIXED: {stop['station_name'][:30]:30s} → {best['name'][:30]:30s} ({dist:.0f}km) [{stop['line_name'][:35]}]")

    print(f"\nFixed: {fixed}, Unmapped: {unmapped}")

    # ============================================================
    # PHASE 1a: Fix has_train_route / has_direct_flight flags
    # ============================================================
    print("\n" + "=" * 60)
    print("PHASE 1a: Fixing wilaya connectivity flags...")
    print("=" * 60)

    # Build connectivity from actual line stops (after fix)
    train_wilaya_pairs = set()
    r = conn.execute(text("""
        SELECT DISTINCT s1.wilaya_id as w1, s2.wilaya_id as w2
        FROM line_stops ls1
        JOIN line_stops ls2 ON ls1.line_id = ls2.line_id AND ls1.station_id != ls2.station_id
        JOIN stations s1 ON ls1.station_id = s1.id
        JOIN stations s2 ON ls2.station_id = s2.id
        JOIN transport_lines tl ON ls1.line_id = tl.id
        WHERE tl.mode = 'train'
    """))
    for row in r:
        a, b = (row[0], row[1]) if row[0] < row[1] else (row[1], row[0])
        train_wilaya_pairs.add((a, b))
    print(f"Train-connected wilaya pairs: {len(train_wilaya_pairs)}")

    flight_wilaya_pairs = set()
    r = conn.execute(text("""
        SELECT DISTINCT s1.wilaya_id as w1, s2.wilaya_id as w2
        FROM line_stops ls1
        JOIN line_stops ls2 ON ls1.line_id = ls2.line_id AND ls1.station_id != ls2.station_id
        JOIN stations s1 ON ls1.station_id = s1.id
        JOIN stations s2 ON ls2.station_id = s2.id
        JOIN transport_lines tl ON ls1.line_id = tl.id
        WHERE tl.mode = 'flight'
    """))
    for row in r:
        a, b = (row[0], row[1]) if row[0] < row[1] else (row[1], row[0])
        flight_wilaya_pairs.add((a, b))
    print(f"Flight-connected wilaya pairs: {len(flight_wilaya_pairs)}")

    # Update wilaya_distances
    r = conn.execute(text("SELECT origin_wilaya_id, dest_wilaya_id, has_train_route, has_direct_flight FROM wilaya_distances"))
    updates = 0
    train_fixed = 0
    flight_fixed = 0
    for row in r:
        ow, dw = row[0], row[1]
        a, b = (ow, dw) if ow < dw else (dw, ow)
        has_train = (a, b) in train_wilaya_pairs
        has_flight = (a, b) in flight_wilaya_pairs
        if has_train != row[2] or has_flight != row[3]:
            conn.execute(text("""
                UPDATE wilaya_distances
                SET has_train_route = :train, has_direct_flight = :flight
                WHERE origin_wilaya_id = :ow AND dest_wilaya_id = :dw
            """), {"train": has_train, "flight": has_flight, "ow": ow, "dw": dw})
            updates += 1
            if has_train and not row[2]:
                train_fixed += 1
            if has_flight and not row[3]:
                flight_fixed += 1

    print(f"Updated: {updates} pairs ({train_fixed} newly train-connected, {flight_fixed} newly flight-connected)")

    # Verify Boumerdes↔Oran
    r = conn.execute(text("""
        SELECT has_train_route, has_direct_flight FROM wilaya_distances
        WHERE (origin_wilaya_id=35 AND dest_wilaya_id=31) OR (origin_wilaya_id=31 AND dest_wilaya_id=35)
    """))
    row = r.fetchone()
    print(f"\nBoumerdes↔Oran after fix: train={row[0]}, flight={row[1]}")

    # Show total train/flight pairs
    r = conn.execute(text("SELECT COUNT(*) FROM wilaya_distances WHERE has_train_route = true"))
    print(f"Total train-connected pairs: {r.scalar()}")
    r = conn.execute(text("SELECT COUNT(*) FROM wilaya_distances WHERE has_direct_flight = true"))
    print(f"Total flight-connected pairs: {r.scalar()}")

    conn.commit()
    print("\nDONE — all changes committed.")

engine.dispose()
