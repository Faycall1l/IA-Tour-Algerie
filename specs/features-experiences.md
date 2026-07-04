# Feature: Experiences Marketplace

## Overview

Experiences are bookable activities offered by providers (guides, agencies, hotels). Unlike POIs (which are fixed locations anyone can submit), experiences are commercial listings managed by verified providers.

## Experience Types

| Type | Example |
|------|---------|
| `tour` | Guided day trip through Casbah |
| `workshop` | Pottery-making class |
| `homestay` | Overnight with a local family |
| `hiking` | Djurdjura mountain trek |
| `cultural` | Traditional music evening |
| `food` | Couscous cooking class |
| `adventure` | Paragliding in Tipaza |
| `wellness` | Hammam + massage |

## CRUD Endpoints

### Creation — `POST /api/v1/experiences`

Auth required. User must have a provider role (`guide`, `agency`, or `hotel`).

```json
{
  "title": "Casbah Walking Tour",
  "description": "Explore the historic Casbah with a local guide...",
  "type": "tour",
  "wilaya_id": 16,
  "price": 2500,
  "duration": "3 hours",
  "max_participants": 8,
  "includes": "Guide, bottled water, traditional pastry tasting",
  "meets_at": "Place des Martyrs, Algiers"
}
```

### Listing — `GET /api/v1/experiences`

| Param | Values |
|-------|--------|
| `type` | `tour`, `workshop`, ... |
| `wilaya_id` | 1–58 |
| `min_price` / `max_price` | Integer (DZD) |
| `provider_id` | UUID |
| `sort` | `created_at`, `price`, `title` |
| `order` | `asc`, `desc` |
| `page` / `page_size` | Pagination |

### Search — `GET /api/v1/experiences/search?q=cooking+class`

Falls through Qdrant vector search. If Qdrant is down, falls back to SQL `ILIKE` on title.

### Detail — `GET /api/v1/experiences/{id}`

Returns full detail with provider info (name, avatar, rating).

```json
{
  "id": "uuid",
  "title": "Casbah Walking Tour",
  "description": "...",
  "type": "tour",
  "price": 2500,
  "duration": "3 hours",
  "max_participants": 8,
  "images": ["http://minio:9000/athar-media/experiences/img1.jpg"],
  "status": "active",
  "provider": {
    "id": "uuid",
    "display_name": "Amazigh Tours",
    "avatar_url": "..."
  }
}
```

### Update — `PUT /api/v1/experiences/{id}`

Only the author (provider who created it) can update. Admin cannot (unless they own the resource).

### Delete — `DELETE /api/v1/experiences/{id}`

Author or admin can delete. Also removes from Qdrant index.

### Photos — `POST /api/v1/experiences/{id}/photos`

Multipart upload. Appends to the `photos` array field (stored as ARRAY(String) in Postgres). Uploaded to MinIO under `experiences/` prefix.

## Provider Requirements

To create an experience, a user must have set their role to one of:
- `guide`
- `agency`
- `hotel`

These roles are settable via `PUT /api/v1/users/me/role`. Travelers cannot create experiences.

## Provider Profiles

`PUT /api/v1/users/me/profile` — creates or updates `ProviderProfile`:

```json
{
  "service_type": "guide",
  "business_name": "Amazigh Tours Algérie",
  "description": "Certified guide with 10 years of experience...",
  "years_experience": 10,
  "license_number": "G-2024-0042",
  "languages": ["AR", "FR", "EN", "TZ"],
  "service_area": "Kabylie, Algiers",
  "website": "https://amazigh-tours.dz",
  "social_links": {"instagram": "@amazigh_tours"}
}
```

### Provider Listing — `GET /api/v1/users/providers`

Public endpoint. Lists users with `role IN (guide, agency, hotel)` who have a `ProviderProfile`. Filters by `service_type`, `wilaya_id`, search.

### Single Provider — `GET /api/v1/users/providers/{user_id}`

Returns user info + full profile + their active experiences.

## Data Model

```python
class ProviderProfile(Base):
    user_id: UUID  # FK → users, unique
    service_type: str  # guide | agency | hotel
    business_name: str | None
    description: str | None
    years_experience: int | None
    license_number: str | None
    languages: list[str]
    service_area: str | None
    website: str | None
    social_links: dict | None
```

One profile per user. Optional fields depend on service_type but stored in one table for simplicity.

## Future

- **Availability calendar** — providers set available dates/times.
- **Instant booking** vs request-to-book toggle.
- **Reviews for providers** (separate from POI reviews).
- **Payout system** — track earnings per provider.
