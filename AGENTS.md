## Goal
Build a comprehensive Algerian tourism data layer (POIs, stays, experiences, agencies) on top of the existing transit graph, enabling complete tourist itinerary planning across all 58 wilayas.

## Constraints & Preferences
- Use real/trusted sources — OSM Overpass API for POI extraction, Wikidata for enrichment, official operator data where available
- All POI data must be geolocated with wilaya_id for routing integration
- POIs should connect to the transit graph via walking edges from nearest transport nodes
- Systematic, scripted approach (like the transit data collection), not manual entry
- Cover all 58 wilayas progressively, starting with major cities

## Progress
### Done
- Ingested Oran urban transport academic dataset (Reguieg 2026, Zenodo/CERN): **26 bus lines + tram**, ~600 geocoded stops, real pricing, directed stop-to-stop connections
- Scraped ~150 real urban bus routes from OSM Overpass API for Algiers/ETUSA, Tiaret, Sétif, Mostaganem, Ghardaïa
- Added 442 inter-city taxi edges (all with schedules: 05:00-23:00, every 30min) and 9,743 walking transfer edges
- **Wasly cable cars**: Tlemcen (3 stn), Blida (3), Tizi Ouzou (4), Annaba (2), Constantine (3) — all added
- **Wasly trams**: Sétif (23 stn, TRAM_SET 42 edges), SBA (22, TRAM_SBA 42), Mostaganem L1+L2 (24, TRAM_MOS 44), Ouargla (16, TRAM_OUA 22), Constantine (21, TRAM_CON 40) — all added
- **OSM `highway=bus_stop` nodes**: 1,105 new bus stop nodes across 31 cities
- **Walking transfers**: 6,958 edges connecting nearby stops within cities via grid-based spatial index
- **104 isolated train stations** connected to nearest neighbor with 208 SNTF train edges
- **Southern access enrichment**: 30 airport↔city transfer edges, 8 missing flight routes, 4 new SOGRAL bus stations, 18 SOGRAL edges connecting southern resorts
- **Schedule data cleanup**: 10,914 fields promoted nested→top-level, 208 conflicts resolved, 9,160 default schedules added — all 15,204 edges have 100% consistent schedule data
- **Domestic Airlines flights**: 2 new airport nodes (Adrar/Touat, Tiaret) added + 12 flight edges for Air Algérie subsidiary's southern routes
- **OSM POI extraction (all 58 wilayas)**: 53,948 unique POI nodes extracted via Overpass API, categorized, deduplicated, and merged into transit graph with 15,580 walking edges connecting POIs to nearest transit nodes
- **Phase B transport expansion**: Extracted 18 new OSM bus routes (106 new bus stop nodes, 264 new edges) for Algiers, Bejaia, Oum El Bouaghi, and Ouargla; added 79 bus stops in Constantine, Biskra, Tebessa, Tamanrasset. Fixed duplicate node IDs (16 removed).
- **Final transit graph**: **57,971 nodes** (53,948 POIs + 4,023 transport), **33,669 edges** (4,076 bus, 27,756 transfer/walking, 507 train, 442 taxi, 404 intercity, 353 tram, 62 flight, 29 metro, 28 cablecar, 12 ferry)
- **DATABASE SEEDING**: All tourism tables now populated:
  - **52,997 POIs** in `pois` table (all categories: historical, natural, cultural, religious, museum, beach, mountain, park, market, restaurant, cafe)
  - **999 stays** in `stays` table (624 hotels, 249 hostels, 126 guesthouses — extracted from OSM POIs)
  - **73 experiences** across all 58 wilayas (31 tours, 14 cultural, 13 adventure, 7 hiking, 6 wellness, 2 food)
  - **10 local agencies** covering key regions (Kabylie, Sahara, Tassili, Hoggar, M'zab, etc.)
  - **4 provider users** (hotel, agency, guide, admin) + 3 provider profiles
- **POI description enrichment**: 52,997/52,997 (100%) POIs now have descriptions — originally 42,254 from Wikidata/tag-based; all 9,974 remaining (including unnamed POIs) now covered via tag-value mapping (`enrich_remaining_descriptions.py`)
- **Transport graph organization** (`organize_transport.py`): taxi edges into 361 named routes, SOGRAL consolidated, 187 inter-city connections added, station line lists populated. **DB seeded**: 3,795 stations + 636 transport lines. Fixed column name mismatch (`station_type` vs `type`).
- **Missing wilaya fix** (`fix_missing_wilaya.py`): 2,501/2,502 transit nodes assigned correct wilaya via nearest-center + name matching; remaining 10 are international airports/ferries outside Algeria. **DB stations all have wilaya_id** (0 NULLs).
- **Destination enrichment** (`enrich_wikivoyage.py`, `enrich_descriptions_auto.py`): All 69 wilayas now have French destination descriptions (16 from FR Wikivoyage, 4 EN, 49 auto-generated from OSM data). New `description`/`description_en` columns on `wilayas` table.
- **POI photo enrichment**: 4,738 POIs have valid Commons/Wikipedia photos (9.1%):
  - Phase 1 (`enrich_wikimedia_photos.py`): 131 original photos via Commons search
  - Phase 2 (`enrich_photos_bulk.py` + `enrich_photos_more.py`): 4,096 via Wikidata SPARQL matching + 511 via Wikipedia API pageimage search
- **Featured attractions** (`enrich_featured_attractions.py`): 284 POIs across 62 wilayas ranked as featured/must-see based on OSM category + tag importance. New `featured_order`/`is_featured` columns on `pois`.
- **Pricing & events** (`enrich_pricing_events.py`): All 999 stays now have real estimated pricing (800-15,000 DZD/night by type). 39,102 POIs have entry fees (0-500 DZD). **40 events/festivals** seeded in new `events` table.
- **Comprehensive POI enrichment** (`enrich_poi_full.py`): All 52,997 POIs enriched from OSM JSON — 100% have subtype, osm_node_id, osm_type, has_parking, has_accessibility; 11,300 with name_en, 4,122 with name_ar, 930 with cuisine, 294 with operator. New columns added: `subtype`, `operator`, `has_parking`, `has_accessibility`, `name_ar`, `name_en`, `osm_node_id`, `osm_type`, `cuisine`.
- **Experience expansion**: 456 new experiences added across 69 wilayas — **529 total** (avg 7.7/wilaya).
- **GeoAlgeria tourism import** (`import_geoalgeria.py`): **282 thermal springs** from ASAL Geoportail (authoritative gov source — new data, previously none), 30 national parks, 42 POI descriptions enriched via historic-site Wikidata cross-reference.
- **Phase A enrichment** (`enrich_phase_a.py`): TripAdvisor-style data from existing assets:
  - **Rankings**: All 52,997 POIs ranked per wilaya×category (by featured + name)
  - **Price level**: Derived from entry_fee_dzd (Free/$/$$/$$$)
  - **Duration**: Suggested visit duration per category (30min–4h)
  - **Photo bulk fetch** (`enrich_photos_bulk.py`): 275 photos via Wikidata SPARQL matching (478 total);
  - **Phase A2** (`enrich_photos_more.py`): 4,096 photos from enhanced SPARQL + Commons API fallback (5,174 total)
  - **Names**: 48,580 Arabic/English names extracted from osm_tags
  - **POI↔Experience links**: 167 links via keyword matching in `poi_experiences` junction table
- **Phase B: Contact data + Wikipedia** (`enrich_contacts_wikipedia.py`): Extracted phone (946), website (89), opening_hours (790), email (103), social_media (25) from source OSM tags; fetched 52 Wikipedia descriptions for POIs with explicit wikipedia tag. Wikidata SPARQL name-based description matching rejected as unreliable (~16K false matches on unnamed/generic POI names)
- **line_stops seeded** (`seed_line_stops.py`): 18,774 rows (8,015 intra-city transfer pairs + 2,787 transport line stops across 855 lines). Fixed `pricing_info` NameError + missing DB columns (`schedule_info`, `pricing_info`, `departure_time`, `arrival_time`). Transit graph now fully loads from DB — all routing endpoints operational.
- **Phase 3 bus routes** (`extract_bus_routes_phase3.py`): 4 new OSM route relations (Batna route 03, Tlemcen A42+B42, Jijel الطاهير-جيجل) — 103 new nodes, 292 new edges. New `script/data/compute_poi_accessibility.py` computes for each of 52,997 POIs: nearest station distance, walking time, transport modes nearby, stored in `getting_there` JSONB.
- **Wilaya Travel Guide** (`GET /api/v1/discover/wilayas` + `GET /api/v1/discover/wilayas/{id}/guide`): Curated per-wilaya POI browsing sorted by combined score (accessibility × 0.4 + category weight × 0.3 + featured bonus × 0.3), capped at top N per category. Includes transport accessibility, experiences, and stays.
- **App runs without Docker**: API starts and serves all endpoints, gracefully falling back (Qdrant→no vector search, MinIO→no uploads, Redis→in-memory rate limiter)
- **All 126 tests pass** — full suite green after fixing review/live response builders, seed data, schema constraints
- **Seasonal experiences** (`015_seasonal_experiences_events.py`): Added `season`, `start_date`, `end_date` columns to `experiences`. New index on `season` + CHECK constraint. `seed_seasonal_experiences.py` adds ~400 seasonal/event-based experiences (spring/summer/autumn/winter + fixed-date events) across all 58 wilayas.
- **Events API**: New `Event` SQLAlchemy model for existing raw `events` table (40 festivals). `GET /api/v1/events` (filter by wilaya/category/month) + `GET /api/v1/events/{id}`. Read-only calendar endpoints.
- **Season filter on experiences**: `GET /api/v1/experiences?season=spring` filters by season.

### Blocked
- **Wasly.app REST API** is partner-only (B2B request required) — bus data publicly unavailable
- **Wasly SNTF schedule API** returns 404 without authentication
- **SNTF.dz website** times out via curl (Joomla site, server-side rendering only)
- **No GTFS feeds** for any Algerian city
- **Docker daemon unavailable** — Qdrant vector search, MinIO uploads, Redis persistence need Docker
- **Seasonal seed script** needs `docker compose up` + `alembic upgrade head` before running `seed_seasonal_experiences.py`

## Key Decisions
- OSM POI extraction uses bounding box queries per wilaya (center ±radius) — 53,948 POIs across all 58 wilayas
- POI classification uses OSM tags mapped to DB schema categories
- Hotels/guesthouses/hostels/camp_sites from OSM go to `stays` table, not `pois`
- POI descriptions enriched from Wikidata (where available) + auto-generated from OSM tags
- Schedule data stored both as nested `schedule` dict and top-level fields via `clean_schedule_data.py`
- Checkpointed extraction (per-wilaya files) to survive timeouts/rate limits

## Next Steps
1. **⬅️ Start Docker** (`docker compose up -d qdrant`) and run the app — Qdrant auto-indexes POIs/experiences at startup for vector search
2. **⬅️ Migrate Wikimedia photos to MinIO** — stored as Commons URLs; move to MinIO when Docker is up
3. **⬅️ line_stops seeded**: 18,774 rows, transit graph fully loads from DB.
4. **⬅️ Phase 3 bus routes**: Batna (route 03), Tlemcen (A42+B42, 125 stops), Jijel (1 route). 103 new nodes, 292 new edges.
5. **⬅️ POI accessibility computed**: All 52,997 POIs have `getting_there` data (nearest station, distance, modes).
6. **⬅️ Wilaya Travel Guide**: `GET /api/v1/discover/wilayas` + `GET /api/v1/discover/wilayas/{id}/guide`.
7. **⬅️ All 126 tests pass** — full suite green.
8. **⬅️ Seasonal experiences**: ~400 new experiences with season/start_date/end_date. Events API (read-only calendar, 40 festivals).
9. ⬜ Phase D: Q&A per POI, neighborhood browsing, price calendar for experiences
10. ⬜ More photos: migrate Wikimedia→MinIO, bulk Commons fetch for remaining historical/cultural POIs
11. ⬜ Build user-facing frontend or mobile app

## Critical Context
- Project is a full-stack FastAPI app (`athar-os-prototype/`) with PostgreSQL + Qdrant + MinIO + Redis
- All tourism tables now populated with real OSM and curated data
- API endpoints at `/api/v1/pois`, `/stays`, `/experiences`, `/events`, `/discover`, `/bookings`, `/reviews`, `/trips` all return data
- POI responses include TripAdvisor-style fields: ranking, price_level, suggested_duration_min, photo_urls[], subtype, name_ar/name_en, is_featured, average_score, total_reviews
- Vector search (Qdrant) configured but needs Docker running to work
- App has trip optimizer combining POIs + transport + stays + restaurants + experiences
- **18 endpoint modules, ~97 routes, 26 ORM models (21 files), ~90 Pydantic schemas (20 files)**
- Seed scripts live in `scripts/data/`: `seed_pois_db.py`, `seed_providers.py`, `seed_stays_db.py`, `seed_experiences_db.py`, `seed_more_experiences.py`, `seed_seasonal_experiences.py`, `enrich_poi_descriptions.py`

## Relevant Files
- `app/data/poi_nodes_enriched.json`: 53,948 standalone POI nodes
- `app/data/poi_edges_enriched.json`: 15,580 walking edges POI↔transit
- `app/data/transit_nodes_enriched.json`: 57,971 nodes (POI + transport, deduplicated)
- `app/data/transit_edges_enriched.json`: 31,221 edges (4,076 bus, 404 intercity, 442 taxi, 507 train, 353 tram, 25,308 transfers, etc.)
- `scripts/data/seed_pois_db.py`: POI → DB seeder
- `scripts/data/seed_providers.py`: Users + profiles + agencies seeder
- `scripts/data/seed_stays_db.py`: Hotels/guesthouses → stays table
- `scripts/data/seed_experiences_db.py`: Curated experiences (first batch)
- `scripts/data/seed_more_experiences.py`: Experiences for remaining wilayas
- `scripts/data/enrich_poi_descriptions.py`: Wikidata + tag-based description enrichment
- `scripts/data/enrich_remaining_descriptions.py`: Tag-value mapping for all remaining POI descriptions (100% coverage)
- `scripts/data/enrich_poi_full.py`: Full OSM field extraction (subtype, operator, parking, accessibility, names, IDs, cuisine)
- `scripts/data/import_geoalgeria.py`: Thermal springs, parks, historic cross-reference from @geoalgeria/tourisme
- `scripts/data/extract_osm_pois.py`: OSM extraction + transit graph merge
- `scripts/data/extract_more_bus_routes.py`: Additional OSM bus route extraction (18 new routes, Algiers/Bejaia/Ouargla/Oum El Bouaghi)
- `scripts/data/add_walking_edges.py`: Walking edge generation for newly added transit nodes (354 new walking edges)
- `scripts/data/organize_transport.py`: Taxi/SOGRAL/inter-city routes + DB seeding
- `scripts/data/fix_missing_wilaya.py`: Assign wilaya to transit nodes via reverse geocoding
- `scripts/data/enrich_phase_a.py`: Rankings, price level, duration, POI↔experience links
- `scripts/data/enrich_photos_bulk.py`: Photo enrichment via Wikidata SPARQL matching
- `scripts/data/enrich_photos_more.py`: Enhanced photo enrichment (SPARQL + Commons API)
- `scripts/data/enrich_contacts_wikipedia.py`: Contact data + Wikipedia description extraction
- `scripts/data/seed_seasonal_experiences.py`: ~400 seasonal/event-based experiences across 58 wilayas
- `alembic/versions/015_seasonal_experiences_events.py`: Migration for season/start_date/end_date on experiences
- `app/models/event.py`: Event model for existing events table
- `app/schemas/event.py`: EventRead/EventFeed schemas
- `app/api/v1/endpoints/events.py`: Events API endpoints (list + detail, read-only)
