"""
Seed transport data (stations, lines, stops) into the database.

Run via: python -m app.services.seed_transport
"""
import asyncio
import sys

from sqlalchemy import select

from app.data.transport_stations import LINES_SEED, STATIONS_SEED, find_station
from app.db.session import async_session
from app.models.station import LineStop, Station, TransportLine


async def seed() -> None:
    async with async_session() as db:
        existing = (await db.execute(select(Station).limit(1))).scalar_one_or_none()
        if existing:
            print("Stations already seeded. Delete them first to re-seed.")
            return

        station_id_map: dict[str, str] = {}

        for entry in STATIONS_SEED:
            st = Station(
                name=entry["name"],
                name_ar=entry.get("name_ar"),
                wilaya_id=entry["wilaya_id"],
                latitude=entry["lat"],
                longitude=entry["lng"],
                station_type=entry["type"],
                operator=entry["operator"],
                is_active=True,
            )
            db.add(st)
            await db.flush()
            station_id_map[entry["name"]] = str(st.id)
            print(f"  + {entry['type']:>8} {entry['name']}")

        for line_entry in LINES_SEED:
            line = TransportLine(
                name=line_entry["name"],
                operator=line_entry["operator"],
                mode=line_entry["mode"],
                color=line_entry.get("color"),
                description=line_entry.get("description"),
                is_active=True,
            )
            db.add(line)
            await db.flush()

            for order, stop_name in enumerate(line_entry["stops"]):
                sid = station_id_map.get(stop_name)
                if not sid:
                    found = find_station(stop_name)
                    if found:
                        sid = station_id_map.get(found["name"])
                if not sid:
                    print(f"  ⚠ Station '{stop_name}' not found for line '{line_entry['name']}'")
                    continue
                stop = LineStop(
                    line_id=line.id,
                    station_id=sid,
                    stop_order=order,
                )
                db.add(stop)

            print(f"  + {line_entry['mode']:>8} {line_entry['name']} ({len(line_entry['stops'])} stops)")

        await db.commit()
        print(f"\n✅ Seeded {len(STATIONS_SEED)} stations and {len(LINES_SEED)} lines")


async def clear() -> None:
    async with async_session() as db:
        await db.execute(LineStop.__table__.delete())
        await db.execute(TransportLine.__table__.delete())
        await db.execute(Station.__table__.delete())
        await db.commit()
        print("🗑  Cleared all transport data")


if __name__ == "__main__":
    if "--clear" in sys.argv:
        asyncio.run(clear())
    else:
        asyncio.run(seed())
