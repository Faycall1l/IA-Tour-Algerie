import asyncio
import io
import logging
import re
from urllib.parse import urlparse

import aiohttp
from minio import Minio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

COMMONS_RE = re.compile(r"https?://upload\.wikimedia\.org/wikipedia/commons/[^\s\"']+")
BATCH_SIZE = 50
MAX_CONCURRENT = 10
USER_AGENT = "ATHAR-OS/0.3 (tourism-data-collector; faycal@athar.dz)"


def _object_name(url: str) -> str:
    """Derive a stable object name from the Commons URL path.
    Reversible for Commons URLs (hash dirs + filename)."""
    path = urlparse(url).path.lstrip("/")
    safe = path.replace("/", "_").replace("%", "_")
    return f"poi_photos/{safe}"


def _minio_url(obj_name: str) -> str:
    public = settings.minio.public_url
    if public:
        return f"{public}/{settings.minio.bucket}/{obj_name}"
    return f"http://{settings.minio.endpoint}/{settings.minio.bucket}/{obj_name}"


async def _download(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.read()
            logger.warning("  HTTP %s for %s", resp.status, url[:100])
    except Exception as exc:
        logger.warning("  Download failed %s: %s", url[:80], exc)
    return None


async def main():
    minio_client = Minio(
        endpoint=settings.minio.endpoint,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=settings.minio.secure,
    )
    if not minio_client.bucket_exists(settings.minio.bucket):
        minio_client.make_bucket(settings.minio.bucket)
        logger.info("Created bucket %s", settings.minio.bucket)

    async with async_session() as db:
        db: AsyncSession
        result = await db.execute(
            select(POI).where(
                POI.photo_url.regexp_match(r"upload\.wikimedia\.org")
                | POI.photo_urls.any("upload.wikimedia.org")
            )
        )
        pois = result.scalars().all()

    logger.info("Found %d POIs with Commons photo URLs", len(pois))

    headers = {"User-Agent": USER_AGENT}
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    updates: dict[object, dict[str, object]] = {}

    async with aiohttp.ClientSession(headers=headers, connector=connector) as session:
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        async def process_one(poi: POI) -> None:
            new_photo_url = poi.photo_url  # default: keep original
            new_photo_urls = poi.photo_urls  # default: keep original

            # photo_url
            if poi.photo_url and COMMONS_RE.match(poi.photo_url):
                obj = _object_name(poi.photo_url)
                try:
                    minio_client.stat_object(settings.minio.bucket, obj)
                    new_photo_url = _minio_url(obj)
                except Exception:
                    async with sem:
                        data = await _download(session, poi.photo_url)
                    if data:
                        try:
                            minio_client.put_object(
                                bucket_name=settings.minio.bucket,
                                object_name=obj,
                                data=io.BytesIO(data),
                                length=len(data),
                                content_type="image/jpeg",
                            )
                            new_photo_url = _minio_url(obj)
                            logger.info("  Uploaded %s", obj)
                        except Exception as exc:
                            logger.warning("  MinIO upload failed for %s: %s", obj, exc)

            # photo_urls array
            if poi.photo_urls:
                migrated = list(poi.photo_urls)
                changed = False
                for idx, u in enumerate(migrated):
                    if u and COMMONS_RE.match(u):
                        obj = _object_name(u)
                        try:
                            minio_client.stat_object(settings.minio.bucket, obj)
                            migrated[idx] = _minio_url(obj)
                            changed = True
                        except Exception:
                            async with sem:
                                data = await _download(session, u)
                            if data:
                                try:
                                    minio_client.put_object(
                                        bucket_name=settings.minio.bucket,
                                        object_name=obj,
                                        data=io.BytesIO(data),
                                        length=len(data),
                                        content_type="image/jpeg",
                                    )
                                    migrated[idx] = _minio_url(obj)
                                    changed = True
                                    logger.info("  Uploaded alt %s", obj)
                                except Exception as exc:
                                    logger.warning("  MinIO upload failed for alt %s: %s", obj, exc)
                if changed:
                    new_photo_urls = migrated

            db_updates = {}
            if new_photo_url != poi.photo_url:
                db_updates["photo_url"] = new_photo_url
            if new_photo_urls != poi.photo_urls:
                db_updates["photo_urls"] = new_photo_urls
            if db_updates:
                updates[poi.id] = db_updates

        for i in range(0, len(pois), BATCH_SIZE):
            batch = pois[i : i + BATCH_SIZE]
            await asyncio.gather(*[process_one(p) for p in batch])
            if (i + BATCH_SIZE) % 200 == 0:
                logger.info("Progress: %d/%d", min(i + BATCH_SIZE, len(pois)), len(pois))

    logger.info("Upload phase done. Updating %d POI records in DB...", len(updates))
    async with async_session() as db:
        db: AsyncSession
        for pid, vals in updates.items():
            await db.execute(update(POI).where(POI.id == pid).values(**vals))
        await db.commit()

    logger.info("Migration complete. %d POI records updated with MinIO URLs.", len(updates))


if __name__ == "__main__":
    asyncio.run(main())
