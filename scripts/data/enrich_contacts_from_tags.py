"""Extract phone, website, email, opening_hours from osm_tags into dedicated columns.

OSM tags like:
  - phone, contact:phone
  - website, contact:website
  - email, contact:email
  - opening_hours
  - facebook, instagram, twitter

are stored in osm_tags JSONB but not extracted to the model columns.
This script migrates them.
"""

import asyncio
import logging
import re

from sqlalchemy import func, select, update

from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500

PHONE_KEYS = ("phone", "contact:phone", "mobile", "contact:mobile", "fax")
WEBSITE_KEYS = ("website", "contact:website", "url", "contact:url")
EMAIL_KEYS = ("email", "contact:email")
SOCIAL_KEYS = {
    "facebook": "contact:facebook",
    "instagram": "contact:instagram",
    "twitter": "contact:twitter",
}
HOURS_KEY = "opening_hours"


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 8 and len(digits) <= 15:
        return raw.strip()
    return None


def _extract_first(tags: dict, keys: tuple) -> str | None:
    for k in keys:
        val = tags.get(k)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return None


async def process_batch(pois: list[POI]) -> int:
    updates = 0
    for poi in pois:
        if not poi.osm_tags:
            continue
        tags = poi.osm_tags
        updates_dict = {}

        # Phone
        if not poi.phone:
            raw = _extract_first(tags, PHONE_KEYS)
            if raw:
                cleaned = _clean_phone(raw)
                if cleaned:
                    updates_dict["phone"] = cleaned

        # Website
        if not poi.website:
            raw = _extract_first(tags, WEBSITE_KEYS)
            if raw:
                updates_dict["website"] = raw

        # Opening hours
        if not poi.opening_hours:
            raw = tags.get(HOURS_KEY)
            if raw and isinstance(raw, str) and raw.strip():
                updates_dict["opening_hours"] = raw.strip()

        if updates_dict:
            async with async_session() as db:
                await db.execute(update(POI).where(POI.id == poi.id).values(**updates_dict))
                await db.commit()
            updates += 1

    return updates


async def main():
    async with async_session() as db:
        total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0

        # POIs with osm_tags but missing contact data
        result = await db.execute(
            select(POI).where(
                POI.osm_tags.isnot(None),
                POI.osm_tags != {},
                (POI.phone.is_(None)) | (POI.website.is_(None)) | (POI.opening_hours.is_(None)),
            ).order_by(POI.is_featured.desc()).limit(10000)
        )
        pois = result.scalars().all()

    logger.info("Found %d POIs with osm_tags missing contact info (out of %d total)", len(pois), total)

    updated = 0
    for i in range(0, len(pois), BATCH_SIZE):
        batch = pois[i : i + BATCH_SIZE]
        n = await process_batch(batch)
        updated += n
        logger.info("Batch %d/%d: %d updated (total: %d)", i // BATCH_SIZE + 1, (len(pois) + BATCH_SIZE - 1) // BATCH_SIZE, n, updated)

    logger.info("Done! Updated %d POIs with contact data from osm_tags", updated)


if __name__ == "__main__":
    asyncio.run(main())
