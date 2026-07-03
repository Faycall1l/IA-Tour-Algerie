from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from app.core.config import settings
from app.services.embeddings import EMBEDDING_DIM, EmbeddingService

if TYPE_CHECKING:
    from qdrant_client import QdrantClient

    from app.models.poi import POI

logger = logging.getLogger(__name__)

COLLECTION_NAME = "pois"


class VectorSearchService:
    def __init__(self, embedder: EmbeddingService) -> None:
        self.embedder = embedder
        self.client: QdrantClient | None = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            from qdrant_client import QdrantClient

            self.client = QdrantClient(
                host=settings.qdrant.host,
                port=settings.qdrant.port,
                grpc_port=settings.qdrant.grpc_port,
                prefer_grpc=settings.qdrant.prefer_grpc,
            )
            self._ensure_collection()
            logger.info(
                "VectorSearch connected to Qdrant at %s:%s",
                settings.qdrant.host,
                settings.qdrant.port,
            )
        except Exception as exc:
            logger.warning("Qdrant unavailable (vector search disabled): %s", exc)
            self.client = None

    def _ensure_collection(self) -> None:
        if not self.client:
            return
        collections = [c.name for c in self.client.get_collections().collections]
        if COLLECTION_NAME not in collections:
            from qdrant_client.http.models import Distance, VectorParams

            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)

    def index_poi(self, poi: POI) -> None:
        if not self.client:
            return
        text = f"{poi.name} {poi.description or ''} {poi.category}"
        vector = self.embedder.encode(text)
        from qdrant_client.http.models import PointStruct

        self.client.upsert(
            collection_name=COLLECTION_NAME,
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
            collection_name=COLLECTION_NAME,
            query_vector=vector,
            limit=limit,
        )
        ids: list[uuid.UUID] = []
        for hit in hits:
            pid = hit.payload.get("poi_id") if hit.payload else None
            if pid:
                try:
                    ids.append(uuid.UUID(pid))
                except ValueError:
                    continue
        return ids

    def delete_poi(self, poi_id: uuid.UUID) -> None:
        if not self.client:
            return
        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=[poi_id.hex],
        )
