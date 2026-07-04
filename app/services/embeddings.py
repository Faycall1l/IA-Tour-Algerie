from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class EmbeddingService:
    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading embedding model %s ...", MODEL_NAME)
            self._model = SentenceTransformer(MODEL_NAME, backend="onnx")
            logger.info("Embedding model loaded (ONNX backend)")
        except Exception:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info("ONNX backend unavailable, falling back to default...")
                self._model = SentenceTransformer(MODEL_NAME)
                logger.info("Embedding model loaded (default backend)")
            except Exception as exc:
                logger.warning("Embedding model unavailable: %s", exc)
                self._model = None

    def encode(self, text: str) -> list[float]:
        self._load()
        if not self._model:
            raise RuntimeError("Embedding model not available")
        return self._model.encode(text, normalize_embeddings=True).tolist()
