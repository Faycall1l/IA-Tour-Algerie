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

## Models (20 SQLAlchemy ORM models across 16 files)

### User (`users`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| phone | String(20) | Unique, indexed |
| display_name | String(100) | Nullable |
| avatar_url | String(500) | Nullable |
| role | String(20) | `traveler` \| `guide` \| `agency` \| `hotel` \| `admin`, default `traveler`, CHECK |
| is_active | Boolean | Default true |
| is_verified | Boolean | Default false |
| language | String(5) | Default 'fr' |
| languages | ARRAY(String) | Nullable |
| bio | String(1000) | Nullable |
| created_at | DateTime(tz) | server_default now() |
| updated_at | DateTime(tz) | onupdate now() |

### RefreshToken (`refresh_tokens`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| token_hash | String(128) | SHA-256 of token |
| family | String(36) | UUID rotation group |
| is_revoked | Boolean | Default false |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Wilaya (`wilayas`)
69 rows seeded with AR/FR/EN names + lat/lng + descriptions.

| Column | Type | Notes |
|--------|------|-------|
| id | Integer | PK |
| name_ar | String(100) | |
| name_fr | String(100) | |
| name_en | String(100) | |
| latitude | Float | |
| longitude | Float | |
| description | Text | Nullable, French destination description |
| description_en | Text | Nullable, English destination description |
| created_at | DateTime(tz) | |

### POI (`pois`)
52,997 rows from OSM + GeoAlgeria enrichment.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(200) | |
| name_ar | String(200) | Arabic name |
| name_en | String(200) | English name |
| category | String(50) | CHECK: `historical`, `natural`, `cultural`, `religious`, `museum`, `beach`, `mountain`, `park`, `market`, `restaurant`, `cafe`, `other` |
| subtype | String(100) | E.g. `thermal_spring`, `national_park`, `amphitheatre` |
| wilaya_id | Integer | FK → wilayas.id, indexed |
| commune | String(200) | Commune name |
| latitude | Float | |
| longitude | Float | |
| description | Text | |
| photo_url | Text | |
| photo_urls | ARRAY(String) | Array of Wikimedia/MinIO URLs |
| entry_fee_dzd | Float | Estimated entry price |
| price_level | String(10) | Free/$/$$/$$$ |
| website | String(300) | |
| phone | String(50) | |
| opening_hours | String(200) | |
| operator | String(200) | POI operator |
| cuisine | String(200) | For restaurant POIs |
| has_parking | Boolean | |
| has_accessibility | Boolean | Wheelchair access |
| historic_civilization | String(100) | Roman, Ottoman, etc. |
| osm_node_id | BigInt | OSM node ID |
| osm_type | String(20) | `node` or `way` |
| osm_tags | JSONB | Raw OSM tags |
| thermal_data | JSONB | Temperature, debit, minerality (for thermal springs) |
| is_featured | Boolean | Default false |
| featured_order | Integer | Ranking for featured POIs |
| ranking_position | Integer | Nullable, per-wilaya×category ranking |
| ranking_total | Integer | Nullable |
| suggested_duration_min | Integer | Per-category default (30min–4h) |
| neighborhood | String(200) | District/quarter |
| award | String(200) | |
| getting_there | JSONB | Transit accessibility: nearest_station_name, distance_km, walking_time_min, modes_nearby, accessibility_score, combined_score |
| trip_type_counts | JSONB | |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(wilaya_id, category)`, `(wilaya_id)`.

### Stay (`stays`)
999 rows from OSM hotel/guesthouse/hostel extraction.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider_id | UUID | FK → users.id, CASCADE |
| name | String(200) | |
| property_type | String(50) | CHECK: `hotel`, `riad`, `guesthouse`, `hostel`, `eco_lodge`, `apartment` |
| description | Text | |
| wilaya_id | Integer | FK → wilayas.id |
| address | String(500) | |
| latitude | Float | |
| longitude | Float | |
| price_per_night_dzd | Float | CK ≥ 0 |
| amenities | ARRAY(String) | |
| photos | ARRAY(String) | |
| check_in_time | String(5) | |
| check_out_time | String(5) | |
| max_guests | Integer | CK ≥ 1 |
| total_rooms | Integer | |
| is_active | Boolean | Default true |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(provider_id)`, `(wilaya_id)`.

### Experience (`experiences`)
529+ rows (expanded with ~400 seasonal/event-based experiences via `seed_seasonal_experiences.py`).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| provider_id | UUID | FK → users.id |
| title | String(200) | |
| category | String(50) | CHECK: `tour`, `workshop`, `homestay`, `hiking`, `cultural`, `food`, `adventure`, `wellness`, `other` |
| description | Text | |
| wilaya_id | Integer | FK → wilayas.id |
| meeting_point | String(500) | |
| meeting_point_lat | Float | |
| meeting_point_lng | Float | |
| price_dzd | Float | |
| duration_hours | Float | |
| max_participants | Integer | |
| language | String(5) | |
| included | ARRAY(String) | |
| what_to_bring | ARRAY(String) | |
| photos | ARRAY(String) | |
| status | String(20) | `draft` \| `active` \| `cancelled` |
| season | String(10) | Nullable, `spring` \| `summer` \| `autumn` \| `winter`, CHECK |
| start_date | Date | Nullable, for event-based experiences |
| end_date | Date | Nullable, for event-based experiences |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(provider_id)`, `(wilaya_id, category)`, `(season)`.

### Trip (`trips`)
| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| title | String(200) | |
| start_date | Date | |
| end_date | Date | |
| status | String(20) | `active` \| `archived`, default `active`, CHECK |
| total_budget_dzd | Float | |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(user_id)`, `(user_id, status)`.

### TripItem (`trip_items`)
Polymorphic items attached to a trip.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| trip_id | UUID | FK → trips.id, CASCADE |
| day_number | Integer | |
| sort_order | Integer | Default 0 |
| time_slot | String(20) | `morning` \| `afternoon` \| `evening`, nullable |
| item_type | String(20) | CHECK: `poi`, `experience`, `stay`, `restaurant`, `transport` |
| item_id | UUID | FK to the respective table |
| notes | Text | |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(trip_id)`, `(trip_id, day_number)`.

### Event (`events`)
40 seeded festivals/events.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| title | String(200) | |
| wilaya_id | Integer | FK → wilayas.id |
| category | String(50) | |
| description | Text | |
| month | Integer | CK 1–12 |
| duration_days | Integer | Default 1 |
| is_recurring | Boolean | Default true |
| photo_url | String(500) | |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(wilaya_id)`, `(month)`.

### ProviderProfile (`provider_profiles`)
One-to-one with User. Uses unified `provider_type` field with polymorphic columns based on type.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, unique |
| provider_type | String(20) | `guide`, `agency`, `hotel` |
| company_name | String(200) | Agency business name |
| description | Text | |
| specializations | ARRAY(String) | Guide specialties (e.g. `["hiking", "culture", "desert"]`) |
| certifications | ARRAY(String) | Guide certifications |
| service_areas | ARRAY(String) | Wilayas served |
| max_group_size | Integer | |
| team_size | Integer | Agency team size |
| property_name | String(200) | Hotel property name |
| property_type | String(50) | `hotel`, `riad`, `guesthouse`, `eco_lodge` |
| amenities | ARRAY(String) | Hotel amenities |
| price_range_min | Float | |
| price_range_max | Float | |
| check_in_time | String(5) | |
| check_out_time | String(5) | |
| star_rating | Integer | 1–5 |
| registration_number | String(100) | License/registration |
| years_experience | Integer | |
| languages | ARRAY(String) | |
| website | String(500) | |
| is_approved | Boolean | Default false |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Station (`stations`)
3,795 rows from transit graph.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(300) | |
| name_ar | String(300) | |
| name_en | String(300) | |
| station_type | String(50) | `bus_stop`, `train_station`, `tram_stop`, `metro_station`, `cable_car_station`, `ferry_terminal`, `airport`, `taxi_stand` |
| wilaya_id | Integer | FK → wilayas.id |
| latitude | Float | |
| longitude | Float | |
| osm_node_id | BigInt | |
| lines | ARRAY(String) | Transport line names serving this station |
| created_at | DateTime(tz) | |

### TransportLine (`transport_lines`)
636 rows.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(200) | |
| line_type | String(20) | `bus`, `tram`, `train`, `metro`, `cable_car`, `taxi`, `flight`, `ferry`, `intercity_bus` |
| wilaya_id | Integer | FK → wilayas.id |
| operator | String(200) | |
| color | String(7) | |
| created_at | DateTime(tz) | |

### LineStop (`line_stops`)
18,774 rows linking stations to lines.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| line_id | UUID | FK → transport_lines.id |
| station_id | UUID | FK → stations.id |
| stop_order | Integer | |
| schedule_info | JSONB | |
| pricing_info | JSONB | |
| departure_time | String(5) | |
| arrival_time | String(5) | |
| created_at | DateTime(tz) | |

### Favorite (`favorites`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| entity_type | String(20) | `poi` \| `experience` \| `stay`, CHECK |
| entity_id | UUID | Polymorphic FK |
| created_at | DateTime(tz) | |

**Constraints:** UNIQUE(user_id, entity_type, entity_id). Indexes: `(user_id)`, `(entity_type, entity_id)`.

### Collection (`collections`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| name | String(200) | |
| description | Text | Nullable |
| is_public | Boolean | Default false |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### CollectionItem (`collection_items`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| collection_id | UUID | FK → collections.id, CASCADE |
| entity_type | String(20) | `poi` \| `experience` \| `stay`, CHECK |
| entity_id | UUID | Polymorphic FK |
| notes | Text | Nullable |
| sort_order | Integer | Default 0 |
| created_at | DateTime(tz) | |

**Constraints:** UNIQUE(collection_id, entity_type, entity_id).

### Artisan (`artisans`)
3,752 rows extracted from OSM Overpass API (craft=*, shop=craft/*).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE, nullable |
| name | String(200) | |
| craft_type | String(50) | CHECK: `pottery`, `carpet_weaving`, `leather_work`, `woodwork`, `metalwork`, `jewelry`, `textile`, `basket_weaving`, `tilework`, `calligraphy`, `embroidery`, `stone_carving`, `glasswork`, `copper_work`, `other` |
| description | Text | Nullable |
| wilaya_id | Integer | FK → wilayas.id |
| address | String(500) | Nullable |
| commune | String(200) | Nullable |
| latitude | Float | Nullable |
| longitude | Float | Nullable |
| phone | String(20) | Nullable |
| whatsapp | String(20) | Nullable |
| website | String(500) | Nullable |
| photos | ARRAY(String) | Nullable |
| opening_hours | String(200) | Nullable |
| years_experience | Integer | Nullable |
| specializations | ARRAY(String) | Nullable |
| price_range_min | Float | Nullable |
| price_range_max | Float | Nullable |
| accepts_custom_orders | Boolean | Default true |
| has_workshop | Boolean | Default true |
| accepts_visitors | Boolean | Default true |
| is_verified | Boolean | Default false |
| metadata | JSONB | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### TransportOperator (`transport_operators`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| name | String(100) | Unique |
| name_ar | String(100) | Nullable |
| mode | String(20) | `taxi`, `bus`, `train`, etc. |
| phone | String(30) | Nullable |
| website | String(300) | Nullable |
| email | String(200) | Nullable |
| headquarters_wilaya_id | Integer | FK → wilayas.id, nullable |
| description | String(500) | Nullable |
| coverage_type | String(30) | Nullable |
| is_active | Boolean | Default true |
| metadata | JSON | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### UserPreference (`user_preferences`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE, unique |
| preferred_categories | JSONB | Nullable, list of category strings |
| preferred_wilayas | JSONB | Nullable, list of wilaya IDs |
| travel_style | String(30) | CHECK: `adventure`, `cultural`, `relaxation`, `nature`, `historical`, `culinary`, `spiritual`, `mixed` |
| budget_tier | String(20) | CHECK: `budget`, `mid_range`, `luxury`, `any` |
| interests | JSONB | Nullable |
| avoided_categories | JSONB | Nullable |
| min_entry_fee | Float | Nullable |
| max_entry_fee | Float | Nullable |
| preferred_duration_min | Integer | Nullable |
| profile_summary | Text | Nullable |
| interaction_score | JSONB | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

### Recommendation (`recommendations`)

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | PK |
| user_id | UUID | FK → users.id, CASCADE |
| entity_type | String(20) | `poi`, `experience`, `stay` |
| entity_id | UUID | Polymorphic FK |
| wilaya_id | Integer | FK → wilayas.id, nullable |
| score | Float | |
| explanation | Text | Nullable |
| reason_code | String(50) | Nullable |
| is_seen | Boolean | Default false |
| is_dismissed | Boolean | Default false |
| feedback | String(20) | Nullable, `helpful` \| `not_relevant` \| `dismissed` |
| model_version | String(50) | Nullable |
| created_at | DateTime(tz) | |
| updated_at | DateTime(tz) | |

Indexes: `(user_id, score)`, `(user_id, wilaya_id)`.

### WilayaDistance (`wilaya_distances`)
Pre-computed distances between all 69×69 wilaya pairs.

| Column | Type | Notes |
|--------|------|-------|
| origin_id | Integer | FK → wilayas.id |
| dest_id | Integer | FK → wilayas.id |
| distance_km | Float | |
| road_distance_km | Float | |

### POI-Experience Junction (`poi_experiences`)
167 links via keyword matching.

| Column | Type | Notes |
|--------|------|-------|
| poi_id | UUID | FK → pois.id |
| experience_id | UUID | FK → experiences.id |

## Constraints at DB Level
- **CHECK constraints** on `role`, `category`, `property_type`, `transport_mode`, `overall_score`, `status`, `item_type`, `time_slot`, `month`, `duration_days`, `max_guests`, `price_per_night_dzd`.
- **FK CASCADE** on all user/POI/experience references.

## Orphaned DB Tables (no ORM model, legacy from killed features)
These tables exist in the database but have no corresponding SQLAlchemy model. They were created by migrations but the model files were deleted during cleanup. Safe to drop if desired:
- `bookings` — 0 rows (killed)
- `circuits`, `circuit_items` — 0 rows (killed)
- `discussion_threads`, `discussion_posts` — 0 rows (killed)
- `reviews`, `review_votes` — 17K reviews, 35K votes seeded (killed, but data exists)
- `price_reports` — 0 rows (killed)
- `price_calendar` — 0 rows (killed)
- `live_posts` — 0 rows (killed)
- `notifications` — 0 rows (killed)
- `suggestions` — 0 rows (killed)
- `visits` — 0 rows (killed)
- `athar_traveler_profile` — 0 rows (killed)
- `local_agencies` — 10 rows seeded (killed)
- `poi_experiences` — 167 rows (junction table, no ORM model)
- `thermal_springs` — 282 rows imported from ASAL Geoportail (data exists, imported via raw SQL)

## Alembic Migrations

| # | Name | Changes |
|---|------|---------|
| 001 | Initial schema | users, refresh_tokens, reviews, pois, live_posts, price_reports |
| 002 | Seed wilayas | wilayas table + 69 rows |
| 003 | Price constraints | CHECK on transport_mode |
| 004 | POI constraints | CHECK on category |
| 005 | Review constraints | UNIQUE(user_id, poi_id) |
| 006 | User roles + providers | Role field, ProviderProfile table |
| 007 | Experiences | Experiences table + CHECK constraints |
| 008 | Bookings + Notifications | Bookings + Notifications tables |
| 009 | Trip Dashboard | Trips, TripItems, Circuits, CircuitItems |
| 010 | Stays + trip item types | Stays table, CHECK on item_type |
| 011 | Wilaya distances | WilayaDistance table |
| 012 | Seed wilaya distances | Pre-computed 69×69 distances |
| 013 | Stations + transport lines | Station, TransportLine, LineStop tables |
| 014 | Review enhancements | sub_ratings, helpfulness_count, owner_response on reviews; ReviewVote table |
| 015 | Seasonal experiences | season, start_date, end_date on experiences; season index + CHECK |
| 016 | Phase D | discussion_threads, discussion_posts, price_calendar tables; neighborhood index on pois |
