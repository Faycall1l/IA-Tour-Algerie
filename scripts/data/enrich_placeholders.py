"""Generate placeholder photos for POIs without images.

Uses placehold.co service to generate category-colored placeholder images
with text like "Historical site in Algiers" or "Beach in Oran".

This ensures every POI in API responses has at least some visual.
"""

import asyncio
import logging
from urllib.parse import quote

from sqlalchemy import select, func, update

from app.db.session import async_session
from app.models.poi import POI
from app.models.wilaya import Wilaya

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 500

CATEGORY_COLORS = {
    "historical": "8B4513",
    "natural": "228B22",
    "cultural": "4A90D9",
    "religious": "DAA520",
    "museum": "8B008B",
    "beach": "1E90FF",
    "mountain": "2F4F4F",
    "park": "32CD32",
    "market": "FF6347",
    "restaurant": "FF4500",
    "cafe": "8B4513",
    "other": "708090",
}

CATEGORY_LABELS = {
    "historical": "Historical Site",
    "natural": "Natural Site",
    "cultural": "Cultural Site",
    "religious": "Religious Site",
    "museum": "Museum",
    "beach": "Beach",
    "mountain": "Mountain",
    "park": "Park",
    "market": "Market",
    "restaurant": "Restaurant",
    "cafe": "Cafe",
    "other": "Point of Interest",
}


def _make_placeholder_url(category: str, wilaya_name: str | None, name: str | None) -> str:
    color = CATEGORY_COLORS.get(category, "708090")
    label = CATEGORY_LABELS.get(category, "Point of Interest")
    text_parts = [label]
    if wilaya_name:
        text_parts.append(wilaya_name)
    if name:
        short_name = name[:40] if len(name) > 40 else name
        text_parts.append(short_name)
    text = quote(" | ".join(text_parts))
    return f"https://placehold.co/600x400/{color}/FFFFFF?text={text}&font=raleway"


async def main():
    async with async_session() as db:
        # Build wilaya name map
        wilayas = (await db.execute(select(Wilaya.id, Wilaya.name_fr))).all()
        wilaya_map = {w.id: w.name_fr for w in wilayas}

        total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0

        # POIs without any photo
        result = await db.execute(
            select(POI).where(
                (POI.photo_url.is_(None)) | (POI.photo_url == ""),
            )
            .order_by(POI.is_featured.desc())
        )
        pois = result.scalars().all()

    logger.info("Found %d POIs without photos to placehold (out of %d total)", len(pois), total)

    updated = 0
    async with async_session() as db:
        for i in range(0, len(pois), BATCH_SIZE):
            batch = pois[i : i + BATCH_SIZE]
            for poi in batch:
                wil_name = wilaya_map.get(poi.wilaya_id)
                url = _make_placeholder_url(poi.category, wil_name, poi.name)
                await db.execute(update(POI).where(POI.id == poi.id).values(photo_url=url))
                updated += 1

            await db.commit()
            logger.info("Batch %d/%d: %d placeholders set (total: %d)",
                        i // BATCH_SIZE + 1, (len(pois) + BATCH_SIZE - 1) // BATCH_SIZE,
                        len(batch), updated)

    logger.info("Done! %d POIs now have placeholder photos", updated)


if __name__ == "__main__":
    asyncio.run(main())
