# Architecture & Tech Stack

## System Overview

ATHAR OS is an async Python backend (Python 3.11, FastAPI) for an agentic travel guide for Algeria — not a marketplace, not social media. Built for data quality, AI-powered discovery, and offline-first mobile consumption.

```
                           ┌─────────────────────────────┐
                           │  PWA / Flutter App (future)  │
                           └──────────┬──────────────────┘
                                      │ HTTPS / JSON
                           ┌──────────▼──────────────────┐
                           │   FastAPI (uvicorn)          │
                           │                              │
                           │  Auth  POIs  Stays           │
                           │  Experiences  Transport      │
                           │  Trips  Discover             │
                           │  Admin  Users  Wilayas       │
                           │  Agents  Artisans  Events    │
                           └──────┬────┬────┬────┬───────┘
                                  │    │    │    │
                         ┌────────▼──┐┌─▼──┐┌▼───┐┌▼────┐
                         │PostgreSQL ││Qdnt││MinIO││Redis│
                         │  16.4     ││1.18││2026││7.4  │
                         │  asyncpg  ││gRPC││Apr ││pass │
                         └───────────┘└────┘└────┘└─────┘
```

All services except MinIO (standalone) run in Docker Compose on an isolated `backend` network. Only the API has an external port (bound to `127.0.0.1`).

## Tech Stack

| Component | Version | Notes |
|-----------|---------|-------|
| Python | **3.11** | |
| FastAPI | **0.139** | |
| Uvicorn | **0.34** | `--proxy-headers` for reverse proxy |
| SQLAlchemy | **2.0.38** | `[asyncio]` extra, asyncpg driver |
| Alembic | **1.15** | async migration runner |
| PyJWT | **2.13** | `[cryptography]` extra for EdDSA |
| Qdrant | **1.18** | gRPC, audit logging, API key auth |
| MinIO | **2026-04** | Standalone, local filesystem backend |
| Redis | **7.4** | Password-protected |
| PostgreSQL | **16.4** | Non-root |

## Tech Decisions & Tradeoffs

### Async SQLAlchemy 2.0 (asyncpg)
- **Why**: Blocking DB calls in async handlers waste a thread; asyncpg gives native async Postgres.
- **Tradeoff**: More complex session management, fewer ORM convenience features.

### EdDSA (Ed25519) for JWT
- **Why**: Asymmetric keys mean only the auth service can sign. ~8× faster verification than RS256. 32-byte keys.
- **Tradeoff**: Key pair needs to be provisioned. Auto-generated at startup if not configured (tokens invalidated on restart).

### Qdrant for Semantic Search (gRPC)
- **Why**: Pure Go binary, easy self-host, gRPC is ~2× faster than REST for vector search.
- **Tradeoff**: More infra than pgvector, but better performance at scale.

### ONNX for Embeddings
- **Why**: `sentence-transformers` v3.2+ supports ONNX backend with 2-3× CPU speedup.
- **Tradeoff**: ONNX adds a dependency (`optimum`, `onnxruntime`).

### MinIO for File Storage
- **Why**: S3-compatible, self-hosted, respects data sovereignty.
- **Tradeoff**: Currently standalone (not in Docker). 626 photos migrated from Wikimedia Commons (432 POIs). 4,306 POIs still using direct Commons URLs.

### Docker Compose Hardening
- **Why**: All services on isolated network, non-root users, `cap_drop: ALL`, no exposed internal ports, pinned image versions, resource limits.
- **Tradeoff**: Requires Docker Desktop (not available on dev machine — MinIO and Qdrant run standalone).

### Rate Limiting (slowapi)
- **Why**: Auth endpoints need protection against brute-force.
- **Tradeoff**: In-memory backend (not persistent across restarts).

## Middleware Stack (order in `main.py`)

1. **CORS** (`CORSMiddleware`) — explicit origins (`localhost:3000`, `localhost:5173`)
2. **LocaleMiddleware** — detects `Accept-Language` or `?lang=`, stores in `request.state.locale`
3. **SlowAPIMiddleware** — rate limits (10/min OTP, 20/min verify+refresh)
4. **TrustedHostMiddleware** — blocks host header injection
5. **Security headers** (custom middleware) — X-Content-Type-Options, X-Frame-Options, Permissions-Policy, Referrer-Policy
6. **Exception handlers** — `AppError` → JSON, unhandled → 500 with stack trace

## Security Headers (every response)

| Header | Value |
|--------|-------|
| X-Content-Type-Options | `nosniff` |
| X-Frame-Options | `DENY` |
| X-XSS-Protection | `0` |
| Referrer-Policy | `strict-origin-when-cross-origin` |
| Permissions-Policy | `geolocation=(), microphone=(), camera=()` |

## Route Count

**106 operations** across 18 endpoint modules + health.

## Project Structure

```
app/
├── api/v1/
│   ├── endpoints/     # 18 resource modules + health
│   │   ├── admin.py          # Admin operations
│   │   ├── agents.py         # AI agent chat
│   │   ├── artisans.py       # Artisan CRUD
│   │   ├── auth.py           # OTP, login, register
│   │   ├── collections.py    # Collections CRUD
│   │   ├── discover.py       # Discover feed
│   │   ├── events.py         # Events CRUD
│   │   ├── experiences.py    # Experience CRUD
│   │   ├── favorites.py      # Favorites CRUD
│   │   ├── geojson.py        # GeoJSON export
│   │   ├── health.py         # Health check
│   │   ├── pois.py           # POI CRUD + search + nearby
│   │   ├── recommendations.py # User prefs + recommendations
│   │   ├── search.py         # Unified search
│   │   ├── stays.py          # Stay CRUD
│   │   ├── transport.py      # Transport routing
│   │   ├── trips.py          # Trip CRUD + optimization
│   │   ├── users.py          # User profile
│   │   └── wilayas.py        # Wilaya list
│   ├── router.py      # Aggregates all endpoint modules
│   └── __init__.py
├── core/              # config, security (EdDSA), exceptions, i18n, logging
├── db/                # session (async engine with pool_timeout + SSL), base, mixins
├── models/            # 20 SQLAlchemy ORM models (16 files)
│   ├── artisan.py            # Artisan
│   ├── collection.py         # Collection, CollectionItem
│   ├── event.py              # Event
│   ├── experience.py         # Experience
│   ├── favorite.py           # Favorite
│   ├── poi.py                # POI
│   ├── provider_profile.py   # ProviderProfile
│   ├── recommendation.py     # UserPreference, Recommendation
│   ├── refresh_token.py      # RefreshToken
│   ├── station.py            # Station, TransportLine, LineStop
│   ├── stay.py               # Stay
│   ├── transport_operator.py # TransportOperator
│   ├── trip.py               # Trip, TripItem
│   ├── user.py               # User
│   ├── wilaya.py             # Wilaya
│   └── wilaya_distance.py    # WilayaDistance
├── schemas/           # ~97 pydantic schemas (19 files)
│   ├── admin.py, artisan.py, auth.py, collection.py
│   ├── event.py, experience.py, favorite.py, health.py
│   ├── poi.py, provider.py, provider_dashboard.py
│   ├── provider_profile.py, recommendation.py, search.py
│   ├── stay.py, transport.py, trip.py, user.py, wilaya.py
│   └── __init__.py
├── services/          # StorageService (MinIO), EmbeddingService (ONNX)
│                      # VectorSearchService (Qdrant), TransitRoutingService
│                      # TransportService, TripOptimizer, TripBriefGenerator
│                      # RecommendationEngine, POIGraphService
└── main.py            # App factory, lifespan, middleware stack, error handlers
```
