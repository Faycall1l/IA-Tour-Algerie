# API Reference

ATHAR exposes a REST API under the `/api/v1` prefix. This reference is generated from the live OpenAPI inventory (87 paths, 112 operations).

## Auth Scopes

| Scope | Meaning |
|-------|---------|
| **Public** | No `Authorization` header required |
| **Optional** | Returns personalized data (e.g. `is_favorited`) if a valid Bearer token is supplied |
| **Auth** | Requires `Authorization: Bearer <access_token>` |
| **Provider/Admin** | Requires a provider (`guide`, `agency`, `hotel`) or `admin` role |
| **Admin** | Requires the `admin` role |

## Route Inventory

### Health

```
GET    /api/v1/health                          # Service + database health check (public)
```

### Authentication (prefix `/auth`)

```
POST   /api/v1/auth/send-otp                   # Send passwordless OTP (public, 10/min)
POST   /api/v1/auth/verify-otp                 # Verify OTP → access + refresh tokens (public, 20/min)
POST   /api/v1/auth/refresh                    # Rotate tokens (public, 20/min; replay revokes family)
POST   /api/v1/auth/register-provider          # Register as a provider (auth, 5/min)
```

OTP is 6 digits, TTL 5 minutes, max 5 attempts per code, max 3 sends per phone per 10 minutes. The OTP is never returned in the response body.

### Wilayas

```
GET    /api/v1/wilayas                         # List 69 wilayas (public, ?search=)
GET    /api/v1/wilayas/{wilaya_id}             # Single wilaya (public)
```

### POIs (prefix `/pois`, tags "Points of Interest")

```
POST   /api/v1/pois                            # Create POI (provider/admin)
GET    /api/v1/pois                            # List POIs (public; ?wilaya_id=&category=&neighborhood=&search=&sort=)
GET    /api/v1/pois/neighborhoods              # Distinct neighborhoods (public, ?wilaya_id=)
GET    /api/v1/pois/nearby                     # Nearby POIs (public, ?lat=&lng=&radius_km=&category=)
GET    /api/v1/pois/search                     # Semantic search via Qdrant + FTS fallback (public, ?q=&limit=)
GET    /api/v1/pois/tour/optimize              # Optimized walking tour (public, ?wilaya_id=&budget_hours=&categories=&max_pois=)
GET    /api/v1/pois/tour/clusters              # Density-based POI clusters (public, ?wilaya_id=&radius_m=)
GET    /api/v1/pois/tour/hubs                  # Transit-hub POIs (public, ?wilaya_id=&top_n=)
GET    /api/v1/pois/{poi_id}                   # POI detail (optional auth → is_favorited)
PATCH  /api/v1/pois/{poi_id}                   # Partial update (provider/admin)
POST   /api/v1/pois/{poi_id}/photo             # Upload photo → MinIO (provider/admin, multipart)
GET    /api/v1/pois/{poi_id}/similar           # Similar POIs in same wilaya/category (public)
DELETE /api/v1/pois/{poi_id}                   # Delete POI (provider/admin)
```

POI responses include TripAdvisor-style fields: `ranking`, `price_level`, `suggested_duration_min`, `photo_urls[]`, `subtype`, `name_ar`/`name_en`, `is_featured`, `fun_fact`.

### Experiences (prefix `/experiences`)

```
POST   /api/v1/experiences                     # Create experience (auth; role must be guide/agency/hotel)
GET    /api/v1/experiences                     # List active (public; ?wilaya_id=&category=&provider_id=&season=&provider_type=&status=)
GET    /api/v1/experiences/search              # Semantic search via Qdrant + FTS fallback (public)
GET    /api/v1/experiences/{experience_id}     # Detail + provider info (optional auth → is_favorited)
PUT    /api/v1/experiences/{experience_id}     # Update (owner/admin)
DELETE /api/v1/experiences/{experience_id}     # Delete (owner/admin)
POST   /api/v1/experiences/{experience_id}/photos  # Upload multiple photos (owner/admin, multipart)
```

### Stays (prefix `/stays`)

```
POST   /api/v1/stays                           # Create stay (auth; role hotel/agency/admin)
GET    /api/v1/stays                           # List active (public; ?wilaya_id=&property_type=&min_price=&max_price=)
GET    /api/v1/stays/{stay_id}                 # Stay detail (optional auth → is_favorited)
PUT    /api/v1/stays/{stay_id}                 # Update (owner/admin)
DELETE /api/v1/stays/{stay_id}                 # Delete (owner/admin)
```

### Transport Network (prefix `/transport`)

```
GET    /api/v1/transport/routes/from/{origin_wilaya_id}        # All destinations from a wilaya (public)
GET    /api/v1/transport/routes/{origin_wilaya_id}/{dest_wilaya_id}  # Multi-modal options: train/bus/flight/taxi + driving estimates
GET    /api/v1/transport/stations              # List stations (public; ?wilaya_id=&type=)
GET    /api/v1/transport/stations/nearby       # Nearest stations (public, ?lat=&lng=&limit=&type=)
GET    /api/v1/transport/lines                 # List transport lines (public, ?mode=)
GET    /api/v1/transport/plan                  # Turn-by-turn walking + transit planner (public, ?from_lat=&from_lng=&to_lat=&to_lng=)
GET    /api/v1/transport/access/{poi_id}       # Transit access for a POI (public, ?lat=&lng=&name=)
GET    /api/v1/transport/route-to-poi/{poi_id} # Directions from GPS point to a POI (public, ?from_lat=&from_lng=)
GET    /api/v1/transport/operators             # Operators with contacts (public, ?mode=train|flight|bus|taxi|tram|cablecar)
```

### Trips — Trip Dashboard (prefix `/trips`)

```
POST   /api/v1/trips                           # Create trip (auth)
GET    /api/v1/trips                           # List my trips (auth; ?status=active|archived)
GET    /api/v1/trips/brief/{wilaya_id}         # Generate wilaya trip brief (public)
GET    /api/v1/trips/{trip_id}                 # Trip detail with day plans (auth, owner)
PUT    /api/v1/trips/{trip_id}                 # Update trip (auth, owner)
DELETE /api/v1/trips/{trip_id}                 # Delete trip (auth, owner)
POST   /api/v1/trips/{trip_id}/items           # Add item (auth, owner)
PUT    /api/v1/trips/{trip_id}/items/{item_id} # Reorder / change day / update item (auth, owner)
DELETE /api/v1/trips/{trip_id}/items/{item_id} # Remove item (auth, owner)
POST   /api/v1/trips/{trip_id}/optimize        # Reorder day items to minimize walking (auth, owner)
POST   /api/v1/trips/{trip_id}/share           # Generate share token + URL (auth, owner)
GET    /api/v1/trips/shared/{share_token}      # View shared trip without auth (public)
```

### Events (prefix `/events`, read-only calendar for travelers)

```
GET    /api/v1/events                          # List events (public; ?wilaya_id=&category=&month=)
POST   /api/v1/events                          # Create event (provider/admin)
GET    /api/v1/events/{event_id}               # Event detail (public)
PATCH  /api/v1/events/{event_id}               # Update event (provider/admin)
DELETE /api/v1/events/{event_id}               # Delete event (provider/admin)
```

### Artisans (prefix `/artisans`)

```
POST   /api/v1/artisans                        # Create artisan profile (auth; auto-promotes traveler → artisan)
GET    /api/v1/artisans                        # List (public; ?wilaya_id=&craft_type=&accepts_visitors=&search=&sort=)
GET    /api/v1/artisans/{artisan_id}           # Detail (public)
PUT    /api/v1/artisans/{artisan_id}           # Update (owner/admin)
DELETE /api/v1/artisans/{artisan_id}           # Delete (owner/admin)
```

### Search — Unified Full-Text (prefix `/search`)

```
GET    /api/v1/search                          # POIs + stays + experiences via tsvector (public, ?q=&page=&page_size=)
GET    /api/v1/search/suggest                  # Autocomplete across all three (public, ?q=&limit=)
```

### GeoJSON — Spatial data (public)

```
GET    /api/v1/pois.geojson                    # POIs as FeatureCollection (?wilaya_id=&category=&is_featured=&limit=)
GET    /api/v1/stays.geojson                   # Stays as FeatureCollection (?wilaya_id=&limit=)
GET    /api/v1/experiences.geojson             # Active experiences as FeatureCollection (?wilaya_id=&category=&limit=)
GET    /api/v1/nearby/pois                     # POIs within radius (?lat=&lng=&radius_km=&limit=)
```

### Collections — Wishlists (prefix `/collections`, auth)

```
GET    /api/v1/collections                     # List user's collections
POST   /api/v1/collections                     # Create collection
GET    /api/v1/collections/{collection_id}     # Collection with items
PUT    /api/v1/collections/{collection_id}     # Update name/description/is_public
DELETE /api/v1/collections/{collection_id}     # Delete collection + items
POST   /api/v1/collections/{collection_id}/items   # Batch add items (deduplicates)
DELETE /api/v1/collections/{collection_id}/items/{item_id}  # Remove single item
```

### Favorites (prefix `/favorites`, auth)

```
GET    /api/v1/favorites                       # List favorites (?entity_type=poi|experience|stay)
POST   /api/v1/favorites                       # Add favorite (entity_type + entity_id)
DELETE /api/v1/favorites/{favorite_id}         # Remove favorite
```

### Recommendations — Personalized (prefix `/recommendations`, auth)

```
GET    /api/v1/recommendations                 # Ranked recs (?wilaya_id=&entity_type=&limit=)
GET    /api/v1/recommendations/preferences     # Get user preferences
PATCH  /api/v1/recommendations/preferences     # Update preferences
POST   /api/v1/recommendations/preferences/derive  # Re-derive preferences from interactions
POST   /api/v1/recommendations/{rec_id}/feedback   # Feedback: liked/dismissed/bookmarked
```

### Users (prefix `/users`)

```
GET    /api/v1/users/me                        # Current user profile (auth)
PUT    /api/v1/users/me                        # Update profile (auth)
PUT    /api/v1/users/me/role                   # Switch role (auth; self-assignable roles only — admin blocked)
PUT    /api/v1/users/me/profile                # Update provider profile (auth; provider role required)
GET    /api/v1/users/me/dashboard              # Provider dashboard: listings + metrics (auth; provider/admin)
GET    /api/v1/users/providers                 # List providers (public; ?role=&page=&page_size=)
GET    /api/v1/users/providers/{user_id}       # Single provider detail (public)
```

### Discover (prefix `/discover`)

```
GET    /api/v1/discover/wilayas                # All wilayas with summary stats + highlight POI (public)
GET    /api/v1/discover/wilayas/{wilaya_id}    # Consolidated view: POIs + experiences + stays + artisans (public)
GET    /api/v1/discover/wilayas/{wilaya_id}/guide   # Curated guide, POIs by combined score, top N per category (public, ?top=)
GET    /api/v1/discover/experiences/by-poi/{poi_id} # Experiences matching a POI (public)
```

### AI Agents (prefix `/agent`, all auth + rate limited)

```
POST   /api/v1/agent/chat                      # Travel assistant (20/h)
POST   /api/v1/agent/plan-trip                 # Itinerary planner (10/h)
POST   /api/v1/agent/search                    # Unified search via agent (30/h)
POST   /api/v1/agent/transport                 # Transport specialist: routes/schedules/contacts (20/h)
POST   /api/v1/agent/events                    # Events & festivals specialist (20/h)
GET    /api/v1/agent/sessions                  # List conversation sessions (30/h)
DELETE /api/v1/agent/sessions/{session_id}     # Soft-delete session + memories (20/h)
```

Agents support multi-turn memory via `session_id` in the request body. All agent runs are traced, circuit-broken, and time-limited by the resilience stack (`app/agents/resilience.py`).

**Structured deep links:** every chat/search/plan/transport/events reply carries a `links[]` array of `AgentLink` objects (`type` = poi | stay | experience | event | artisan | wilaya | transport, plus `id`, `name`, `url`, `wilaya_id`) pointing to the concrete entities the answer references, e.g. `/pois/{id}`, `/wilayas/{id}`, `/transport/plan?from_wilaya=16&to_wilaya=31`. URLs are relative by default and become absolute when `ATHAR_APP_URL` is configured. Replies also include a plain-text `Quick links:` footer for text-only clients. The same links are emitted on degraded (fallback) replies.

**Offline fallback (degraded mode):** when the LLM backend is unavailable (circuit breaker open, per-run timeout, or `ATHAR_AGENT__VLLM` not configured), `POST /agent/chat`, `/search`, `/transport`, and `/events` fall back to a rule-based responder (`app/agents/fallback.py`) that answers the most common query shapes — wilaya guides, POI/stay/experience search, transport routes, operator contacts, events — directly from the database using the same validated tools as the agents. Fallback replies set `degraded: true` in the body and an `X-Agent-Degraded: rule-based-fallback` response header. Queries the fallback cannot answer confidently return 503; `/plan-trip` (itinerary) never degrades since planning requires the LLM.

### Admin (prefix `/admin`, all admin-only)

```
GET    /api/v1/admin/stats                     # Dashboard counts + POI distribution
GET    /api/v1/admin/users                     # List users (?role=&verified=&page=&page_size=)
PUT    /api/v1/admin/users/{user_id}/role      # Change user role (creates/deletes provider profile)
PUT    /api/v1/admin/users/{user_id}/verify    # Toggle is_verified
GET    /api/v1/admin/providers                 # List provider profiles (?verified=&provider_type=)
PUT    /api/v1/admin/providers/{profile_id}/approve  # Approve provider
DELETE /api/v1/admin/experiences/{experience_id}    # Delete any experience
GET    /api/v1/admin/verify/poi/{poi_id}       # LLM/rule-based POI quality verification
GET    /api/v1/admin/verify/stats              # POI data-quality stats
GET    /api/v1/admin/agent/stats               # Agent observability: success rates, tokens, traces (?limit=)
```

## Naming Conventions

- **Plural nouns** for collections: `/pois`, `/experiences`, `/stays`
- **Snake case** for query params: `?wilaya_id=`, `?page_size=`
- **Search as sub-resource**: `GET /experiences/search?q=...`

## Pagination

All list endpoints use cursorless pagination:

| Param | Default | Max |
|-------|---------|-----|
| `page` | 1 | — |
| `page_size` | 20 | 50 |

Response includes metadata:

```json
{
  "items": [...],
  "total": 142,
  "page": 1,
  "page_size": 20,
  "total_pages": 8,
  "has_prev": false,
  "has_next": true
}
```

## Error Responses

Consistent JSON shape via `AppError` hierarchy:

```json
{
  "error": "not_found",
  "message": "Stay not found",
  "details": null
}
```

| Exception | HTTP | `error` key |
|-----------|------|-------------|
| `NotFoundException` | 404 | `not_found` |
| `BadRequestException` | 400 | `bad_request` |
| `UnauthorizedException` | 401 | `unauthorized` |
| `ForbiddenException` | 403 | `forbidden` |
| `ConflictException` | 409 | `conflict` |
| `ValidationException` | 422 | `validation_error` |
| Unhandled | 500 | `internal_error` |

## Middleware Stack (order in `main.py`)

1. **TrustedHostMiddleware** — validates `Host` header against `allowed_hosts` (default loopback only; `ATHAR_ALLOWED_HOSTS` JSON override)
2. **SecurityHeadersMiddleware** — CSP `default-src 'none'`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, HSTS in prod; `Cache-Control: no-store` on `/auth/*` and `/users/me`
3. **CORS** (`CORSMiddleware`) — explicit origins (not `*`)
4. **LocaleMiddleware** — detects `Accept-Language` or `?lang=`, stores in `request.state.locale`, emits `Content-Language`
5. **ErrorMiddleware** — catches `AppError` → JSON, unhandled → 500 with sanitized stack trace
6. **Rate limiter** — slowapi with Redis backend (sorted-set sliding window, shared across workers; in-memory fail-open fallback)

## Request Flow

```
Request → TrustedHost → SecurityHeaders → CORS → LocaleMiddleware → ErrorMiddleware → Limiter → Router → Endpoint
                                                                                                                          │
                                                                                                                   get_db() → async session
                                                                                                                   get_current_user() → JWT decode → DB fetch
                                                                                                                   business logic → DB queries
                                                                                                                   response → Pydantic validation → JSON
```

## Auth & Security

- **JWT EdDSA (Ed25519)** — asymmetric keys, persisted to `secrets/jwt_ed25519.pem`, aud/iss validation
- **Passwordless OTP** — 6 digits, TTL 5 min, 5 attempts max, 3 sends/10 min per phone, constant-time compare
- **Refresh token rotation** — presenting a revoked token revokes the entire token family (theft detection)
- **Rate limits** — 10/min send-otp, 20/min verify-otp/refresh, 5/min register-provider; agents: 20/h chat/transport/events, 10/h plan-trip, 30/h search/sessions, 20/h delete
- **Roles** — self-assignment restricted to `traveler/guide/agency/hotel` (admin blocked); deactivated users rejected at the auth boundary
- **Docs gating** — `/docs`, `/redoc`, `/openapi.json` disabled unless `debug` is true

## Trip Item Types

Trip items are polymorphic with no FK constraints:

| `item_type` | Description | Duration |
|------------|-------------|----------|
| `poi` | Points of interest | 30–90 min (category-based) |
| `experience` | Bookable tours/activities | From DB |
| `stay` | Accommodation | 720 min (overnight) |
| `restaurant` | Dining | 90 min |
| `transport` | Transfers between locations | 60 min |

## Stay Model

Stays represent bookable accommodations with:

- **Property types:** `hotel`, `hostel`, `guesthouse`, `eco_lodge`, `apartment`
- **Amenities:** JSON array of strings (e.g., `["wifi", "parking", "breakfast"]`)
- **Location:** Wilaya FK + address + lat/lng
- **Capacity:** `max_guests` + `total_rooms`
- **Pricing:** `price_per_night_dzd` in DZD (800–15,000)
- **Photos:** MinIO URLs array
- **Availability:** `is_active` flag

## Discover Endpoints

### Consolidated Wilaya View

`GET /api/v1/discover/wilayas/{wilaya_id}` returns all content for a wilaya:

```json
{
  "wilaya_id": 16,
  "wilaya_name": "Alger",
  "pois": [
    {
      "id": "...",
      "name": "Grande Poste",
      "category": "historical"
    }
  ],
  "experiences": [
    {
      "id": "...",
      "title": "Algiers City Tour",
      "category": "tour",
      "provider_name": "Travel Algeria",
      "price_dzd": 5000
    }
  ],
  "stays": [
    {
      "id": "...",
      "name": "Hotel El Aurassi",
      "property_type": "hotel",
      "price_per_night_dzd": 15000
    }
  ],
  "artisans": [
    {
      "id": "...",
      "name": "Atelier Kabyle",
      "craft_type": "pottery",
      "is_verified": true
    }
  ]
}
```

### Wilaya Travel Guide

`GET /api/v1/discover/wilayas/{wilaya_id}/guide?top=10` returns curated per-wilaya guide:

- POIs sorted by combined score (`getting_there` JSON on each POI)
- Capped at top N per category (11 categories), featured POIs listed separately
- Includes transport access info (nearest station, distance, walking time, modes), experiences, stays
