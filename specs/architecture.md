# Architecture & Tech Stack

## System Overview

ATHAR OS is an async Python backend (Python 3.14, FastAPI 0.139) for a three-sided marketplace connecting travelers with local Algerian providers (guides, agencies, hotels). Built for sovereignty, offline-first mobile consumption, and hackathon-velocity iteration.

```
┌─────────────────────────────────────────────────────┐
│                  Flutter App (future)                │
│              PWA (offline-first shell)               │
└────────────────┬────────────────────────────────────┘
                 │ HTTPS / JSON (reverse proxy)
┌────────────────▼────────────────────────────────────┐
│           FastAPI 0.139 (uvicorn 0.34)               │
│  ┌─────┬─────┬──────┬──────┬──────┬───────────┐   │
│  │Auth │POIs │Prices│ Live │Exper │Bookings   │   │
│  │     │     │      │ Feed │iences│+ Notifs   │   │
│  └──┬──┴──┬──┴──┬───┴──┬───┴──┬───┴───────────┘   │
│     │     │     │      │      │                     │
└─────┼─────┼─────┼──────┼──────┼─────────────────────┘
      │     │     │      │      │
  ┌───▼──┐┌─▼──┐┌─▼───┐┌─▼───┐
  │ PG   ││Qdnt││MinIO││Redis│
  │16    ││1.18││2026 ││7.4  │
  │asyncp││gRPC││Apr  ││pass │
  └──────┘└────┘└─────┘└─────┘
```

All services run in Docker Compose on an isolated `backend` network. Only the API has an external port (bound to `127.0.0.1`).

## Tech Stack (verified July 2026)

| Component | Version | Notes |
|-----------|---------|-------|
| Python | **3.14.6** | JIT compiler, Android binary support |
| FastAPI | **0.139.0** | `app.frontend()` with deps |
| Uvicorn | **0.34.0** | `--proxy-headers` for reverse proxy |
| SQLAlchemy | **2.0.38** | `[asyncio]` extra, asyncpg driver |
| Alembic | **1.15.0** | async migration runner |
| PyJWT | **2.13.0** | `[cryptography]` extra for EdDSA |
| Qdrant | **1.18.2** | gRPC, audit logging, API key auth |
| MinIO | **2026-04-17** | OIDC/LDAP hardening |
| Redis | **7.4** | Password-protected |
| PostgreSQL | **16.4** | Non-root (UID 999) |

## Tech Decisions & Tradeoffs

### Async SQLAlchemy 2.0 (asyncpg)
- **Why**: Blocking DB calls in async handlers waste a thread; asyncpg gives native async Postgres.
- **Tradeoff**: More complex session management, fewer ORM convenience features.
- **2026 update**: SQLAlchemy 2.1 beta makes `greenlet` optional via `[asyncio]` extra.

### EdDSA (Ed25519) for JWT
- **Why**: RFC 8725bis (June 2026) recommends EdDSA as the default. Asymmetric keys mean only the auth service can sign. ~8× faster verification than RS256. 32-byte keys.
- **Tradeoff**: Key pair needs to be provisioned. Auto-generated at startup if not configured (tokens invalidated on restart).

### Qdrant for Semantic Search (gRPC)
- **Why**: Pure Go binary, easy self-host, gRPC is ~2× faster than REST for vector search. API key authentication since v1.16.
- **Tradeoff**: More infra than pgvector, but better performance at scale.

### ONNX for Embeddings
- **Why**: `sentence-transformers` v3.2+ (2024) supports ONNX backend with 2-3× CPU speedup. Falls back to default PyTorch if ONNX unavailable.
- **Tradeoff**: ONNX adds a dependency (`optimum`, `onnxruntime`) but the speedup is significant for CPU-only deployments.

### MinIO for File Storage
- **Why**: S3-compatible, self-hosted, respects data sovereignty, public-read policies avoid presigned URL complexity.
- **Tradeoff**: Public-read means anyone with the URL can view files. Acceptable for travel photos.

### Docker Compose Hardening
- **Why**: All services on isolated network, non-root users, `cap_drop: ALL`, no exposed internal ports, pinned image versions, resource limits.
- **Tradeoff**: More verbose compose file, but resistant to container escape and resource starvation.

### Rate Limiting (slowapi)
- **Why**: Auth endpoints need protection against brute-force. slowapi is the standard FastAPI rate limiter.
- **Tradeoff**: In-memory backend (not persistent across restarts). Redis backend planned.

## Middleware Stack (order in `main.py`)

1. **CORS** (`CORSMiddleware`) — explicit origins (`localhost:3000`, `localhost:5173`)
2. **LocaleMiddleware** — detects `Accept-Language` or `?lang=`, stores in `request.state.locale`
3. **SlowAPIMiddleware** — rate limits (10/min OTP, 20/min verify+refresh)
4. **TrustedHostMiddleware** — blocks host header injection
5. **Security headers** (custom middleware) — X-Content-Type-Options, X-Frame-Options, Permissions-Policy, Referrer-Policy
6. **Prometheus** (`prometheus-fastapi-instrumentator`) — metrics at `/metrics`
7. **Exception handlers** — `AppError` → JSON, unhandled → 500 with stack trace

## Security Headers (every response)

| Header | Value |
|--------|-------|
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| X-XSS-Protection | `0` |
| Referrer-Policy | `strict-origin-when-cross-origin` |
| Permissions-Policy | `geolocation=(), microphone=(), camera=()` |

## Route Count

**~50 routes** across 12 endpoint modules + 3 legacy + health + metrics.

## Project Structure

```
app/
├── api/v1/
│   ├── endpoints/     # 12 resource modules (auth, pois, prices, bookings, ...)
│   ├── router.py      # Aggregates all endpoint modules
│   └── __init__.py
├── core/              # config, security (EdDSA), exceptions, i18n, logging
├── db/                # session (async engine with pool_timeout + SSL), base, mixins
├── models/            # 13 SQLAlchemy ORM models
├── schemas/           # 50+ pydantic schemas
├── services/          # StorageService, EmbeddingService (ONNX), VectorSearchService
└── main.py            # App factory, lifespan, middleware stack, error handlers
```
