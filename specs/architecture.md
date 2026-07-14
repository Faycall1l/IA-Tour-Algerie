# Architecture & Tech Stack

## System Overview

ATHAR OS is an async Python backend (Python 3.11, FastAPI) for a three-sided marketplace connecting travelers with local Algerian providers (guides, agencies, hotels). Built for sovereignty, offline-first mobile consumption, and hackathon-velocity iteration.

```
                          ┌─────────────────────────────┐
                          │  PWA / Flutter App (future)  │
                          └──────────┬──────────────────┘
                                     │ HTTPS / JSON
                          ┌──────────▼──────────────────┐
                          │   FastAPI (uvicorn)          │
                          │                              │
                          │  Auth  POIs  Prices  Live    │
                          │  Experiences  Stays  Trips   │
                          │  Bookings  Notifications     │
                          │  Transport  Circuits         │
                          │  Discover  Admin  Users      │
                          │  Wilayas  Health             │
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

**~97 routes** across 18 endpoint modules + health + 3 legacy.

## Project Structure

```
app/
├── api/v1/
│   ├── endpoints/     # 18 resource modules
│   │   ├── admin.py          # 12 routes
│   │   ├── auth.py           # 3 routes
│   │   ├── bookings.py       # 4 routes
│   │   ├── circuits.py       # 2 routes
│   │   ├── discover.py       # 4 routes
│   │   ├── events.py         # 2 routes
│   │   ├── experiences.py    # 7 routes
│   │   ├── health.py         # 1 route
│   │   ├── live.py           # 4 routes
│   │   ├── notifications.py  # 3 routes
│   │   ├── pois.py           # 6 routes
│   │   ├── prices.py         # 3 routes
│   │   ├── reviews.py        # 7 routes
│   │   ├── stays.py          # 5 routes
│   │   ├── transport.py      # 7 routes
│   │   ├── trips.py          # 11 routes
│   │   ├── users.py          # 6 routes
│   │   └── wilayas.py        # 2 routes
│   ├── router.py      # Aggregates all endpoint modules
│   └── __init__.py
├── core/              # config, security (EdDSA), exceptions, i18n, logging
├── db/                # session (async engine with pool_timeout + SSL), base, mixins
├── models/            # 26 SQLAlchemy ORM models (21 files)
│   ├── poi.py              # POI
│   ├── user.py             # User
│   ├── wilaya.py           # Wilaya
│   ├── stay.py             # Stay
│   ├── experience.py       # Experience
│   ├── trip.py             # Trip, TripItem
│   ├── circuit.py          # Circuit, CircuitItem
│   ├── booking.py          # Booking
│   ├── review.py           # Review, ReviewVote
│   ├── price_report.py     # PriceReport
│   ├── live_post.py        # LivePost
│   ├── notification.py     # Notification
│   ├── refresh_token.py    # RefreshToken
│   ├── provider_profile.py # ProviderProfile
│   ├── traveler_profile.py # AtharTravelerProfile
│   ├── station.py          # Station, TransportLine, LineStop
│   ├── local_agency.py     # LocalAgency
│   ├── wilaya_distance.py  # WilayaDistance
│   ├── poi_experience.py   # POI↔Experience junction
│   └── event.py            # Event
├── schemas/           # ~90 pydantic schemas (20 files)
│   ├── admin.py, auth.py, booking.py, circuit.py, event.py
│   ├── experience.py, health.py, live_post.py, notification.py
│   ├── poi.py, price_report.py, provider_profile.py, review.py
│   ├── stay.py, transport.py, trip.py, user.py, wilaya.py
│   └── __init__.py
├── services/          # StorageService (MinIO), EmbeddingService (ONNX)
│                      # VectorSearchService (Qdrant), TransitRoutingService
│                      # TransportService, TripOptimizer, TripBriefGenerator
└── main.py            # App factory, lifespan, middleware stack, error handlers
```
