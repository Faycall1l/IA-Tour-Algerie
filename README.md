# ATHAR OS (أثر) — AI-Powered Sovereign Tourism Platform

**ATHAR OS** is a sovereign, AI-powered tourism platform for Algeria. It connects travelers with local providers (guides, agencies, hotels), offers real-time price intelligence, semantic POI/experience search, and WhatsApp-based trip management — all while respecting Loi 18-07 data sovereignty.

## Features

### Travel Data Platform
| Module | Routes | Description |
|--------|--------|-------------|
| **Auth** | 3 | Passwordless OTP via Twilio Verify (fallback "123456"), JWT EdDSA refresh |
| **Wilayas** | 2 | All 69 wilayas with AR/FR/EN names + GPS |
| **POIs** | 5 | CRUD, 12 categories, semantic search via Qdrant, MinIO photos, rating enrichment |
| **Price Reports** | 3 | Create, list, fair-price estimate (median) |
| **Reviews** | 4 | CRUD, ratings distribution, one review per user per POI constraint |
| **Live Posts** | 4 | CRUD with photos, moderation support |
| **Experiences** | 7 | CRUD, 8 types, semantic search, MinIO photos |
| **Stays** | 5 | CRUD for hotels/agencies, filters (wilaya, type, price), ownership enforcement |
| **Bookings** | 4 | State machine (pending→confirmed→completed/cancelled), WhatsApp alerts |
| **Notifications** | 3 | Paginated list, unread count, mark read |
| **Trips** | 10+1 | CRUD, itinerary items (POI/experience/stay/restaurant/transport), route optimizer, brief generator, WhatsApp send |
| **Discover** | 2 | Wilaya consolidated view (POIs + experiences + stays), POI-to-experience linking |
| **Admin Dashboard** | 11 | Price reports, users, providers, content moderation |

### Legacy Modules (guarded stubs)
| Module | Route |
|--------|-------|
| **Visa** | `/api/v1/visa/process-passport` |
| **WhatsApp Bot** | `/api/v1/whatsapp/webhook` |
| **Artisan Studio** | `/api/v1/studio/refine-video` |

## Tech Stack

- **Backend:** FastAPI (Python 3.11+), async SQLAlchemy 2.0 + asyncpg
- **Database:** PostgreSQL 16+, Qdrant (vector DB), Redis (rate limiting)
- **Storage:** MinIO (S3-compatible, self-hosted)
- **Search:** sentence-transformers (all-MiniLM-L6-v2, 384-dim, ONNX backend)
- **Auth:** JWT EdDSA (Ed25519), passwordless OTP via Twilio Verify
- **Messaging:** Twilio WhatsApp API (booking/trip alerts)
- **Monitoring:** Prometheus metrics, structured error middleware
- **Infrastructure:** Docker Compose, GitHub Actions CI
- **Containerization:** Multi-stage Docker build, non-root user, security hardening

## Project Structure

```
athar-os-prototype/
├── app/
│   ├── main.py                    # App factory, lifespan, middleware stack
│   ├── core/
│   │   ├── config.py              # Pydantic-settings config
│   │   ├── security.py            # JWT EdDSA create/decode
│   │   ├── exceptions.py          # AppError hierarchy (6 classes)
│   │   ├── error_middleware.py    # Structured error handling
│   │   ├── limiter.py            # Rate limiter (Redis/in-memory)
│   │   └── dependencies.py       # Shared deps
│   ├── db/
│   │   ├── base.py               # SQLAlchemy Base + metadata
│   │   ├── session.py            # Async session factory
│   │   └── migrations/           # Alembic (async)
│   ├── models/                   # 17 ORM models
│   │   ├── user.py, poi.py, review.py, experience.py, booking.py
│   │   ├── trip.py, stay.py, notification.py, live.py, price_report.py
│   │   ├── wilaya.py, provider_profile.py, athar_traveler.py, refresh_token.py
│   │   └── agency.py, live_post.py
│   ├── schemas/                  # Pydantic request/response schemas
│   ├── api/v1/endpoints/         # 80+ routes across 12+ routers
│   │   ├── auth.py, wilayas.py, pois.py, prices.py, reviews.py
│   │   ├── live.py, users.py, experiences.py, bookings.py
│   │   ├── notifications.py, trips.py, admin.py, stays.py, discover.py
│   │   └── legacy (guarded): visa.py, whatsapp.py, studio.py
│   ├── services/                 # Business logic
│   │   ├── storage.py            # MinIO file upload
│   │   ├── embedding.py          # sentence-transformers (ONNX)
│   │   ├── vector_search.py      # Qdrant collections (POIs + experiences)
│   │   ├── twilio.py             # Verify + WhatsApp
│   │   ├── trip_optimizer.py     # Route optimization + item enrichment
│   │   └── trip_brief.py         # Trip summary generation
│   └── utils/                    # Helpers
├── migrations/                   # Alembic env + versions (10 migrations)
├── specs/                        # Architecture / feature docs
├── tests/                        # 60+ tests (pytest-asyncio)
├── Dockerfile                    # Multi-stage, security hardening
├── docker-compose.yml            # API + PG + Redis + Qdrant + MinIO
└── pyproject.toml                # Ruff, pytest, coverage config
```

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Redis (optional, falls back to in-memory)
- Qdrant (optional, falls back to keyword search)
- MinIO (optional, falls back to local storage)

### Setup

```bash
git clone https://github.com/anomalyco/athar-os.git
cd athar-os-prototype
cp .env.example .env   # Configure your environment
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### Docker

```bash
docker compose up -d
```

## API Documentation

Once running, visit:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Prometheus Metrics:** http://localhost:8000/metrics

## Testing

```bash
pytest tests/ -v
```

## Architecture

### Key Design Decisions

- **Async SQLAlchemy 2.0** from start — prevents blocking in async endpoints
- **Passwordless OTP** via phone — fits Algerian market
- **JWT EdDSA (Ed25519)** over HS256 — asymmetric keys, no shared-secret risk
- **Three-sided marketplace:** Traveler ↔ Platform ↔ Provider
- **Agentic traveler layer is invisible** — agents work in background shaping UI, never a chat interface
- **Polymorphic TripItem model** — supports POIs, experiences, stays, restaurants, transport with a single items table
- **Dead-code service stubs** — legacy OCR, voice, media services replaced with stubs that log warnings

### Data Sovereignty

ATHAR OS is designed to respect Loi 18-07 (Algerian data protection law):
- All data stored in-country (PostgreSQL, MinIO, Qdrant)
- PII stripped before sending to external APIs
- All services designed for self-hosting on Algerian cloud infrastructure

## License

MIT
