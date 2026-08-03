"""
Bulk index all POIs and experiences into Qdrant vector search.
Uses batch encoding + batch upserts for ~50x speedup vs. per-item indexing.
"""

import asyncio
import logging
import sys
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import Batch, PointStruct
from sentence_transformers import SentenceTransformer
from sqlalchemy import select

from app.db.session import async_session
from app.models.experience import Experience
from app.models.poi import POI
from app.services.vector_search import has_real_name

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

POIS_COLLECTION = "pois"
EXPERIENCES_COLLECTION = "experiences"
BATCH_SIZE = 256
EMBEDDING_DIM = 384


def make_embedder():
    logger.info("Loading embedding model all-MiniLM-L6-v2 ...")
    try:
        m = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
    except Exception:
        logger.warning("Model not cached — attempting download")
        m = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Embedding model loaded")
    return m


def encode_batch(embedder, texts: list[str]) -> list[list[float]]:
    vecs = embedder.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [v.tolist() for v in vecs]


async def fetch_all_pois(db):
    r = await db.execute(select(POI).order_by(POI.id))
    return r.scalars().all()


async def fetch_all_experiences(db):
    r = await db.execute(select(Experience).order_by(Experience.id))
    return r.scalars().all()


def index_collection(
    qc: QdrantClient,
    collection: str,
    embedder: SentenceTransformer,
    items: list,
    text_fields: list[str],
    payload_map: dict[str, str],  # payload_key -> model_attr
):
    total = len(items)
    logger.info(f"Indexing {total} items into '{collection}' ...")
    offset = 0
    while offset < total:
        batch = items[offset : offset + BATCH_SIZE]
        texts = []
        for item in batch:
            parts = [str(getattr(item, f, "")) for f in text_fields]
            texts.append(" ".join(parts))
        vectors = encode_batch(embedder, texts)

        points = []
        for item, vec in zip(batch, vectors):
            payload = {k: str(getattr(item, a, "")) for k, a in payload_map.items()}
            if collection == POIS_COLLECTION:
                payload["has_name"] = has_real_name(payload.get("name"))
            points.append(
                PointStruct(
                    id=item.id.hex if hasattr(item.id, "hex") else str(item.id),
                    vector=vec,
                    payload=payload,
                )
            )

        qc.upsert(collection_name=collection, points=points, wait=True)
        offset += BATCH_SIZE
        if offset % 5120 == 0 or offset >= total:
            logger.info(f"  {min(offset, total)}/{total} ({100 * min(offset, total) // total}%)")

    info = qc.get_collection(collection)
    logger.info(f"  '{collection}' now has {info.points_count} points")


async def main():
    embedder = make_embedder()
    qc = QdrantClient(host="localhost", port=6333, timeout=180)

    # Ensure collections exist
    from qdrant_client.http.models import Distance, VectorParams

    for col in [POIS_COLLECTION, EXPERIENCES_COLLECTION]:
        existing = [c.name for c in qc.get_collections().collections]
        if col in existing:
            qc.delete_collection(col)
            logger.info(f"Deleted existing collection '{col}'")
        qc.create_collection(
            collection_name=col,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info(f"Created collection '{col}'")

    async with async_session() as db:
        pois = await fetch_all_pois(db)
        exps = await fetch_all_experiences(db)

    index_collection(
        qc,
        POIS_COLLECTION,
        embedder,
        pois,
        text_fields=["name", "description", "category", "subtype"],
        payload_map={
            "poi_id": "id",
            "name": "name",
            "category": "category",
            "wilaya_id": "wilaya_id",
            "subtype": "subtype",
            "is_featured": "is_featured",
        },
    )

    index_collection(
        qc,
        EXPERIENCES_COLLECTION,
        embedder,
        exps,
        text_fields=["title", "description", "category", "location"],
        payload_map={
            "experience_id": "id",
            "title": "title",
            "category": "category",
            "wilaya_id": "wilaya_id",
            "provider_id": "provider_id",
            "status": "status",
            "season": "season",
        },
    )

    logger.info(f"\nDone: {len(pois)} POIs + {len(exps)} experiences indexed")


if __name__ == "__main__":
    asyncio.run(main())
