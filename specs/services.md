# Services: Storage, Embeddings, Vector Search

## StorageService (`app/services/storage.py`)

MinIO wrapper for file uploads.

### Configuration

```python
class MinIOSettings(BaseSettings):
    endpoint: str = "localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket_name: str = "athar-media"
    use_ssl: bool = False
    public_url: str = "http://localhost:9000"
```

### Behaviour

```python
async def upload(file: UploadFile, folder: str = "general") -> str:
```

1. Validates file type (`.jpg`, `.jpeg`, `.png`, `.webp` only).
2. Validates file size (max 10 MB).
3. Generates UUID filename (e.g., `pois/a1b2c3d4-e5f6-7890-abcd-ef1234567890.jpg`).
4. Creates `athar-media` bucket if not exists.
5. Sets bucket policy to **public-read** — no presigned URLs needed.
6. Uploads with `content-type` for browser display.
7. Returns public URL: `http://localhost:9000/athar-media/pois/uuid.jpg`.

**Graceful fallback**: If MinIO is not running, logs a warning and returns `None`.

### Public Bucket Decision

Files are world-readable by design:
- Travel photos and POI images are not sensitive.
- Avoids presigned URL complexity.
- Acceptable for MVP; can add auth on read if needed later.

---

## EmbeddingService (`app/services/embeddings.py`)

sentence-transformers wrapper for local text embeddings.

```python
class EmbeddingService:
    model_name: str = "all-MiniLM-L6-v2"  # 384-dim
```

### Behaviour

- **Lazy loading**: Model loads on first `encode()` call, not at startup.
- **Download**: First call downloads ~80MB to `~/.cache/huggingface/`.
- **Normalization**: Output vectors are L2-normalized (unit length) — required for cosine similarity in Qdrant.

```python
async def encode(text: str) -> list[float]:
    # Runs model.encode() in a thread pool to not block event loop
    # Returns 384-dim normalized vector
```

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
    prefer_grpc: bool = True
    collection_name_pois: str = "pois"
    collection_name_experiences: str = "experiences"
    vector_size: int = 384
```

### Collections

| Collection | Vector Dim | Payload | Used By |
|-----------|-----------|---------|---------|
| `pois` | 384 | `{poi_id, name, description, category, wilaya_id}` | POI search |
| `experiences` | 384 | `{experience_id, title, description, type, wilaya_id}` | Experience search |

### Methods

```python
async def index_poi(poi_id: str, text: str, payload: dict) -> None
async def index_experience(experience_id: str, text: str, payload: dict) -> None
async def search(text: str, filters: dict | None = None, limit: int = 20) -> list[dict]
async def search_experiences(text: str, filters: dict | None = None, limit: int = 20) -> list[dict]
async def delete_poi(poi_id: str) -> None
async def delete_experience(experience_id: str) -> None
```

### Startup Auto-Indexing

On app startup (`lifespan`), the service:
1. Checks if `pois` and `experiences` collections exist.
2. If they exist and have points, skips (assumes already indexed).
3. Otherwise, fetches all POIs/Experiences from PostgreSQL and indexes them.
4. Logs count of indexed items.

This keeps the search index in sync with the database without manual reindexing.

### Search Flow

```
1. Receive text query + optional filters (wilaya_id, category/type)
2. EmbeddingService.encode(text) → 384-dim vector
3. Qdrant.search(collection, vector, filter) → scored results
4. Extract IDs from results
5. SQLAlchemy: SELECT * FROM pois WHERE id IN (results)
6. Attach scores from Qdrant (optional, for relevance display)
7. Return items ordered by Qdrant score
```

### Graceful Fallback

If Qdrant is not running:
- `search()` returns empty list.
- `index_*()` logs warning and does nothing.
- DB-only search (SQL LIKE on name/title) is used as fallback in endpoints.
