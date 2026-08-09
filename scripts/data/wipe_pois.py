"""Wipe the entire POI corpus (pois + poi_experiences + Qdrant pois collection).

Part of the POI rebuild: the old 52,685-POI corpus was junk (78.8% placeholder
names, fake shared photos). This script empties the pois table (CASCADE clears
poi_experiences) and drops the Qdrant pois collection so it can be reseeded
from real TripAdvisor data.

Run: python scripts/data/wipe_pois.py
"""

import asyncio
import os
from pathlib import Path
import sys

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import async_session


async def wipe_db() -> None:
    async with async_session() as session:
        async with session.begin():
            result = await session.execute(text("DELETE FROM pois"))
        print(f"pois deleted: {result.rowcount}")
    async with async_session() as session:
        result = await session.execute(text("SELECT count(*) FROM pois"))
        print(f"pois remaining: {result.scalar()}")
        result = await session.execute(text("SELECT count(*) FROM poi_experiences"))
        print(f"poi_experiences remaining: {result.scalar()}")


def wipe_qdrant() -> None:
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    resp = httpx.delete(f"{qdrant_url}/collections/pois", timeout=30)
    resp.raise_for_status()
    print(f"Qdrant pois collection dropped: {resp.json()['result']}")


if __name__ == "__main__":
    asyncio.run(wipe_db())
    wipe_qdrant()
