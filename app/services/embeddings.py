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

            # local_files_only avoids a HuggingFace round-trip on every boot —
            # load fails fast when the model isn't cached instead of blocking
            # on retries (offline/restricted networks).
            self._model = SentenceTransformer(
                MODEL_NAME,
                backend="onnx",
                local_files_only=True,
                model_kwargs={"file_name": "onnx/model.onnx"},
            )
            logger.info("Embedding model loaded (ONNX, local cache)")
        except Exception:
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
                logger.info("Embedding model loaded (default backend, local cache)")
            except Exception as exc:
                logger.warning(
                    "Embedding model not found in cache (%s) — attempting download", exc
                )
                try:
                    from sentence_transformers import SentenceTransformer

                    self._model = SentenceTransformer(MODEL_NAME, backend="onnx")
                except Exception as exc2:
                    try:
                        from sentence_transformers import SentenceTransformer

                        self._model = SentenceTransformer(MODEL_NAME)
                    except Exception as exc3:
                        logger.warning("Embedding model unavailable: %s / %s", exc2, exc3)
                        self._model = None

    def encode(self, text: str) -> list[float]:
        self._load()
        if not self._model:
            raise RuntimeError("Embedding model not available")
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load()
        if not self._model:
            raise RuntimeError("Embedding model not available")
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vecs]
