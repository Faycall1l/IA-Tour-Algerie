# Architecture & Tech Stack

## System Overview

ATHAR OS is an async Python backend for a three-sided marketplace connecting travelers with local Algerian providers (guides, agencies, hotels). Built for sovereignty, offline-first mobile consumption, and hackathon-velocity iteration.

```
┌─────────────────────────────────────────────────────┐
│                  Flutter App (future)                │
│              PWA (offline-first shell)               │
└────────────────┬────────────────────────────────────┘
                 │ HTTPS / JSON
┌────────────────▼────────────────────────────────────┐
│           FastAPI (async, uvicorn)                   │
│  ┌─────┬─────┬──────┬──────┬──────┬───────────┐   │
│  │Auth │POIs │Prices│ Live │Exper │Bookings   │   │
│  │     │     │      │ Feed │iences│+ Notifs   │   │
│  └──┬──┴──┬──┴──┬───┴──┬───┴──┬───┴───────────┘   │
│     │     │     │      │      │                     │
└─────┼─────┼─────┼──────┼──────┼─────────────────────┘
      │     │     │      │      │
  ┌───▼──┐┌─▼──┐┌─▼───┐┌─▼───┐┌─▼───┐
  │ PG   ││Qdnt││MinIO││Redis││API  │
  │SQLAl ││    ││     ││(fut)││GPT  │
  └──────┘└────┘└─────┘└─────┘└─────┘
```

## Tech Decisions & Tradeoffs

### Async SQLAlchemy 2.0 (asyncpg)
- **Why**: Blocking DB calls in async handlers waste a thread; asyncpg gives native async Postgres.
- **Tradeoff**: More complex session management, fewer ORM convenience features (e.g., no `lazy='joined'` without `selectinload`).

### Passwordless Auth via OTP
- **Why**: No email/password friction; phone number is the identity anchor in Algeria. WhatsApp OTP matches local usage patterns.
- **Tradeoff**: Recovery depends on phone number access; no email fallback yet.

### Qdrant for Semantic Search
- **Why**: Pure Go binary, easy self-host, native async gRPC, supports filtering + vector search together. Keeps data in-country.
- **Tradeoff**: More infra than pgvector (which would avoid a separate service), but better performance at scale and clearer separation.

### MinIO for File Storage
- **Why**: S3-compatible, self-hosted, respects data sovereignty, public-read policies avoid presigned URL complexity.
- **Tradeoff**: Public-read means anyone with the URL can view files. Acceptable for travel photos (no sensitive data).

### sentence-transformers locally
- **Why**: All data stays in-country. No API call to OpenAI for embeddings. `all-MiniLM-L6-v2` is 80MB, runs on CPU in ~50ms per text.
- **Tradeoff**: Less accurate than `text-embedding-3-large`, but zero cost and zero data export.

### Separate Qdrant Collections (not shared)
- **Why**: POIs and experiences have different payload schemas. Separate collections avoid messy filter logic and allow independent reindexing.
- **Tradeoff**: Two collections to manage, but the schema difference justifies it.

### Single ProviderProfile table
- **Why**: Simpler than separate GuideProfile/AgencyProfile/HotelProfile tables. Single migration, single query pattern. Optional fields cover all types.
- **Tradeoff**: Some fields are irrelevant per type (e.g., `license_number` for a hotel), but this is manageable at this scale.

### Booking state machine
- **Why**: Simple linear lifecycle (`pending → confirmed → completed | cancelled`) is understandable for MVP. Complex multi-step booking would need a state machine library.
- **Tradeoff**: No partial payments, no dispute states, no timeouts.

### structlog for JSON logging
- **Why**: Structured logs are parseable, searchable, and carry correlation IDs. Critical for debugging async requests.
- **Tradeoff**: More verbose config than standard logging, but worth it.

### LocaleMiddleware (AR/FR/EN/TZ)
- **Why**: Algerian market has 4 significant languages. Middleware detects from Accept-Language or query param.
- **Tradeoff**: Translations are minimal (error messages only). Full i18n of content is deferred.

## Project Structure

```
app/
├── api/v1/
│   ├── endpoints/     # 11 resource modules (auth, pois, prices, ...)
│   ├── router.py      # Aggregates all endpoint modules
│   └── __init__.py
├── core/              # config, security, exceptions, i18n, logging
├── db/                # session, base, mixins
├── models/            # 13 SQLAlchemy ORM models
├── schemas/           # 50+ pydantic schemas for request/response
├── services/          # StorageService, EmbeddingService, VectorSearchService
└── main.py            # App factory, lifespan, middleware, error handlers
```

## Data Flow Diagram (Key Path)

```
Traveler searches "historical sites" →
  GET /api/v1/pois?search=historical+sites →
    VectorSearchService.search(text) →
      EmbeddingService.encode(text) →
        sentence-transformers (local) →
          384-dim vector
      Qdrant.search(collection="pois", vector) →
        {poi_id, score}
    SQLAlchemy: SELECT pois WHERE id IN (...) +
      SELECT AVG(score), COUNT(*) FROM reviews WHERE poi_id IN (...) →
    Response: [POIRead { ..., average_score, total_reviews }]
```
