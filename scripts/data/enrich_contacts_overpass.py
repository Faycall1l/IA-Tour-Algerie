"""Fetch phone/website/opening_hours from OSM Overpass API for all POIs.

Queries Overpass by OSM node ID to get full tags, then extracts contact info.
Most OSM POI nodes don't have contact tags, but we try anyway.
"""

import asyncio
import logging
import re

import aiohttp
from sqlalchemy import func, select, update

from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BATCH_SIZE = 150
MAX_POIS = 50000
USER_AGENT = "ATHAR-OS/0.3 (data-collector; faycal@athar.dz) aiohttp/3"

PHONE_KEYS = ("phone", "contact:phone", "mobile", "contact:mobile", "fax")
WEBSITE_KEYS = ("website", "contact:website", "url", "contact:url")

CONTACT_PREFIXES = (
    "contact:phone", "contact:mobile", "contact:website", "contact:email",
    "contact:facebook", "contact:instagram", "contact:twitter",
)


def _get_first(tags: dict, keys: tuple) -> str | None:
    for k in keys:
        val = tags.get(k)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if 8 <= len(digits) <= 15:
        return raw.strip()
    return None


def extract_contact_info(tags: dict) -> dict:
    updates = {}
    raw_phone = _get_first(tags, PHONE_KEYS) or _get_first(tags, CONTACT_PREFIXES[:1])
    if raw_phone:
        cleaned = _clean_phone(raw_phone)
        if cleaned:
            updates["phone"] = cleaned

    raw_web = _get_first(tags, WEBSITE_KEYS) or _get_first(tags, CONTACT_PREFIXES[2:3])
    if raw_web:
        updates["website"] = raw_web

    raw_hours = tags.get("opening_hours", "")
    if raw_hours and isinstance(raw_hours, str) and len(raw_hours) > 3:
        updates["opening_hours"] = raw_hours

    return updates


async def process_batch(
    session: aiohttp.ClientSession, pois: list[POI], sem: asyncio.Semaphore
) -> int:
    async with sem:
        ids = [str(p.osm_node_id) for p in pois if p.osm_node_id]
        if not ids:
            return 0

        query = f"[out:json];node(id:{','.join(ids)});out tags;"
        try:
            async with session.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Overpass returned %d for batch", resp.status)
                    return 0
                data = await resp.json()
        except Exception as exc:
            logger.warning("Overpass request failed: %s", exc)
            return 0

        updates_by_id: dict[int, dict] = {}
        for elem in data.get("elements", []):
            tags = elem.get("tags", {})
            info = extract_contact_info(tags)
            if info:
                updates_by_id[elem["id"]] = info

        if not updates_by_id:
            return 0

        updated = 0
        async with async_session() as db:
            for poi in pois:
                info = updates_by_id.get(poi.osm_node_id)
                if info:
                    await db.execute(update(POI).where(POI.id == poi.id).values(**info))
                    updated += 1
            await db.commit()

        return updated


async def main():
    async with async_session() as db:
        total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0
        # POIs with osm_node_id but missing phone, website, or hours
        result = await db.execute(
            select(POI).where(
                POI.osm_node_id.isnot(None),
                (
                    POI.phone.is_(None)
                    | POI.website.is_(None)
                    | POI.opening_hours.is_(None)
                ),
            )
            .order_by(POI.is_featured.desc())
            .limit(MAX_POIS)
        )
        pois = result.scalars().all()

    logger.info("Found %d POIs to check via Overpass (out of %d total)", len(pois), total)

    sem = asyncio.Semaphore(3)
    headers = {"User-Agent": USER_AGENT}
    connector = aiohttp.TCPConnector(limit=5)
    total_updated = 0

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        for i in range(0, len(pois), BATCH_SIZE):
            batch = pois[i : i + BATCH_SIZE]
            n = await process_batch(session, batch, sem)
            total_updated += n
            if n > 0:
                logger.info(
                    "Batch %d/%d: %d updated (total: %d)",
                    i // BATCH_SIZE + 1,
                    (len(pois) + BATCH_SIZE - 1) // BATCH_SIZE,
                    n,
                    total_updated,
                )

    logger.info("Done! Updated %d/%d POIs with contact data from Overpass", total_updated, len(pois))


if __name__ == "__main__":
    asyncio.run(main())
