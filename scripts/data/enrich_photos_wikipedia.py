#!/usr/bin/env python3
"""Fetch Wikipedia main images for POIs with Wikipedia refs but no photos.

Uses the Wikipedia API to get the main image for each article,
reuses the MinIO download/upload machinery from migrate_photos_minio.
"""

import httpx
from sqlalchemy import text

from app.db.session import async_session

WIKI_API = "https://en.wikipedia.org/w/api.php"


def get_wiki_image(client: httpx.Client, title: str) -> str | None:
    """Get the main image URL for a Wikipedia article."""
    try:
        resp = client.get(
            WIKI_API,
            params={
                "action": "query",
                "titles": title,
                "prop": "pageimages",
                "pithumbsize": 800,
                "format": "json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {}).get("source")
            if thumb:
                return thumb
    except Exception:
        pass
    return None


async def main():
    import asyncio

    from scripts.data.migrate_photos_minio import (
        download_and_upload,
        get_minio_client,
    )

    minio_client = get_minio_client()

    async with async_session() as db:
        rows = await db.execute(text("""
            SELECT id, name, osm_tags->>'wikipedia' as wiki_ref
            FROM pois
            WHERE osm_tags->>'wikipedia' IS NOT NULL
              AND photo_url IS NULL
            ORDER BY is_featured DESC, name
            LIMIT 30
        """))

        targets = [(r.id, r.name, r.wiki_ref) for r in rows if r.wiki_ref]

    enriched = 0
    with httpx.Client(
        headers={"User-Agent": "ATHAR/1.0 (travel-guide; athar-os@example.com)"},
    ) as client:
        for poi_id, name, wiki_ref in targets:
            parts = wiki_ref.split(":", 1)
            if len(parts) != 2:
                continue
            lang, title = parts
            if lang != "en":
                continue

            print(f"Fetching image for: {name} ({title})")
            img_url = get_wiki_image(client, title)
            if not img_url:
                print("  No image found")
                continue

            try:
                minio_url, _ext = download_and_upload(minio_client, client, img_url)
            except Exception as e:
                print(f"  Upload error: {e}")
                continue

            if not minio_url:
                print("  Upload failed")
                continue

            async with async_session() as db:
                await db.execute(
                    text("""
                        UPDATE pois
                        SET photo_url = :url,
                            photo_urls = COALESCE(photo_urls, '[]'::jsonb)
                                         || :url::jsonb,
                            photo_source = 'wikipedia'
                        WHERE id = :id
                    """),
                    {"url": minio_url, "id": poi_id},
                )
                await db.commit()
            enriched += 1
            print(f"  OK: {minio_url}")

    print(f"\nTotal enriched: {enriched}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
