#!/usr/bin/env python3
"""Untangle chained wilaya remaps from fix_wilaya_numbering.py.

That script updated child tables with sequential UPDATEs in dict-insertion
order, so each step re-captured rows moved by previous steps:

- 50-58 children (pois/stations/stays/experiences/events/artisans) ended up
  stacked: w50 = {old50, old52, old54, old56, old58}, w51 = {old51, old53,
  old55, old57}, w52-58 empty.
- 59-69 experiences ended up stacked: w60 = {dz59 Aflou stays, dz61 El Aricha,
  dz63 Barika}, w61 = El Kantara, w62 = Bir El Ater, w64 = {Ksar Chellala,
  Ksar El Boukhari}, w65 = {Aïn Ouessara, Bou Saâda}, w66 = {Messaad,
  El Abiodh Sidi Cheikh}.

Because the pre-migration assignment used nearest-center with the SAME center
coordinates, re-assigning geolocated rows to their nearest official 50-69
center is the exact inverse of the chain. Experiences/event have no usable
coordinates -> matched by wilaya name in the title.

Stations at 60-69 (assigned by step 5 + curated corrections) are NOT touched.

Usage: python scripts/data/fix_wilaya_chain.py
"""

from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import async_session  # noqa: E402
from sqlalchemy import text  # noqa: E402

OFFICIAL_50_69: dict[int, tuple[str, float, float]] = {
    50: ("Bordj Badji Mokhtar", 21.3275, 0.915),
    51: ("Ouled Djellal", 34.4267, 5.0642),
    52: ("Béni Abbès", 30.0833, -2.1667),
    53: ("In Salah", 27.1936, 2.4828),
    54: ("In Guezzam", 19.5656, 5.7725),
    55: ("Touggourt", 33.1044, 6.0683),
    56: ("Djanet", 24.5547, 9.4847),
    57: ("El M'Ghair", 33.9486, 5.9217),
    58: ("El Meniaa", 30.5833, 2.8833),
    59: ("Aflou", 34.11279, 2.1019),
    60: ("Barika", 35.3972, 5.3658),
    61: ("El Kantara", 35.192365, 5.6668306),
    62: ("Bir El Ater", 34.748, 8.0594),
    63: ("El Aricha", 34.22259, -1.257),
    64: ("Ksar Chellala", 35.21222, 2.3189),
    65: ("Aïn Ouessara", 35.4542653, 2.904444),
    66: ("Messaad", 34.15429, 3.50309),
    67: ("Ksar El Boukhari", 35.88889, 2.74905),
    68: ("Bou Saâda", 35.2091, 4.1744),
    69: ("El Abiodh Sidi Cheikh", 32.898611, 0.544444),
}

# wilaya name fragments found in experience/event titles -> official id.
# Longer/more specific fragments must come first within the same wilaya.
NAME_MATCHERS: list[tuple[str, int]] = [
    ("Bordj Badji Mokhtar", 50),
    ("Badji Mokhtar", 50),
    ("Ouled Djellal", 51),
    ("Béni Abbès", 52),
    ("Beni Abbes", 52),
    ("In Salah", 53),
    ("Aïn Salah", 53),
    ("In Guezzam", 54),
    ("Aïn Guezzam", 54),
    ("Touggourt", 55),
    ("Djanet", 56),
    ("El M'Ghair", 57),
    ("El Mghair", 57),
    ("El Meniaa", 58),
    ("Meniaa", 58),
    ("Aflou", 59),
    ("Barika", 60),
    ("El Kantara", 61),
    ("Kantara", 61),
    ("Bir El Ater", 62),
    ("Bir el Ater", 62),
    ("El Aricha", 63),
    ("Ksar Chellala", 64),
    ("Chellala", 64),
    ("Aïn Ouessara", 65),
    ("Ain Ouessara", 65),
    ("Aïn Oussera", 65),
    ("Ain Oussera", 65),
    ("Messaad", 66),
    ("Ksar El Boukhari", 67),
    ("Ksar el Boukhari", 67),
    ("Bou Saâda", 68),
    ("Bou Saada", 68),
    ("El Abiodh Sidi Cheikh", 69),
    ("El Abiodh", 69),
    ("Abiodh", 69),
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_official(lat: float, lng: float) -> int:
    return min(
        OFFICIAL_50_69,
        key=lambda wid: haversine_km(lat, lng, OFFICIAL_50_69[wid][1], OFFICIAL_50_69[wid][2]),
    )


async def fix_geolocated() -> int:
    """Reassign pois/stays/artisans in 50-69 + stations in 50-51 by nearest center."""
    async with async_session() as session:
        async with session.begin():
            moved = 0
            for tbl, col, keep_range in (
                ("pois", "wilaya_id", (50, 69)),
                ("stays", "wilaya_id", (50, 69)),
                ("artisans", "wilaya_id", (50, 69)),
                ("stations", "wilaya_id", (50, 51)),
            ):
                lo, hi = keep_range
                rows = (
                    await session.execute(
                        text(
                            f"SELECT id, latitude, longitude FROM {tbl} "
                            f"WHERE wilaya_id BETWEEN :lo AND :hi"
                        ),
                        {"lo": lo, "hi": hi},
                    )
                ).all()
                updates: dict[int, int] = {}
                for r in rows:
                    if r[1] is None or r[2] is None:
                        print(f"  !! {tbl} id={r[0]} has no coords, skipping")
                        continue
                    updates[r[0]] = nearest_official(r[1], r[2])
                for row_id, wid in updates.items():
                    await session.execute(
                        text(f"UPDATE {tbl} SET {col} = :wid WHERE id = :rid"),
                        {"wid": wid, "rid": row_id},
                    )
                moved += len(updates)
                print(f"  {tbl}: reassigned {len(updates)} rows by nearest official center")
            return moved


async def fix_by_title(table: str) -> int:
    """Match experiences/events at the chained wilayas by title fragment."""
    async with async_session() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    text(
                        f"SELECT id, title, wilaya_id FROM {table} "
                        "WHERE wilaya_id BETWEEN 50 AND 69"
                    )
                )
            ).all()
            unmatched: list[tuple[str, object]] = []
            moved = 0
            for r in rows:
                title = str(r[1] or "")
                best = next(
                    (wid for frag, wid in NAME_MATCHERS if frag.lower() in title.lower()),
                    None,
                )
                if best is None:
                    unmatched.append((title, r[0]))
                    continue
                if best != r[2]:
                    await session.execute(
                        text(f"UPDATE {table} SET wilaya_id = :wid WHERE id = :rid"),
                        {"wid": best, "rid": r[0]},
                    )
                moved += 1
        print(f"  {table}: rematched {moved} rows by title (total checked {len(rows)})")
        if unmatched:
            print(f"  !! {table}: {len(unmatched)} unmatched titles:")
            for t, i in unmatched[:40]:
                print(f"     id={i} {t[:70]}")
        return moved


async def main() -> None:
    print("== geolocated tables ==")
    await fix_geolocated()
    print("== title-matched tables ==")
    await fix_by_title("experiences")
    await fix_by_title("events")
    print("DONE")


if __name__ == "__main__":
    asyncio.run(main())
