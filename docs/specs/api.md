# API Layer

## Route Inventory (106 operations, 81 paths)

```
# Public
GET    /api/v1/health                          # Health check

# Auth
POST   /api/v1/auth/send-otp                   # Passwordless OTP
POST   /api/v1/auth/verify-otp                 # Login
POST   /api/v1/auth/refresh                    # Rotate tokens
POST   /api/v1/auth/register-provider          # Register as provider

# Wilayas
GET    /api/v1/wilayas                         # List 69 wilayas
GET    /api/v1/wilayas/{wilaya_id}             # Single wilaya

# POIs
GET    /api/v1/pois/neighborhoods              # List distinct neighborhoods (?wilaya_id=)
POST   /api/v1/pois                            # Create POI (auth)
GET    /api/v1/pois                            # List POIs (filters: wilaya, category, neighborhood, search, sort)
GET    /api/v1/pois/search                     # Semantic search via Qdrant
GET    /api/v1/pois/nearby                     # Nearby POIs (?lat=&lng=&radius_km=)
GET    /api/v1/pois/{poi_id}                   # POI detail
PATCH  /api/v1/pois/{poi_id}                   # Partial update POI (admin)
POST   /api/v1/pois/{poi_id}/photo             # Upload POI photo (admin)
DELETE /api/v1/pois/{poi_id}                   # Delete POI (admin)
GET    /api/v1/pois/{poi_id}/similar           # Similar POIs

# POI Tour Optimization
GET    /api/v1/pois/tour/optimize              # Optimize walking tour
GET    /api/v1/pois/tour/clusters              # Density-based clusters
GET    /api/v1/pois/tour/hubs                  # Transit hub POIs

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
GET    /api/v1/transport/operators             # Transport operators with contacts
GET    /api/v1/transport/plan                  # Route planner (origin,dest,time)
GET    /api/v1/transport/access/{poi_id}       # Transit access info for a POI

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
POST   /api/v1/trips/{trip_id}/share           # Generate share link
GET    /api/v1/trips/shared/{share_token}      # View shared trip

# Events (read-only calendar)
GET    /api/v1/events                          # List events (filters: wilaya, category, month)
POST   /api/v1/events                          # Create event (auth, admin)
GET    /api/v1/events/{event_id}               # Event detail
PATCH  /api/v1/events/{event_id}               # Update event (admin)
DELETE /api/v1/events/{event_id}               # Delete event (admin)

# Artisans
POST   /api/v1/artisans                        # Create artisan (auth)
GET    /api/v1/artisans                        # List artisans (filters: wilaya, craft)
GET    /api/v1/artisans/{artisan_id}           # Artisan detail
PUT    /api/v1/artisans/{artisan_id}           # Update artisan (owner)
DELETE /api/v1/artisans/{artisan_id}           # Delete artisan (owner/admin)

# Search (Full-Text)
GET    /api/v1/search                          # Unified search across POIs, stays, experiences (?q=)
GET    /api/v1/search/suggest                  # Search suggestions/autocomplete

# GeoJSON (spatial data)
GET    /api/v1/pois.geojson                    # All POIs as GeoJSON FeatureCollection (filters)
GET    /api/v1/stays.geojson                   # All stays as GeoJSON
GET    /api/v1/experiences.geojson             # All experiences as GeoJSON
GET    /api/v1/nearby/pois                     # POIs near location (?lat=&lng=&radius_km=)

# Collections (wishlists)
GET    /api/v1/collections                     # List user's collections
POST   /api/v1/collections                     # Create collection
GET    /api/v1/collections/{id}                # Collection with all items
PUT    /api/v1/collections/{id}                # Update name/description/is_public
DELETE /api/v1/collections/{id}                # Delete collection + items
POST   /api/v1/collections/{id}/items          # Batch add items (deduplicates)
DELETE /api/v1/collections/{id}/items/{item_id} # Remove single item

# Favorites
GET    /api/v1/favorites                       # List favorites (auth)
POST   /api/v1/favorites                       # Add favorite (auth)
DELETE /api/v1/favorites/{id}                  # Remove favorite (auth)

# Recommendations (Personalized)
GET    /api/v1/recommendations                 # Get ranked recs (?wilaya_id=&entity_type=&limit=)
GET    /api/v1/recommendations/preferences     # Get user preferences
PATCH  /api/v1/recommendations/preferences     # Update preferences
POST   /api/v1/recommendations/preferences/derive  # Re-derive from interactions
POST   /api/v1/recommendations/{rec_id}/feedback    # Feedback (liked/dismissed/bookmarked)

# Users
GET    /api/v1/users/me                        # Current user profile
PUT    /api/v1/users/me                        # Update profile
PUT    /api/v1/users/me/role                   # Switch role
PUT    /api/v1/users/me/profile                # Update provider profile
GET    /api/v1/users/me/dashboard              # User dashboard stats
GET    /api/v1/users/providers                 # List providers (role=guide/agency/hotel)
GET    /api/v1/users/providers/{user_id}       # Single provider detail

# AI Agents
POST   /api/v1/agent/chat                      # Travel assistant (20/h, asks about Algeria travel)
POST   /api/v1/agent/plan-trip                 # Itinerary planner (10/h, returns structured TripPlan)
POST   /api/v1/agent/search                    # Unified search via agent (30/h)

# Discover
GET    /api/v1/discover/wilayas                # List all wilayas with summary stats (counts, highlight POI)
GET    /api/v1/discover/wilayas/{wilaya_id}    # Consolidated view (all POIs + experiences + stays)
GET    /api/v1/discover/wilayas/{wilaya_id}/guide  # Curated guide: POIs sorted by combined score, capped top N per category
GET    /api/v1/discover/experiences/by-poi/{poi_id}  # Find experiences matching a POI

# Admin
GET    /api/v1/admin/stats                     # Dashboard stats (counts, recent)
GET    /api/v1/admin/verify/stats              # POI verification stats
GET    /api/v1/admin/verify/poi/{poi_id}       # POI verification detail
GET    /api/v1/admin/users                     # List users (filter: role, verified)
PUT    /api/v1/admin/users/{id}/role           # Change user role
PUT    /api/v1/admin/users/{id}/verify         # Toggle user verified
GET    /api/v1/admin/providers                 # List provider profiles
PUT    /api/v1/admin/providers/{id}/approve    # Approve provider
DELETE /api/v1/admin/experiences/{id}          # Delete any experience
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
  ]
}
```

### Wilaya Travel Guide

`GET /api/v1/discover/wilayas/{wilaya_id}/guide?top=10` returns curated per-wilaya guide:

- POIs sorted by combined score (`accessibility_score × 0.4 + category_weight × 0.3 + featured_bonus × 0.3`)
- Capped at top N per category (11 categories)
- Includes transport access info (`getting_there`), featured status, experiences, stays

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

## Security

- **JWT EdDSA (Ed25519)** — asymmetric keys, aud/iss validation
- **Rate limiting** — 10/min for OTP, 20/min for general endpoints, 20/h agent chat, 10/h plan-trip, 30/h agent search
- **CSRF protection** — not needed (API uses Bearer tokens, not cookies)
- **Security headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 0`
- **Host validation** — TrustedHostMiddleware with configurable `allowed_hosts`
- **CORS** — explicit origin allowlist, credentials enabled
