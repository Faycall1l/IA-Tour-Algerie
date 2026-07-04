# Database

## Stack
- **PostgreSQL 16.4** via asyncpg
- **SQLAlchemy 2.0.38** async ORM with `async_sessionmaker` (greenlet via `[asyncio]` extra)
- **Alembic 1.15** async migration runner
- Connection pool: 10 persistent + 5 overflow, 30s timeout, SSL support

## Connection Pool Configuration

```python
engine = create_async_engine(
    settings.database.url,
    pool_size=10,               # Persistent connections
    max_overflow=5,             # Burst connections under load
    pool_pre_ping=True,         # Check health before checkout
    pool_recycle=1800,          # Reconnect after 30 min (handles server-side timeout)
    pool_timeout=30,            # Wait max 30s for a connection
    echo=settings.debug,        # Log all queries in dev only
    connect_args={"ssl": "require"} if sslmode=require in URL else None,
)
```

**Security**:
- Pool size reduced from 20→10 to avoid `TooManyConnectionsError` with multiple workers.
- `pool_timeout=30` prevents infinite waits under load.
- SSL support via `?sslmode=require` in connection URL → `connect_args["ssl"]` activates.

## Models (13 total)

### User (`users`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK, default uuid4 |
| phone | String(20) | Unique, indexed |
| display_name | String(100) | Nullable |
| avatar_url | String(500) | Nullable, MinIO URL |
| role | String(20) | `traveler` \| `guide` \| `agency` \| `hotel` \| `admin`, default `traveler`, CHECK constraint |
| is_active | Boolean | Default true |
| is_verified | Boolean | Default false, admin action |
| language | String(5) | Default 'fr' |
| languages | ARRAY(String) | E.g. `{AR,FR,EN}` |
| bio | String(1000) | Nullable |
| created_at | DateTime(tz) | server_default now() |
| updated_at | DateTime(tz) | onupdate now() |

### RefreshToken (`refresh_tokens`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| token_hash | String(128) | SHA-256 of token |
| family | String(36) | UUID grouping tokens for rotation |
| is_revoked | Boolean | Default false |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Wilaya (`wilayas`)
58 pre-seeded rows with AR/FR/EN names + lat/lng.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK |
| name_ar | String(100) | |
| name_fr | String(100) | |
| name_en | String(100) | |
| latitude | Float | |
| longitude | Float | |
| created_at | DateTime(tz) | |

### POI (`pois`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(200) | |
| description | Text | |
| category | String(20) | CHECK: `historical`, `natural`, `cultural`, `religious`, `museum`, `beach`, `mountain`, `park`, `market`, `other` |
| wilaya_id | Integer | FK → wilayas.id |
| latitude | Float | |
| longitude | Float | |
| image_url | String(500) | Nullable |
| submitted_by | UUID | FK → users.id |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### PriceReport (`price_reports`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| poi_id | UUID | FK → pois.id |
| transport_mode | String(10) | CHECK: `taxi`, `bus`, `train`, `walk`, `car`, `plane` |
| amount | Integer | In DZD |
| submitted_by | UUID | FK → users.id |
| is_verified | Boolean | Default false |
| created_at | DateTime(tz) | |

### Review (`reviews`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| poi_id | UUID | FK → pois.id |
| user_id | UUID | FK → users.id, **unique per poi_id** |
| rating | Integer | 1–5, CHECK |
| comment | Text | Nullable |
| created_at | DateTime(tz) | |

### LivePost (`live_posts`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| caption | String(500) | |
| image_url | String(500) | Nullable |
| wilaya_id | Integer | FK → wilayas.id |
| created_at | DateTime(tz) | |

### Experience (`experiences`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider_id | UUID | FK → users.id |
| title | String(200) | |
| category | String(50) | CHECK: `tour`, `workshop`, `homestay`, `hiking`, `cultural`, `food`, `adventure`, `wellness`, `other` |
| description | Text | Nullable |
| wilaya_id | Integer | FK → wilayas.id |
| meeting_point | String(500) | Nullable |
| meeting_point_lat | Float | Nullable |
| meeting_point_lng | Float | Nullable |
| price_dzd | Float | Nullable |
| duration_hours | Float | Nullable |
| max_participants | Integer | Nullable |
| language | String(5) | Nullable |
| included | ARRAY(String) | Nullable |
| what_to_bring | ARRAY(String) | Nullable |
| photos | ARRAY(String) | MinIO URLs |
| status | String(20) | Default `draft`, CHECK: `draft`, `active`, `cancelled` |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### ProviderProfile (`provider_profiles`)
One-to-one with User.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, unique |
| service_type | String(20) | `guide`, `agency`, `hotel` |
| business_name | String(200) | Nullable |
| description | Text | Nullable |
| years_experience | Integer | Nullable |
| license_number | String(100) | Nullable |
| languages | ARRAY(String) | |
| service_area | String(300) | Nullable |
| website | String(500) | Nullable |
| social_links | JSON | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Booking (`bookings`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| traveler_id | UUID | FK → users.id |
| experience_id | UUID | FK → experiences.id |
| status | String(20) | `pending` \| `confirmed` \| `completed` \| `cancelled`, CHECK, default `pending` |
| message | Text | Nullable, traveler's request message |
| participants | Integer | Default 1 |
| requested_date | Date | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Notification (`notifications`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id |
| type | String(50) | E.g. `booking_request`, `booking_confirmed`, `booking_cancelled` |
| title | String(200) | |
| message | Text | Nullable |
| reference_type | String(50) | E.g. `booking` |
| reference_id | UUID | Nullable, FK target |
| is_read | Boolean | Default false |
| created_at | DateTime(tz) | |

## Constraints at DB Level
- **CHECK constraints** on `role`, `category`, `transport_mode`, `rating`, `status` — data integrity enforced regardless of client.
- **UNIQUE(user_id, poi_id)** on reviews — one review per user per POI.
- **FK CASCADE** on all user/POI/experience references.

## Alembic Migrations

| # | Name | Changes |
|---|------|---------|
| 001 | Initial schema | users, refresh_tokens, reviews, pois, live_posts, price_reports |
| 002 | Seed wilayas | wilayas table + 58 rows |
| 003 | Price constraints | CHECK on transport_mode |
| 004 | POI constraints | CHECK on category |
| 005 | Review constraints | UNIQUE(user_id, poi_id) |
| 006 | User roles + providers | Role field, ProviderProfile table |
| 007 | Experiences | Experiences table + CHECK constraints |
| 008 | Bookings + Notifications | Bookings + Notifications tables |
