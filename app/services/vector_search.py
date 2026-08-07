from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.embeddings import EMBEDDING_DIM, EmbeddingService

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

    from app.models.experience import Experience
    from app.models.poi import POI

logger = logging.getLogger(__name__)

POIS_COLLECTION = "pois"
EXPERIENCES_COLLECTION = "experiences"


def has_real_name(name: str | None) -> bool:
    """True when the name is a real label, not the '(non nommé)' placeholder."""
    if not name:
        return False
    stripped = name.strip()
    return bool(stripped) and not stripped.endswith("(non nommé)")


class VectorSearchService:
    def __init__(self, embedder: EmbeddingService) -> None:
        self.embedder = embedder
        self.client: QdrantClient | None = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from qdrant_client import QdrantClient

            kwargs = {
                "host": settings.qdrant.host,
                "port": settings.qdrant.port,
                "grpc_port": settings.qdrant.grpc_port,
                "prefer_grpc": settings.qdrant.prefer_grpc,
            }
            if settings.qdrant.api_key:
                kwargs["api_key"] = settings.qdrant.api_key
            self.client = QdrantClient(**kwargs)
            self._ensure_collection(POIS_COLLECTION)
            self._ensure_collection(EXPERIENCES_COLLECTION)
            logger.info(
                "VectorSearch connected to Qdrant at %s:%s",
                settings.qdrant.host,
                settings.qdrant.port,
            )
        except Exception as exc:
            logger.warning("Qdrant unavailable (vector search disabled): %s", exc)
            self.client = None

    def _ensure_collection(self, name: str) -> None:
        if not self.client:
            return
        collections = [c.name for c in self.client.get_collections().collections]
        if name not in collections:
            from qdrant_client.http.models import Distance, VectorParams

            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s'", name)

    # ── POIs ──────────────────────────────────────────────────────────

    def count(self, collection: str) -> int:
        if not self.client:
            return 0
        try:
            return self.client.count(collection_name=collection, exact=True).count
        except Exception as exc:
            logger.warning("Qdrant count failed for '%s': %s", collection, exc)
            return 0

    def index_poi(self, poi: POI) -> None:
        if not self.client:
            return
        text = f"{poi.name} {poi.description or ''} {poi.category}"
        vector = self.embedder.encode(text)
        from qdrant_client.http.models import PointStruct

        self.client.upsert(
            collection_name=POIS_COLLECTION,
            points=[
                PointStruct(
                    id=poi.id.hex,
                    vector=vector,
                    payload={
                        "poi_id": str(poi.id),
                        "name": poi.name,
                        "category": poi.category,
                        "wilaya_id": poi.wilaya_id,
                        "has_name": has_real_name(poi.name),
                    },
                )
            ],
        )

    def index_pois_bulk(self, pois: list[POI], batch_size: int = 256) -> int:
        if not self.client or not pois:
            return 0
        from qdrant_client.http.models import PointStruct

        texts = [f"{p.name} {p.description or ''} {p.category}" for p in pois]
        vectors = self.embedder.encode_batch(texts)
        points = [
            PointStruct(
                id=p.id.hex,
                vector=vec,
                payload={
                    "poi_id": str(p.id),
                    "name": p.name,
                    "category": p.category,
                    "wilaya_id": p.wilaya_id,
                    "has_name": has_real_name(p.name),
                },
            )
            for p, vec in zip(pois, vectors, strict=True)
        ]
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=POIS_COLLECTION,
                points=points[i : i + batch_size],
                wait=True,
            )
        return len(points)

    def search(self, query: str, limit: int = 10) -> list[uuid.UUID]:
        if not self.client:
            return []
        vector = self.embedder.encode(query)
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        # Prefer real-named POIs so placeholder "Ruins (non nommé)" entries
        # don't crowd out actual named landmarks.
        named = self.client.query_points(
            collection_name=POIS_COLLECTION,
            query=vector,
            limit=limit,
            query_filter=Filter(
                must=[FieldCondition(key="has_name", match=MatchValue(value=True))]
            ),
        )
        ids = self._extract_ids(named.points, "poi_id")
        if len(ids) < limit:
            # Fill remaining slots from the full index so unnamed POIs stay
            # discoverable (just ranked below named ones).
            seen = set(ids)
            resp = self.client.query_points(
                collection_name=POIS_COLLECTION,
                query=vector,
                limit=max(limit * 3, 30),
            )
            for pid in self._extract_ids(resp.points, "poi_id"):
                if pid not in seen:
                    seen.add(pid)
                    ids.append(pid)
        return ids[:limit]

    def delete_poi(self, poi_id: uuid.UUID) -> None:
        if not self.client:
            return
        self.client.delete(
            collection_name=POIS_COLLECTION,
            points_selector=[poi_id.hex],
        )

    # ── Experiences ───────────────────────────────────────────────────

    def index_experience(self, experience: Experience) -> None:
        if not self.client:
            return
        text = f"{experience.title} {experience.description or ''} {experience.category}"
        vector = self.embedder.encode(text)
        from qdrant_client.http.models import PointStruct

        self.client.upsert(
            collection_name=EXPERIENCES_COLLECTION,
            points=[
                PointStruct(
                    id=experience.id.hex,
                    vector=vector,
                    payload={
                        "experience_id": str(experience.id),
                        "title": experience.title,
                        "category": experience.category,
                        "wilaya_id": experience.wilaya_id,
                        "provider_id": str(experience.provider_id),
                        "status": experience.status,
                    },
                )
            ],
        )

    def index_experiences_bulk(self, experiences: list[Experience], batch_size: int = 256) -> int:
        if not self.client or not experiences:
            return 0
        from qdrant_client.http.models import PointStruct

        texts = [f"{e.title} {e.description or ''} {e.category}" for e in experiences]
        vectors = self.embedder.encode_batch(texts)
        points = [
            PointStruct(
                id=e.id.hex,
                vector=vec,
                payload={
                    "experience_id": str(e.id),
                    "title": e.title,
                    "category": e.category,
                    "wilaya_id": e.wilaya_id,
                    "provider_id": str(e.provider_id),
                    "status": e.status,
                },
            )
            for e, vec in zip(experiences, vectors, strict=True)
        ]
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=EXPERIENCES_COLLECTION,
                points=points[i : i + batch_size],
                wait=True,
            )
        return len(points)

    def search_experiences(self, query: str, limit: int = 10) -> list[uuid.UUID]:
        if not self.client:
            return []
        vector = self.embedder.encode(query)
        resp = self.client.query_points(
            collection_name=EXPERIENCES_COLLECTION,
            query=vector,
            limit=limit,
        )
        return self._extract_ids(resp.points, "experience_id")

    def delete_experience(self, experience_id: uuid.UUID) -> None:
        if not self.client:
            return
        self.client.delete(
            collection_name=EXPERIENCES_COLLECTION,
            points_selector=[experience_id.hex],
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _extract_ids(self, hits: list, id_field: str) -> list[uuid.UUID]:
        ids: list[uuid.UUID] = []
        for hit in hits:
            pid = hit.payload.get(id_field) if hit.payload else None
            if pid:
                try:
                    ids.append(uuid.UUID(pid))
                except ValueError:
                    continue
        return ids
