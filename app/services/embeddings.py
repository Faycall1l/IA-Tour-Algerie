from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL_LOCAL_PATH = "/Users/faycalamrouche/.cache/athar-mlmini"
EMBEDDING_DIM = 384
ONNX_PROVIDERS = ["CPUExecutionProvider"]


class EmbeddingService:
    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer

            self._load_from_cache(SentenceTransformer)
        except Exception as exc:
            logger.warning("Embedding model not found in cache (%s) — attempting download", exc)
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

    def _load_from_cache(self, sentence_transformer) -> None:
        """Try local model dir first, then the HF cache by name (both ONNX)."""
        from pathlib import Path

        candidates: list[tuple[str, dict | None]] = []
        if Path(MODEL_LOCAL_PATH).exists():
            candidates.append((MODEL_LOCAL_PATH, {"file_name": "onnx/model.onnx"}))
        candidates.append((MODEL_NAME, {"file_name": "onnx/model.onnx"}))
        candidates.append((MODEL_NAME, None))

        last_exc: Exception | None = None
        for name, kwargs in candidates:
            try:
                if kwargs:
                    self._model = sentence_transformer(
                        name,
                        backend="onnx",
                        local_files_only=True,
                        model_kwargs={
                            **kwargs,
                            "providers": ONNX_PROVIDERS,
                        },
                    )
                else:
                    self._model = sentence_transformer(name, local_files_only=True)
                logger.info(
                    "Embedding model loaded (ONNX, local): %s",
                    Path(name).name if "/" in name else name,
                )
                return
            except Exception as exc:  # noqa: PERF203
                last_exc = exc
        raise last_exc if last_exc else RuntimeError("no embedding model candidates")

    def warm(self) -> None:
        self._load()

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
