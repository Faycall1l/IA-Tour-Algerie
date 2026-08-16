#!/usr/bin/env python3
"""Fetch photos for POIs with Wikidata refs but no photos via SPARQL P18.

Queries Wikidata SPARQL for images on QIDs that weren't covered by the
earlier P18 pass, downloads and uploads to MinIO.
"""

import asyncio
import hashlib
import re

import httpx
from sqlalchemy import text

from app.db.session import async_session

SPARQL_URL = "https://query.wikidata.org/sparql"
BATCH_SIZE = 50


async def sparql_images(client: httpx.AsyncClient, qids: list[str]) -> dict[str, str]:
    """Batch SPARQL query for P18 images. Returns {qid: image_url}."""
    values = " ".join(f"wd:{q}" for q in qids)
    query = f"""
    SELECT ?item ?itemLabel ?image WHERE {{
      VALUES ?item {{ {values} }}
      ?item wdt:P18 ?image .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,ar". }}
    }}
    LIMIT {len(qids) * 2}
    """
    try:
        resp = await client.get(
            SPARQL_URL,
            params={"query": query, "format": "json"},
            headers={"Accept": "application/sparql-results+json"},
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", {}).get("bindings", [])
        out = {}
        for r in results:
            qid = r["item"]["value"].split("/")[-1]
            img = r["image"]["value"]
            if qid not in out:
                out[qid] = img
        return out
    except Exception as e:
        print(f"  SPARQL error: {e}")
        return {}


async def main():
    from scripts.data.migrate_photos_minio import (
        download_and_upload,
        get_minio_client,
    )

    minio_client = get_minio_client()

    async with async_session() as db:
        rows = await db.execute(text("""
            SELECT id, name, osm_tags->>'wikidata' as qid
            FROM pois
            WHERE osm_tags ? 'wikidata'
              AND photo_url IS NULL
            ORDER BY is_featured DESC, name
        """))
        targets = [(r.id, r.name, r.qid) for r in rows if r.qid]

    print(f"Target POIs: {len(targets)}")

    enriched = 0
    async with httpx.AsyncClient(
        headers={"User-Agent": "ATHAR/1.0 (travel-guide)"},
    ) as client:
        for i in range(0, len(targets), BATCH_SIZE):
            batch = targets[i : i + BATCH_SIZE]
            qids = [t[2] for t in batch]
            qid_to_poi = {t[2]: (t[0], t[1]) for t in batch}

            print(f"\nBatch {i // BATCH_SIZE + 1}: {len(qids)} QIDs")
            images = await sparql_images(client, qids)
            print(f"  Found {len(images)} images")

            for qid, img_url in images.items():
                poi_id, poi_name = qid_to_poi[qid]
                print(f"  {poi_name} ({qid}): {img_url[:80]}...")

                try:
                    minio_url, _ext = download_and_upload(
                        minio_client, httpx.Client(), img_url
                    )
                except Exception as e:
                    print(f"    Upload error: {e}")
                    continue

                if not minio_url:
                    print(f"    Upload failed")
                    continue

                async with async_session() as db2:
                    await db2.execute(
                        text("""
                            UPDATE pois
                            SET photo_url = :url,
                                photo_urls = COALESCE(photo_urls, '[]'::jsonb)
                                             || :url::jsonb,
                                photo_source = 'wikidata'
                            WHERE id = :id
                        """),
                        {"url": minio_url, "id": poi_id},
                    )
                    await db2.commit()
                enriched += 1
                print(f"    OK")

            await asyncio.sleep(2)

    print(f"\nTotal enriched: {enriched}")


if __name__ == "__main__":
    asyncio.run(main())
