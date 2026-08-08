#!/usr/bin/env python3
"""Rebuild Qdrant collections with the multilingual embedder + typed payloads.

Drops and recreates the pois/experiences collections (derived-only data,
safe to wipe) so vectors match the new multilingual model and payload
booleans/ints keep their real types.

Parallelized: POI shards are encoded by N worker processes (each with its
own embedder + Qdrant client), then written back with typed payloads.

Usage: python scripts/reindex_qdrant.py [--workers 4]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import async_session  # noqa: E402
from app.models.experience import Experience  # noqa: E402
from app.models.poi import POI  # noqa: E402
from app.services.embeddings import EMBEDDING_DIM, EmbeddingService  # noqa: E402
from app.services.vector_search import (  # noqa: E402
    EXPERIENCES_COLLECTION,
    POIS_COLLECTION,
    VectorSearchService,
    _poi_index_text,
    _poi_payload,
)
from sqlalchemy import select  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reindex")


def _encode_upsert_shard(args: tuple) -> tuple[int, float]:
    """Worker: encode one shard of POI rows and upsert into Qdrant."""
    shard_id, rows = args
    embedder = EmbeddingService()
    embedder.warm()
    vs = VectorSearchService(embedder)
    if not vs.client:
        return shard_id, 0.0
    from qdrant_client.http.models import PointStruct

    pois = [POI(**row) for row in rows]
    points: list[PointStruct] = []
    t_enc = 0.0
    CHUNK = 512
    for start in range(0, len(pois), CHUNK):
        chunk = pois[start : start + CHUNK]
        texts = [_poi_index_text(p) for p in chunk]
        t0 = time.time()
        vectors = embedder.encode_batch(texts)
        t_enc += time.time() - t0
        for p, vec in zip(chunk, vectors, strict=True):
            points.append(
                PointStruct(id=p.id.hex, vector=vec, payload=_poi_payload(p))
            )
        logger.info(
            "shard %d: encoded %d/%d (%.1f texts/s)",
            shard_id,
            start + len(chunk),
            len(pois),
            (start + len(chunk)) / t_enc,
        )
    t0 = time.time()
    UPSERT_BATCH = 5000
    for start in range(0, len(points), UPSERT_BATCH):
        batch = points[start : start + UPSERT_BATCH]
        try:
            vs.client.upsert(collection_name=POIS_COLLECTION, points=batch, wait=True)
            logger.info(
                "shard %d: upserted %d/%d points (%.0fs)",
                shard_id,
                start + len(batch),
                len(points),
                time.time() - t0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "shard %d: upsert batch %d failed (%s) — retrying 3x",
                shard_id,
                start // UPSERT_BATCH,
                exc,
            )
            for attempt in range(3):
                time.sleep(5 * (attempt + 1))
                try:
                    vs.client.upsert(
                        collection_name=POIS_COLLECTION, points=batch, wait=True
                    )
                    logger.info(
                        "shard %d: upserted %d/%d points (retry %d, %.0fs)",
                        shard_id,
                        start + len(batch),
                        len(points),
                        attempt + 1,
                        time.time() - t0,
                    )
                    break
                except Exception as retry_exc:  # noqa: BLE001
                    logger.warning(
                        "shard %d: retry %d also failed (%s)", shard_id, attempt + 1, retry_exc
                    )
            else:
                logger.error("shard %d: giving up on batch %d", shard_id, start // UPSERT_BATCH)
    return shard_id, time.time() - t0


def _poi_row(p: POI) -> dict:
    """Pickle-safe POI row for multiprocessing workers."""
    return {
        "id": p.id,
        "name": p.name,
        "name_en": p.name_en,
        "name_ar": p.name_ar,
        "description": p.description,
        "category": p.category,
        "subtype": p.subtype,
        "wilaya_id": p.wilaya_id,
        "commune": p.commune,
        "operator": p.operator,
        "cuisine": p.cuisine,
        "neighborhood": p.neighborhood,
        "is_featured": p.is_featured,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=mp.cpu_count() // 2)
    args = parser.parse_args()

    vs = VectorSearchService(EmbeddingService())
    if not vs.client:
        logger.error("Qdrant unavailable — abort")
        return

    logger.info("Loading POIs + experiences from DB...")
    async with async_session() as session:
        pois = list((await session.execute(select(POI))).scalars().all())
        exps = list((await session.execute(select(Experience))).scalars().all())
    logger.info("DB: %d POIs, %d experiences", len(pois), len(exps))

    vs.client.delete_collection(POIS_COLLECTION)
    vs.client.delete_collection(EXPERIENCES_COLLECTION)
    vs._ensure_collection(POIS_COLLECTION)
    vs._ensure_collection(EXPERIENCES_COLLECTION)
    logger.info("Collections dropped + recreated (dim=%d)", EMBEDDING_DIM)

    n_workers = min(args.workers, 6)
    if n_workers == 1:
        logger.info("Encoding %d POIs in-process (single worker)...", len(pois))
        t0 = time.time()
        vs = VectorSearchService(EmbeddingService())
        shard_id, _ = _encode_upsert_shard((0, [_poi_row(p) for p in pois]))
        ok = 1 if shard_id == 0 else 0
        elapsed = time.time() - t0
        logger.info(
            "POIs indexed: %d/%d shards in %.0fs (%.1f texts/s)",
            ok,
            1,
            elapsed,
            len(pois) / elapsed,
        )
    else:
        rows = [_poi_row(p) for p in pois]
        shard_size = max(1, len(rows) // n_workers)
        shards = [
            (i, rows[i * shard_size : (i + 1) * shard_size])
            for i in range(n_workers)
        ]
        if shards and len(shards[-1][1]) == 0:
            shards = shards[:-1]

        t0 = time.time()
        logger.info("Encoding %d POIs with %d workers...", len(rows), len(shards))
        with mp.Pool(len(shards)) as pool:
            results = pool.map(_encode_upsert_shard, shards)
        elapsed = time.time() - t0
        ok = sum(1 for _, dt in results if dt > 0)
        logger.info(
            "POIs indexed: %d/%d shards in %.0fs (%.1f texts/s)",
            ok,
            len(shards),
            elapsed,
            len(rows) / elapsed,
        )

    t0 = time.time()
    n = await asyncio.get_running_loop().run_in_executor(None, vs.index_experiences_bulk, exps)
    logger.info("Experiences indexed: %d in %.0fs", n, time.time() - t0)

    logger.info("DONE — collections rebuilt")
    pois_n = vs.count(POIS_COLLECTION)
    exps_n = vs.count(EXPERIENCES_COLLECTION)
    logger.info("counts: pois=%d experiences=%d", pois_n, exps_n)


if __name__ == "__main__":
    asyncio.run(main())
