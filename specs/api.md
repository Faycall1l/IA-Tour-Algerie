# API Layer

## Route Inventory (45+ routes)

```
GET    /health                              # Health check
POST   /api/v1/auth/send-otp                # Passwordless OTP
POST   /api/v1/auth/verify-otp              # Login
POST   /api/v1/auth/refresh                 # Rotate tokens
GET    /api/v1/wilayas                      # List 58 wilayas
GET    /api/v1/wilayas/{wilaya_id}          # Single wilaya
POST   /api/v1/pois                         # Create POI (auth)
GET    /api/v1/pois                         # List POIs (filters, sort, search via Qdrant)
GET    /api/v1/pois/{poi_id}                # POI detail with average_score + total_reviews
DELETE /api/v1/pois/{poi_id}                # Delete POI (admin)
POST   /api/v1/pois/{poi_id}/photo          # Upload POI photo (admin)
POST   /api/v1/prices                       # Create price report (auth)
GET    /api/v1/prices                       # List price reports
GET    /api/v1/prices/estimate              # Fair price engine
POST   /api/v1/reviews                      # Create review (auth, one per user per POI)
GET    /api/v1/reviews                      # List reviews
GET    /api/v1/reviews/ratings/{poi_id}     # Rating distribution
DELETE /api/v1/reviews/{review_id}          # Delete review (author/admin)
POST   /api/v1/live/posts                   # Create live post (auth, with photo upload)
GET    /api/v1/live/posts                   # List live posts (filters)
GET    /api/v1/live/posts/{post_id}         # Single live post
DELETE /api/v1/live/posts/{post_id}         # Delete (author/admin)
GET    /api/v1/users/me                     # Current user profile
PUT    /api/v1/users/me                     # Update profile
PUT    /api/v1/users/me/role                # Switch role
PUT    /api/v1/users/me/profile             # Update provider profile
GET    /api/v1/users/providers              # List providers (role=guide/agency/hotel)
GET    /api/v1/users/providers/{user_id}    # Single provider detail
POST   /api/v1/experiences                  # Create experience (auth, provider role)
GET    /api/v1/experiences                  # List experiences (filters, sort)
GET    /api/v1/experiences/search           # Semantic search via Qdrant
GET    /api/v1/experiences/{exp_id}         # Experience detail
PUT    /api/v1/experiences/{exp_id}         # Update (author only)
DELETE /api/v1/experiences/{exp_id}         # Delete (author/admin)
POST   /api/v1/experiences/{exp_id}/photos  # Upload photos (author)
POST   /api/v1/bookings                     # Create booking request
GET    /api/v1/bookings                     # List my bookings
GET    /api/v1/bookings/{booking_id}        # Booking detail
PUT    /api/v1/bookings/{booking_id}/status  # Confirm/cancel
GET    /api/v1/notifications                # List notifications
PUT    /api/v1/notifications/{id}/read      # Mark read
PUT    /api/v1/notifications/read-all       # Mark all read
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

1. **CORS** (`CORSMiddleware`) — allows all origins in dev
2. **LocaleMiddleware** — detects `Accept-Language` or `?lang=`, stores in `request.state.locale`
3. **Prometheus** (`prometheus-fastapi-instrumentator`) — metrics at `/metrics`
4. **Exception handlers** — `AppError` → JSON, unhandled → 500 with stack trace

## Request Flow

```
Request → CORS → LocaleMiddleware → Router → Endpoint
                                                 │
                                          get_db() → async session
                                          get_current_user() → JWT decode → DB fetch
                                          business logic → DB queries
                                          response → Pydantic validation → JSON
```

## Legacy Routes (guarded)

```
GET /api/v1/visa/{...}        # Admin visa checker
POST /api/v1/whatsapp/{...}    # WhatsApp bot stub
POST /api/v1/studio/{...}      # Studio media
```

These are wrapped in `try/except` in `main.py` — if their dependencies (Whisper, OpenCV, Qdrant) aren't installed, they silently fail to load instead of crashing the app.
