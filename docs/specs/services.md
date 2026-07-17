# Services: Storage, Embeddings, Vector Search

## StorageService (`app/services/storage.py`)

MinIO wrapper for file uploads.

### Configuration

```python
class MinIOSettings(BaseSettings):
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "athar-uploads"
    secure: bool = False          # Set True in production with TLS
```

### Behaviour

```python
async def upload(file: UploadFile, folder: str = "general") -> str:
```

1. Validates file type (`.jpg`, `.jpeg`, `.png`, `.webp` only).
2. Validates file size (max 10 MB).
3. Generates UUID filename (e.g., `pois/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg`).
4. Creates bucket if not exists (`athar-uploads`).
5. Sets bucket policy to **public-read** — no presigned URLs needed.
6. Uploads with `content-type` for browser display.
7. Returns public URL.

**Graceful fallback**: If MinIO is not running, logs a warning and returns `None`.

### Public Bucket Decision

Files are world-readable by design:
- Travel photos and POI images are not sensitive.
- Avoids presigned URL complexity.
- Acceptable for MVP; can add auth on read if needed later.

### Docker Security

In docker-compose: MinIO runs with `cap_drop: ALL`, `no-new-privileges`, resource limits, and no external port exposure (only reachable via Docker internal network).

---

## EmbeddingService (`app/services/embeddings.py`)

sentence-transformers wrapper for local text embeddings.

```python
class EmbeddingService:
    model_name: str = "all-MiniLM-L6-v2"  # 384-dim
```

### Behaviour

- **Lazy loading**: Model loads on first `encode()` call, not at startup.
- **ONNX backend**: Attempts to load model with `backend="onnx"` for 2-3× CPU speedup. Falls back to default PyTorch backend if ONNX unavailable.
- **Download**: First call downloads ~80MB to `~/.cache/huggingface/`.
- **Normalization**: Output vectors are L2-normalized (unit length) — required for cosine similarity in Qdrant.

```python
def encode(text: str) -> list[float]:
    # Runs model.encode() synchronously (called from thread pool in endpoints)
    # Returns 384-dim normalized vector
```

### Backend Comparison

| Backend | Speed | Memory | Notes |
|---------|-------|--------|-------|
| Default (PyTorch) | 1× | FP32 (full) | Safe fallback |
| ONNX | 2-3× faster | FP32 or int8 | Requires `sentence-transformers[onnx]` |
| ONNX + int8 quantized | 3-4× faster | ~40% less | Requires optuna/optimum |

### Limitations

- `all-MiniLM-L6-v2` is a small, fast model. Good for search quality but not state-of-the-art.
- Multi-language: model supports some French/Arabic but English search works best.
- All processing is CPU on local machine — no GPU utilized.

---

## VectorSearchService (`app/services/vector_search.py`)

Qdrant client for semantic search.

### Configuration

```python
class QdrantSettings(BaseSettings):
    host: str = "localhost"
    port: int = 6333
    grpc_port: int = 6334
    prefer_grpc: bool = True       # gRPC is faster than REST
    api_key: str = ""              # Qdrant 1.16+ API key auth
```

### Collections

| Collection | Vector Dim | Payload | Used By |
|-----------|-----------|---------|---------|
| `pois` | 384 | `{poi_id, name, category, wilaya_id}` | POI search |
| `experiences` | 384 | `{experience_id, title, category, wilaya_id, provider_id, status}` | Experience search |

### Methods

```python
def index_poi(self, poi: POI) -> None
def index_experience(self, experience: Experience) -> None
def search(self, query: str, limit: int = 10) -> list[uuid.UUID]
def search_experiences(self, query: str, limit: int = 10) -> list[uuid.UUID]
def delete_poi(self, poi_id: uuid.UUID) -> None
def delete_experience(self, experience_id: uuid.UUID) -> None
```

### API Key Authentication

When `QDRANT_API_KEY` is set, the Qdrant client passes the API key on every request. All requests without the key are rejected with 401. Requires Qdrant 1.16+.

### gRPC vs REST

`prefer_grpc=True` uses Qdrant's gRPC interface instead of REST:
- ~2× faster for search operations
- Binary protocol (smaller payloads)
- Native streaming support

### Startup Auto-Indexing

On app startup (`lifespan`), the service:
1. Fetches all POIs/Experiences from PostgreSQL.
2. Skips if Qdrant collection already has points (dedup by ID).
3. Otherwise indexes all items into Qdrant.
4. Logs count of indexed items.

### Search Flow

```
1. Receive text query + optional filters (wilaya_id, category/type)
2. EmbeddingService.encode(text) → 384-dim vector
3. Qdrant.search(collection, vector, filter) → scored results
4. Extract UUIDs from result payloads
5. SQLAlchemy: SELECT * FROM pois WHERE id IN (results)
6. Return items ordered by Qdrant score
```

### Graceful Fallback

If Qdrant is not running:
- `search()` returns empty list (caller uses SQL ILIKE fallback).
- `index_*()` logs warning and does nothing.
- DB-only search (SQL `ILIKE` on name/title) is used as fallback in endpoints.
