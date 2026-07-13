# API Layer

## Route Inventory (~88 routes)

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
POST   /api/v1/pois                            # Create POI (auth)
GET    /api/v1/pois                            # List POIs (filters, sort)
GET    /api/v1/pois/search                     # Semantic search via Qdrant
GET    /api/v1/pois/{poi_id}                   # POI detail with average_score + total_reviews
POST   /api/v1/pois/{poi_id}/photo             # Upload POI photo (admin)
DELETE /api/v1/pois/{poi_id}                   # Delete POI (admin)

# Price Reports
POST   /api/v1/prices                          # Create price report (auth)
GET    /api/v1/prices                          # List price reports
GET    /api/v1/prices/estimate                 # Fair price engine

# Reviews
POST   /api/v1/reviews                         # Create review (auth, one per user per POI)
GET    /api/v1/reviews                         # List reviews
GET    /api/v1/reviews/ratings/{poi_id}        # Rating distribution
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

# Experiences
POST   /api/v1/experiences                     # Create experience (auth, provider role)
GET    /api/v1/experiences                     # List experiences (filters, sort)
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
GET    /api/v1/discover/wilayas/{wilaya_id}/guide  # **Curated guide**: POIs sorted by combined score (accessibility × category × featured), capped top N per category, includes transport access info
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
| `page_size` | 20 | 50 (100 for POIs) |

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
5. **Prometheus** (`prometheus-fastapi-instrumentator`) — metrics at `/metrics`
6. **ErrorMiddleware** — catches `AppError` → JSON, unhandled → 500 with sanitized stack trace
7. **Rate limiter** — slowapi with Redis backend (in-memory fallback)

## Request Flow

```
Request → TrustedHost → SecurityHeaders → CORS → LocaleMiddleware → Prometheus → ErrorMiddleware → Limiter → Router → Endpoint
                                                                                                                         │
                                                                                                                  get_db() → async session
                                                                                                                  get_current_user() → JWT decode → DB fetch
                                                                                                                  business logic → DB queries
                                                                                                                  response → Pydantic validation → JSON
```

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
      "category": "landmark",
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
