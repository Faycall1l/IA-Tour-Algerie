#!/usr/bin/env python3
"""Fix wilaya numbering to match the official 2026 administrative map (69 wilayas).

Problems fixed:
1. Wilayas 50-58 were stored in alphabetical-by-French order (Béni Abbès=50, Aïn
   Salah=51, ...) instead of the official order from Loi 19-12/2019 (Bordj Badji
   Mokhtar=50, Ouled Djellal=51, Béni Abbès=52, In Salah=53, In Guezzam=54,
   Touggourt=55, Djanet=56, El M'Ghair=57, El Meniaa=58).
2. Wilayas 59-69 were placeholder transport hubs (Hub Transport, Port Maritime, ...).
   They are replaced by the 11 real wilayas created by Loi 26-06/2026 (JO n°25) +
   décret présidentiel 26-206 du 25 mai 2026 (JO n°40): Aflou, Barika, El Kantara,
   Bir El Ater, El Aricha, Ksar Chellala, Aïn Ouessara, Messaad, Ksar El Boukhari,
   Bou Saâda, El Abiodh Sidi Cheikh.
3. All child rows are remapped. POIs/stays/events in 50-58 are pure ID remaps
   (they were assigned by proximity to the DB's centers, which have correct
   coordinates). Experiences in 59-69 were seeded in dz-admin's wrong order and
   are remapped by wilaya name. Stations in 59-69 mix real new-wilaya stations
   with strays and are reassigned by nearest official center.

Usage: python scripts/data/fix_wilaya_numbering.py
WARNING: one-time migration. Guarded against re-runs on the fixed DB;
         the child remap below chains (see fix_wilaya_chain.py).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

# Official wilayas 50-69: id -> (name_fr, name_ar, name_en, lat, lng)
# 50-58 order per Loi 19-12/2019; 59-69 per décret 26-206 (JO n°40).
OFFICIAL_50_69: dict[int, tuple[str, str, str, float, float]] = {
    50: ("Bordj Badji Mokhtar", "برج باجي مختار", "Bordj Badji Mokhtar", 21.3275, 0.915),
    51: ("Ouled Djellal", "أولاد جلال", "Ouled Djellal", 34.4267, 5.0642),
    52: ("Béni Abbès", "بني عباس", "Beni Abbes", 30.0833, -2.1667),
    53: ("In Salah", "عين صالح", "In Salah", 27.1936, 2.4828),
    54: ("In Guezzam", "عين قزام", "In Guezzam", 19.5656, 5.7725),
    55: ("Touggourt", "تقرت", "Touggourt", 33.1044, 6.0683),
    56: ("Djanet", "جانت", "Djanet", 24.5547, 9.4847),
    57: ("El M'Ghair", "المغير", "El M'Ghair", 33.9486, 5.9217),
    58: ("El Meniaa", "المنيعة", "El Meniaa", 30.5833, 2.8833),
    59: ("Aflou", "أفلو", "Aflou", 34.11279, 2.1019),
    60: ("Barika", "بريكة", "Barika", 35.3972, 5.3658),
    61: ("El Kantara", "القنطرة", "El Kantara", 35.192365, 5.6668306),
    62: ("Bir El Ater", "بئر العاتر", "Bir El Ater", 34.748, 8.0594),
    63: ("El Aricha", "العريشة", "El Aricha", 34.22259, -1.257),
    64: ("Ksar Chellala", "قصر الشلالة", "Ksar Chellala", 35.21222, 2.3189),
    65: ("Aïn Ouessara", "عين وسارة", "Ain Ouessara", 35.4542653, 2.904444),
    66: ("Messaad", "مسعد", "Messaad", 34.15429, 3.50309),
    67: ("Ksar El Boukhari", "قصر البخاري", "Ksar El Boukhari", 35.88889, 2.74905),
    68: ("Bou Saâda", "بوسعادة", "Bou Saada", 35.2091, 4.1744),
    69: (
        "El Abiodh Sidi Cheikh",
        "الأبيض سيدي الشيخ",
        "El Abiodh Sidi Cheikh",
        32.898611,
        0.544444,
    ),
}

# DB id -> official id for the alphabetized 50-58 (old names carried correct coords)
RENUMBER_50_58: dict[int, int] = {
    50: 52,  # Béni Abbès -> official 52
    51: 53,  # Aïn Salah -> In Salah 53
    52: 54,  # Aïn Guezzam -> In Guezzam 54
    53: 55,  # Touggourt
    54: 56,  # Djanet
    55: 57,  # El M'Ghair
    56: 58,  # El Meniaa
    57: 51,  # Ouled Djellal
    58: 50,  # Bordj Badji Mokhtar
}

# Experiences in 59-69 were seeded with dz-admin's wrong order: dz id -> official id
EXPERIENCE_REMAP_59_69: dict[int, int] = {
    59: 59,  # Aflou
    60: 69,  # El Abiodh Sidi Cheikh
    61: 63,  # El Aricha
    62: 61,  # El Kantara
    63: 60,  # Barika
    64: 68,  # Bou Saâda
    65: 62,  # Bir El Ater
    66: 67,  # Ksar El Boukhari
    67: 64,  # Ksar Chellala
    68: 65,  # Aïn Oussara
    69: 66,  # Messaad
}

FK_CONSTRAINTS = [
    ("pois", "pois_wilaya_id_fkey", "NO ACTION"),
    ("stations", "stations_wilaya_id_fkey", "CASCADE"),
    ("stays", "stays_wilaya_id_fkey", "NO ACTION"),
    ("experiences", "experiences_wilaya_id_fkey", "NO ACTION"),
    ("events", "events_wilaya_id_fkey", "NO ACTION"),
    ("artisans", "artisans_wilaya_id_fkey", "NO ACTION"),
    ("wilaya_distances", "wilaya_distances_origin_wilaya_id_fkey", "CASCADE"),
    ("wilaya_distances", "wilaya_distances_dest_wilaya_id_fkey", "CASCADE"),
    ("transport_operators", "transport_operators_headquarters_wilaya_id_fkey", "NO ACTION"),
]


async def main() -> None:
    async with async_session() as session:
        # Safety guard: this script must run ONLY on the pre-migration DB
        # (where id 50 was Béni Abbès). Re-running it on the fixed DB would
        # re-chain child rows; use fix_wilaya_chain.py instead.
        w50 = (
            await session.execute(text("SELECT name_fr FROM wilayas WHERE id = 50"))
        ).scalar_one_or_none()
        if w50 != "Béni Abbès":
            print(
                f"ABORT: wilaya 50 is '{w50}' — DB already migrated. "
                "Re-run is unsafe (chaining bug); see fix_wilaya_chain.py."
            )
            return
        async with session.begin():
            # Sanity checks
            names = dict((await session.execute(text("SELECT id, name_fr FROM wilayas"))).all())
            for old, new in RENUMBER_50_58.items():
                print(f"  renumber {old} {names[old]} -> {new} {names.get(new)}")
            for wid in range(59, 70):
                print(f"  replace {wid} {names[wid]} -> {OFFICIAL_50_69[wid][0]}")

            # ---- 1. Drop FKs referencing wilayas (need free id moves) ----
            for tbl, con, _ in FK_CONSTRAINTS:
                await session.execute(text(f"ALTER TABLE {tbl} DROP CONSTRAINT {con}"))

            # ---- 2. Move wilayas 50-58 to temp ids (+100) ----
            for old in RENUMBER_50_58:
                await session.execute(
                    text("UPDATE wilayas SET id = id + 100 WHERE id = :old"), {"old": old}
                )
            # ---- 3. Renumber to official ids + fix names/coords ----
            for official, (fr, ar, en, lat, lng) in OFFICIAL_50_69.items():
                if official <= 58:
                    await session.execute(
                        text("""
                            UPDATE wilayas SET id = :new, name_fr = :fr, name_ar = :ar,
                                name_en = :en, latitude = :lat, longitude = :lng
                            WHERE id = :tmp
                        """),
                        {
                            "new": official,
                            "fr": fr,
                            "ar": ar,
                            "en": en,
                            "lat": lat,
                            "lng": lng,
                            "tmp": official + 100,
                        },
                    )
                else:
                    await session.execute(
                        text("""
                            UPDATE wilayas SET name_fr = :fr, name_ar = :ar,
                                name_en = :en, latitude = :lat, longitude = :lng
                            WHERE id = :wid
                        """),
                        {"wid": official, "fr": fr, "ar": ar, "en": en, "lat": lat, "lng": lng},
                    )

            # ---- 4. Remap child tables (50-58: pure ID remap) ----
            # NOTE: sequential UPDATEs in dict order CHAIN (each step
            # re-captures rows moved by the previous one). This ran once on
            # the pre-migration DB; fix_wilaya_chain.py untangles the result.
            for tbl in ("pois", "stations", "stays", "events", "artisans"):
                for old, new in RENUMBER_50_58.items():
                    await session.execute(
                        text(f"UPDATE {tbl} SET wilaya_id = :new WHERE wilaya_id = :old"),
                        {"new": new, "old": old},
                    )

            # experiences 50-58 pure ID remap
            for old, new in RENUMBER_50_58.items():
                await session.execute(
                    text("UPDATE experiences SET wilaya_id = :new WHERE wilaya_id = :old"),
                    {"new": new, "old": old},
                )
            # experiences 59-69 remap by wilaya name (dz-admin order -> official)
            for dz_id, off_id in EXPERIENCE_REMAP_59_69.items():
                await session.execute(
                    text("UPDATE experiences SET wilaya_id = :new WHERE wilaya_id = :old"),
                    {"new": off_id, "old": dz_id},
                )

            # ---- 5. Reassign stations 59-69 by nearest official center ----
            centers = {
                r[0]: (r[1], r[2])
                for r in (
                    await session.execute(text("SELECT id, latitude, longitude FROM wilayas"))
                ).all()
            }
            stations_5969 = (
                await session.execute(
                    text(
                        "SELECT id, latitude, longitude FROM stations "
                        "WHERE wilaya_id BETWEEN 59 AND 69"
                    )
                )
            ).all()
            for st_id, lat, lng in stations_5969:
                if lat is None or lng is None:
                    continue
                best, best_d = None, float("inf")
                for wid, (wlat, wlng) in centers.items():
                    d = (lat - wlat) ** 2 + (lng - wlng) ** 2
                    if d < best_d:
                        best, best_d = wid, d
                if best is not None:
                    await session.execute(
                        text("UPDATE stations SET wilaya_id = :wid WHERE id = :sid"),
                        {"wid": best, "sid": st_id},
                    )
            print(f"  reassigned {len(stations_5969)} stations by nearest center")

            # ---- 6. wilaya_distances: remap 50-58 endpoints (temp +100 first) ----
            # move both endpoints to temp
            for old in RENUMBER_50_58:
                await session.execute(
                    text("""
                        UPDATE wilaya_distances SET origin_wilaya_id = origin_wilaya_id + 100
                        WHERE origin_wilaya_id = :old
                    """),
                    {"old": old},
                )
                await session.execute(
                    text("""
                        UPDATE wilaya_distances SET dest_wilaya_id = dest_wilaya_id + 100
                        WHERE dest_wilaya_id = :old
                    """),
                    {"old": old},
                )
            for old, new in RENUMBER_50_58.items():
                await session.execute(
                    text("""
                        UPDATE wilaya_distances SET origin_wilaya_id = :new
                        WHERE origin_wilaya_id = :tmp
                    """),
                    {"new": new, "tmp": old + 100},
                )
                await session.execute(
                    text("""
                        UPDATE wilaya_distances SET dest_wilaya_id = :new
                        WHERE dest_wilaya_id = :tmp
                    """),
                    {"new": new, "tmp": old + 100},
                )
            # normalize (origin < dest) — pairs among 50-58 flip under the permutation
            await session.execute(
                text("""
                UPDATE wilaya_distances SET
                    origin_wilaya_id = LEAST(origin_wilaya_id, dest_wilaya_id),
                    dest_wilaya_id = GREATEST(origin_wilaya_id, dest_wilaya_id)
                WHERE origin_wilaya_id > dest_wilaya_id
            """)
            )
            # drop garbage rows involving 59-69 (fake-hub distances) — recomputed elsewhere
            deleted = await session.execute(
                text("""
                DELETE FROM wilaya_distances
                WHERE origin_wilaya_id >= 59 OR dest_wilaya_id >= 59
            """)
            )
            print(f"  deleted {deleted.rowcount} garbage 59-69 distance rows")

            # ---- 7. Re-add FKs ----
            for tbl, con, action in FK_CONSTRAINTS:
                if "origin" in con:
                    col = "origin_wilaya_id"
                elif "dest" in con:
                    col = "dest_wilaya_id"
                elif "headquarters" in con:
                    col = "headquarters_wilaya_id"
                else:
                    col = "wilaya_id"
                await session.execute(
                    text(f"""
                    ALTER TABLE {tbl} ADD CONSTRAINT {con}
                    FOREIGN KEY ({col})
                    REFERENCES wilayas(id) ON DELETE {action}
                """)
                )
                print(f"  restored FK {con}")

    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
