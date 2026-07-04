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
                    },
                )
            ],
        )

    def search(self, query: str, limit: int = 10) -> list[uuid.UUID]:
        if not self.client:
            return []
        vector = self.embedder.encode(query)
        hits = self.client.search(
            collection_name=POIS_COLLECTION,
            query_vector=vector,
            limit=limit,
        )
        return self._extract_ids(hits, "poi_id")

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

    def search_experiences(self, query: str, limit: int = 10) -> list[uuid.UUID]:
        if not self.client:
            return []
        vector = self.embedder.encode(query)
        hits = self.client.search(
            collection_name=EXPERIENCES_COLLECTION,
            query_vector=vector,
            limit=limit,
        )
        return self._extract_ids(hits, "experience_id")

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
