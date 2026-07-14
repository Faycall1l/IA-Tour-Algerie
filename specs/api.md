# API Layer

## Route Inventory (~108 routes)

```
# Public
GET    /api/v1/health                          # Health check

# Auth
POST   /api/v1/auth/send-otp                   # Passwordless OTP
POST   /api/v1/auth/verify-otp                 # Login
POST   /api/v1/auth/refresh                    # Rotate tokens

# Wilayas
GET    /api/v1/wilayas                         # List 69 wilayas
GET    /api/v1/wilayas/{wilaya_id}             # Single wilaya

# POIs

# Price Reports
POST   /api/v1/prices                          # Create price report (auth)
GET    /api/v1/prices                          # List price reports
GET    /api/v1/prices/estimate                 # Fair price engine

# Reviews
POST   /api/v1/reviews                         # Create review (auth, one per user per POI)
GET    /api/v1/reviews                         # List reviews (sort: recent|highest|lowest|helpful)
GET    /api/v1/reviews/ratings/{poi_id}        # Rating distribution
PUT    /api/v1/reviews/{review_id}             # Edit review (author only)
POST   /api/v1/reviews/{review_id}/vote        # Vote helpful/not-helpful (auth)
POST   /api/v1/reviews/{review_id}/respond     # Owner/admin response
DELETE /api/v1/reviews/{review_id}             # Delete review (author/admin)

# Live Posts
POST   /api/v1/live/posts                      # Create live post (auth, with photo upload)
GET    /api/v1/live/posts                      # List live posts (filters)
GET    /api/v1/live/posts/{post_id}            # Single live post
DELETE /api/v1/live/posts/{post_id}            # Delete (author/admin)

# Users
GET    /api/v1/users/me                        # Current user profile
PUT    /api/v1/users/me                        # Update profile
PUT    /api/v1/users/me/role                   # Switch role
PUT    /api/v1/users/me/profile                # Update provider profile
GET    /api/v1/users/providers                 # List providers (role=guide/agency/hotel)
GET    /api/v1/users/providers/{user_id}       # Single provider detail

# Events (read-only calendar)
GET    /api/v1/events                          # List events (filters: wilaya, category, month)
GET    /api/v1/events/{event_id}               # Event detail

# Discussions (Phase D — Q&A per POI/experience/stay)
POST   /api/v1/discussions                     # Create discussion thread (auth)
GET    /api/v1/discussions                     # List threads for entity (?entity_type=&entity_id=)
GET    /api/v1/discussions/{thread_id}         # Thread detail with all posts
POST   /api/v1/discussions/{thread_id}/posts   # Reply to thread (auth)
DELETE /api/v1/discussions/{thread_id}         # Delete thread (author/admin)
DELETE /api/v1/discussions/posts/{post_id}     # Delete post (author/admin)

# Price Calendar (Phase D — per-date pricing for experiences)
GET    /api/v1/price-calendar/experiences/{experience_id}  # Calendar with min/max/available dates
POST   /api/v1/price-calendar/experiences/{experience_id}  # Batch set prices (provider only)
DELETE /api/v1/price-calendar/{price_id}                   # Delete price entry (provider/admin)

# POIs (with neighborhood browsing)
GET    /api/v1/pois/neighborhoods               # List distinct neighborhoods (?wilaya_id=)
POST   /api/v1/pois                            # Create POI (auth)
GET    /api/v1/pois                            # List POIs (filters: wilaya, category, neighborhood, search, sort)
GET    /api/v1/pois/search                     # Semantic search via Qdrant
GET    /api/v1/pois/{poi_id}                   # POI detail
POST   /api/v1/pois/{poi_id}/photo             # Upload POI photo (admin)
DELETE /api/v1/pois/{poi_id}                   # Delete POI (admin)

# Experiences
POST   /api/v1/experiences                     # Create experience (auth, provider role)
GET    /api/v1/experiences                     # List experiences (filters: wilaya, category, season, provider, status)
GET    /api/v1/experiences/search              # Semantic search via Qdrant
GET    /api/v1/experiences/{experience_id}     # Experience detail
PUT    /api/v1/experiences/{experience_id}     # Update (author only)
DELETE /api/v1/experiences/{experience_id}     # Delete (author/admin)
POST   /api/v1/experiences/{experience_id}/photos  # Upload photos (author)

# Stays
POST   /api/v1/stays                           # Create stay (auth, hotel/agency/admin role)
GET    /api/v1/stays                           # List stays (filters: wilaya, type, price range)
GET    /api/v1/stays/{stay_id}                 # Stay detail
PUT    /api/v1/stays/{stay_id}                 # Update (author only)
DELETE /api/v1/stays/{stay_id}                 # Delete (author/admin)

# Transport Network
GET    /api/v1/transport/routes/{origin_wilaya_id}/{dest_wilaya_id}  # Inter-city routes
GET    /api/v1/transport/routes/from/{origin_wilaya_id}              # All routes from wilaya
GET    /api/v1/transport/stations              # List all stations
GET    /api/v1/transport/stations/nearby       # Nearby stations (lat/lng/radius)
GET    /api/v1/transport/lines                 # List transport lines
GET    /api/v1/transport/plan                  # Route planner (origin,dest,time)
GET    /api/v1/transport/access/{poi_id}       # Transit access info for a POI

# Bookings
POST   /api/v1/bookings                        # Create booking request
GET    /api/v1/bookings                        # List my bookings
GET    /api/v1/bookings/{booking_id}           # Booking detail
PUT    /api/v1/bookings/{booking_id}/status    # Confirm/cancel

# Notifications
GET    /api/v1/notifications                   # List notifications
PUT    /api/v1/notifications/{id}/read         # Mark read
PUT    /api/v1/notifications/read-all          # Mark all read

# Trips (Trip Dashboard)
POST   /api/v1/trips                           # Create trip (auth)
GET    /api/v1/trips                           # List my trips
GET    /api/v1/trips/{trip_id}                 # Trip detail
PUT    /api/v1/trips/{trip_id}                 # Update trip
DELETE /api/v1/trips/{trip_id}                 # Delete trip
POST   /api/v1/trips/{trip_id}/items           # Add item
DELETE /api/v1/trips/{trip_id}/items/{item_id} # Remove item
PUT    /api/v1/trips/{trip_id}/items/{item_id} # Reorder / change day
POST   /api/v1/trips/{trip_id}/optimize        # Route optimization
GET    /api/v1/trips/brief/{wilaya_id}         # Generate wilaya trip brief
POST   /api/v1/trips/{trip_id}/optimize/send-whatsapp  # Send brief via WhatsApp

# Circuits (pre-seeded itineraries)
GET    /api/v1/circuits                        # List circuits (filters)
GET    /api/v1/circuits/{circuit_id}           # Circuit detail with all items

# Discover
GET    /api/v1/discover/wilayas                 # List all wilayas with summary stats (counts, highlight POI)
GET    /api/v1/discover/wilayas/{wilaya_id}    # Consolidated view (all POIs + experiences + stays)
GET    /api/v1/discover/wilayas/{wilaya_id}/guide  # Curated guide: POIs sorted by combined score, capped top N per category
GET    /api/v1/discover/experiences/by-poi/{poi_id}  # Find experiences matching a POI

# Admin Dashboard 🔐
GET    /api/v1/admin/price-reports             # List reports (filter: verified)
PUT    /api/v1/admin/price-reports/{id}/verify # Verify report
DELETE /api/v1/admin/price-reports/{id}        # Reject & delete report
GET    /api/v1/admin/users                     # List users (filter: role, verified)
PUT    /api/v1/admin/users/{id}/role           # Change user role
PUT    /api/v1/admin/users/{id}/verify         # Toggle user verified
GET    /api/v1/admin/providers                 # List provider profiles
PUT    /api/v1/admin/providers/{id}/approve    # Approve provider
DELETE /api/v1/admin/reviews/{id}              # Delete any review
DELETE /api/v1/admin/live-posts/{id}           # Delete any live post
PUT    /api/v1/admin/live-posts/{id}/moderate  # Mark post as moderated
DELETE /api/v1/admin/experiences/{id}          # Delete any experience

# Legacy (guarded)
POST   /api/v1/visa/process-passport           # Admin visa checker
POST   /api/v1/whatsapp/webhook                # WhatsApp bot stub
POST   /api/v1/studio/refine-video             # Studio media
```

## Naming Conventions

- **Plural nouns** for collections: `/pois`, `/reviews`, `/bookings`
- **Snake case** for query params: `?wilaya_id=`, `?page_size=`
- **Status sub-resource**: `PUT /bookings/{id}/status` for state transitions
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
  "message": "Booking not found",
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

1. **TrustedHostMiddleware** — validates `Host` header against `allowed_hosts`
2. **SecurityHeadersMiddleware** — adds `X-Content-Type-Options`, `X-Frame-Options`, etc.
3. **CORS** (`CORSMiddleware`) — explicit origins (not `*`)
4. **LocaleMiddleware** — detects `Accept-Language` or `?lang=`, stores in `request.state.locale`
5. **ErrorMiddleware** — catches `AppError` → JSON, unhandled → 500 with sanitized stack trace
6. **Rate limiter** — slowapi with Redis backend (in-memory fallback)

## Request Flow

```
Request → TrustedHost → SecurityHeaders → CORS → LocaleMiddleware → ErrorMiddleware → Limiter → Router → Endpoint
                                                                                                                         │
                                                                                                                  get_db() → async session
                                                                                                                  get_current_user() → JWT decode → DB fetch
                                                                                                                  business logic → DB queries
                                                                                                                  response → Pydantic validation → JSON
```

## Review System (Phase C — TripAdvisor-style)

### Schema

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "user_name": "Karim Bensalem",
  "poi_id": "uuid",
  "overall_score": 4.5,
  "text": "Fascinating piece of history...",
  "is_verified": true,
  "sub_ratings": {
    "preservation": 4.5,
    "information": 4.0,
    "atmosphere": 5.0,
    "value": 4.0
  },
  "helpfulness_count": 12,
  "owner_response": "Thank you for visiting!",
  "response_created_at": "2026-07-14T...",
  "edited_at": null,
  "created_at": "2026-07-10T..."
}
```

`sub_ratings` varies by POI category:
- **Restaurant:** `food_quality`, `service`, `ambiance`, `value`
- **Museum/Historical:** `exhibits`, `layout`, `information`, `value`
- **Natural/Beach/Mountain:** `scenery`, `accessibility`, `cleanliness`, `value`
- **Cultural/Market:** `authenticity`, `experience`, `value`, `accessibility`
- **Hotel/Stay:** `cleanliness`, `location`, `value`, `service`

### Helpfulness Voting

```
POST /api/v1/reviews/{review_id}/vote
Body: {"helpful": true}   # or false
```

Users cannot vote on their own reviews. One vote per user per review (can toggle).

### Owner Response

```
POST /api/v1/reviews/{review_id}/respond
Body: {"response": "Thank you for your feedback!"}
```

Admin-only (future: POI operator / stay owner).

### Sort Options

`GET /api/v1/reviews?poi_id=...&sort=recent|highest|lowest|helpful`

- `recent` (default) — newest first
- `highest` — best rated first
- `lowest` — worst rated first
- `helpful` — most helpfulness votes first

### POI Detail with Top Reviews

`GET /api/v1/pois/{id}` response includes:

```json
{
  "average_score": 4.3,
  "total_reviews": 8,
  "top_reviews": [
    {
      "id": "...",
      "user_name": "Karim Bensalem",
      "overall_score": 5.0,
      "text": "Absolutely stunning!",
      "created_at": "...",
      "helpfulness_count": 4
    }
  ]
}
```

Top 3 most helpful reviews per POI, shown inline like TripAdvisor's "What people are saying".

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
      "category": "historical",
      "average_score": 4.5,
      "total_reviews": 12
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
  ]
}
```

### Wilaya Travel Guide

`GET /api/v1/discover/wilayas/{wilaya_id}/guide?top=10` returns curated per-wilaya guide:

- POIs sorted by combined score (`accessibility_score × 0.4 + category_weight × 0.3 + featured_bonus × 0.3`)
- Capped at top N per category (11 categories)
- Includes transport access info (`getting_there`), featured status, experiences, stays
- Category weights: museum=100, cultural=90, historical=85, natural=80, beach=75, park=70, mountain=65, market=60, religious=55, restaurant=50, cafe=40, other=30

### POI-to-Experience Linking

`GET /api/v1/discover/experiences/by-poi/{poi_id}` finds experiences in the same wilaya that match the POI by title/description keyword overlap.

## Trip Item Types

Trip items are polymorphic with no FK constraints:

| `item_type` | Description | Enrichment in TripOptimizer |
|------------|-------------|----------------------------|
| `poi` | Points of interest | Duration: 120 min default |
| `experience` | Bookable tours/activities | Duration: from DB |
| `stay` | Accommodation | Duration: 720 min (overnight) |
| `restaurant` | Dining | Duration: 90 min |
| `transport` | Transfers between locations | Duration: 60 min |

## Stay Model

Stays represent bookable accommodations with:

- **Property types:** `hotel`, `riad`, `guesthouse`, `hostel`, `eco_lodge`, `apartment`
- **Amenities:** JSON array of strings (e.g., `["wifi", "parking", "breakfast"]`)
- **Location:** Wilaya FK + address + lat/lng
- **Capacity:** `max_guests` + `total_rooms`
- **Pricing:** `price_per_night_dzd` in DZD
- **Photos:** MinIO URLs array
- **Availability:** `is_active` flag

## Security

- **JWT EdDSA (Ed25519)** — asymmetric keys, aud/iss validation
- **Rate limiting** — 10/min for OTP, 20/min for general endpoints
- **CSRF protection** — not needed (API uses Bearer tokens, not cookies)
- **Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`
- **Host validation** — TrustedHostMiddleware with configurable `allowed_hosts`
- **CORS** — explicit origin allowlist, credentials enabled
- **Container security** — non-root user, `cap_drop: ALL`, `no-new-privileges`, read-only root
- **Docker secrets** — sensitive config passed via `/run/secrets/`

## Legacy Routes (guarded)

```
POST /api/v1/visa/process-passport    # Admin visa checker
POST /api/v1/whatsapp/webhook          # WhatsApp bot stub
POST /api/v1/studio/refine-video       # Studio media
```

These are wrapped in `try/except` in `main.py` — if their dependencies (Whisper, OpenCV, Qdrant) aren't installed, they silently fail to load instead of crashing the app.
