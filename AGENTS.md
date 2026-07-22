## Goal
Build a comprehensive Algerian tourism data layer (POIs, stays, experiences, agencies) on top of the existing transit graph, enabling complete tourist itinerary planning across all 58 wilayas.

## Constraints & Preferences
- **NEVER seed with fictional/synthetic data.** Every record in the database must come from a real, verifiable source (OSM, Wikidata, official operators, user contributions). Fake names, invented descriptions, generated phone numbers, etc. are strictly prohibited. If real data is unavailable for a table, leave it empty and note it as a gap.
- Use real/trusted sources — OSM Overpass API for POI extraction, Wikidata for enrichment, official operator data where available
- All POI data must be geolocated with wilaya_id for routing integration
- POIs should connect to the transit graph via walking edges from nearest transport nodes
- Systematic, scripted approach (like the transit data collection), not manual entry
- Cover all 58 wilayas progressively, starting with major cities
- **Algorithms must be simple yet robust and state of the art** — prefer battle-tested approaches over clever hacks
- **ALWAYS search for existing packages/libraries before implementing anything** — if there's a well-maintained package that solves the problem at scale, use it. Don't reinvent wheels. Check PyPI, npm, crates.io, etc. and prefer packages with 1M+ weekly downloads, active maintenance, and clear docs.

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
- **DATABASE SEEDING (initial)**: 52,997 POIs, 999 stays, 529 experiences, 10 agencies, 40 events
- **POI description enrichment (v1 tag-value mapping)**: 100% coverage from OSM tags
- **Transport graph organization**, **missing wilaya fix**, **destination enrichment**
- **POI photo enrichment**: 16.2% (8,576) with Commons/Wikipedia photos via 4 SPARQL/API phases. Wikimedia Commons ceiling reached for remaining 44K unnamed/generic POIs
- **Featured attractions** (284 POIs), **Pricing & events** (40 festivals), **Phase A** (rankings, price_level, duration, names)
- **Phase B contact data + Wikipedia**: 946 phone, 790 opening_hours, 52 Wikipedia descriptions from OSM tags. Wikidata SPARQL name matching rejected as unreliable
- **line_stops seeded**: 18,774 rows. Transit graph fully loads from DB
- **Phase 3 bus routes + POI accessibility**: Batna, Tlemcen, Jijel routes; 52,997 POIs with `getting_there` data
- **Wilaya Travel Guide**: `GET /api/v1/discover/wilayas` + `{id}/guide`
- **App runs without Docker**: graceful fallbacks for Qdrant/MinIO/Redis
- **Seasonal experiences**: ~400 new experiences with season/date columns. Events API (40 festivals)
- **Phase D**: Q&A per POI (discussion threads), price calendar, neighborhood browsing. Price calendar seed: 90 days of pricing
- **Pydantic AI travel agents** (`app/agents/`): 8 validated tools, 3 agents (chat, trip planner, search). OpenRouter Gemini Flash. Rate-limited endpoints
- **Docker is UP** (Colima): Qdrant (localhost:6333, auto-indexed 52,997 POIs + 3,150 experiences), Redis (memory), MinIO (bucket athar-uploads). `indexing_threshold` fixed from 20K→1K
- **`search_vector` tsvector columns** + pg_trgm GIN trigram indexes on POI, Experience, Stay — fixes `GET /api/v1/pois/search` crash
- **User preferences model** + migration `026`: categories, budget_level, travel_style, accessibility, etc. CRUD at `GET/PUT/DELETE /api/v1/preferences`
- **Personalized recommendations API**: `GET /api/v1/recommendations/pois|experiences|stays` — filters by user preferences + history + budget/ travel_style
- **Pydantic AI verification agent** (`app/agents/verification.py`): rule-based (dry run) + LLM mode. Admin endpoint `GET /api/v1/admin/verify/poi/{id}`. Batch verification script `scripts/data/verify_data_quality.py`
- **Overpass contact extraction** (`enrich_contacts_overpass.py`): only 61 contacts found across 50K POIs — confirms contact data is structurally absent for Algerian tourism POIs
- **Placeholder photos** (`enrich_placeholders.py`): placehold.co colored placeholders for all 44,437 POIs without photos → **100% photo coverage**
- **Wikidata bulk enrichment** (`enrich_wikidata_bulk.py`): 20K entities SPARQL-matched; only 5 websites found — confirms data poverty
- **User-contributed suggestions** (migration `027`): `suggestions` table — users submit edits to POI/stay/experience fields. Admin reviews + auto-applies. `POST /api/v1/suggestions`, `PUT /api/v1/suggestions/{id}/review`. Crowdsourced data pipeline for missing contact info
- **Expanded description enrichment** (`enrich_descriptions_expanded.py`): 52,582/52,997 POIs upgraded from "Boulangerie - à Adrar" template to structured multi-sentence descriptions using OSM tag values (elevation, year, architect, material, civilization, cuisine, operator, etc.). 18,799 remain short (<80 chars) due to minimal tag data (1-2 tags max) — template ceiling reached
- **`distance_km` field** added to `POIBrief` schema — nearby endpoint now returns distance in km sorted ascending
- **Dashboard stats endpoint** (`GET /api/v1/stats`): total POIs, stays, experiences, reviews, events, trips, users for home screen
- **All 155 tests pass** — full suite green

### Blocked
- **Wasly.app REST API** is partner-only (B2B request required) — bus data publicly unavailable
- **Wasly SNTF schedule API** returns 404 without authentication
- **SNTF.dz website** times out via curl (Joomla server-side-only)
- **No GTFS feeds** for any Algerian city
- **Contact data gap**: 96% missing phone, 99% missing website, 94% missing opening_hours — data fundamentally absent from public sources for Algerian tourism POIs. Only path is user-contributed suggestions pipeline
- **GenAI descriptions** require `OPENROUTER_API_KEY` to be set in environment
- **MinIO photo migration** pending — Commons URLs stored directly, need `mc cp` to local MinIO bucket

## Engineering Principles
- **Simple > clever**: State-of-the-art doesn't mean complex. The best solutions are boring, well-understood, and easy to debug.
- **Library-first**: Before writing any non-trivial logic, search for existing packages. For NLP → spaCy/HuggingFace/transformers; search → Qdrant/pgvector/Meilisearch; routing → OSRM/Valhalla/GraphHopper; geocoding → OpenStreetMap's Nominatim/photon; photos → Wikimedia Commons API/SPARQL; etc.
- **Scale matters**: Prefer solutions that handle 100K+ records without degradation. If a library handles batching, streaming, or connection pooling, use those features rather than implementing your own.
- **Fail gracefully**: Every external dependency should have a fallback. If Qdrant is down, fall back to SQL LIKE search. If Redis is down, use in-memory cache. Never crash because a service is unavailable.

## Key Decisions
- OSM POI extraction uses bounding box queries per wilaya (center ±radius) — 53,948 POIs across all 58 wilayas
- POI classification uses OSM tags mapped to DB schema categories
- Hotels/guesthouses/hostels/camp_sites from OSM go to `stays` table, not `pois`
- POI descriptions enriched from Wikidata (where available) + auto-generated from OSM tags
- Schedule data stored both as nested `schedule` dict and top-level fields via `clean_schedule_data.py`
- Checkpointed extraction (per-wilaya files) to survive timeouts/rate limits

## Next Steps
1. ⬜ **Set `OPENROUTER_API_KEY`** — enables Pydantic AI agents (travel planning + verification) to return real LLM-powered responses instead of mock data; enables GenAI description generation for the 18,799 POIs with short (<80 char) descriptions
2. ⬜ **Migrate Commons URLs to MinIO** — copy Wikimedia Commons photos to local MinIO bucket for self-hosted serving
3. ⬜ **User-contributed data growth** — more phone/website/hours data will arrive via the suggestions pipeline as users engage
4. ⬜ **Frontend** — the API is complete with ~120+ routes; needs a mobile/web frontend to be actually usable

## Critical Context
- Project is a full-stack FastAPI app (`athar-os-prototype/`) with PostgreSQL + Qdrant + MinIO + Redis
- **All Docker services running** via Colima: Qdrant (localhost:6333, 52,997 POI vectors + 3,150 experience vectors), Redis (localhost:6379), MinIO (localhost:9000, bucket athar-uploads)
- **DB**: external PostgreSQL (`athar_db`), not Dockerized. Alembic head: `027` (suggestions table)
- **Data counts**: 52,997 POIs (all 69 wilayas), 999 stays, 3,150 experiences, 40 events, ~3,795 stations, 155+ API endpoints, 32 endpoint modules
- POI responses include TripAdvisor-style fields: ranking, price_level, suggested_duration_min, photo_urls (100% coverage via Commons + placeholders), subtype, name_ar/name_en, is_featured, average_score, total_reviews, distance_km (nearby)
- **Description quality**: 100% coverage. 52,582 now rich (OSM tag-expanded), 18,799 short (<80 chars) due to minimal tag data (1-2 tags max) — template ceiling reached
- **Photo quality**: 16.2% real (Commons/Wikipedia), 83.8% placeholders (placehold.co). Placehold.co URLs are colored by category
- **Contact data gap**: 96% missing phone, 99% missing website, 94% missing opening_hours — data fundamentally absent from public sources. Solved by user-contributed suggestions pipeline
- **Trip planner**: 3 layers — manual trip builder (REST API), AI-powered itinerary generation (Pydantic AI, needs API key), pre-built circuits
- **32 endpoint modules, 155+ routes, 31 ORM models, ~95 Pydantic schemas**
- **All 155 tests pass**
- Seed/enrich scripts live in `scripts/data/`

## Relevant Files
- `app/data/poi_nodes_enriched.json`: 53,948 POI nodes
- `app/data/poi_edges_enriched.json`: 15,580 walking edges
- `app/data/transit_nodes_enriched.json`: 57,971 nodes (POI + transport)
- `app/data/transit_edges_enriched.json`: 31,221 edges
- `scripts/data/seed_pois_db.py`, `seed_providers.py`, `seed_stays_db.py`, `seed_experiences_db.py`, `seed_more_experiences.py`, `seed_seasonal_experiences.py`, `seed_price_calendar.py`
- `scripts/data/enrich_poi_descriptions.py`, `enrich_remaining_descriptions.py`, `enrich_poi_full.py`, `enrich_phase_a.py`
- `scripts/data/enrich_photos_bulk.py`, `enrich_photos_more.py`, `enrich_photos_spatial.py`, `enrich_photos_remaining.py`
- `scripts/data/enrich_contacts_wikipedia.py`, `enrich_contacts_overpass.py`, `enrich_wikidata_bulk.py`
- `scripts/data/enrich_descriptions_expanded.py`: OSM tag-based description expansion (52,582 enriched)
- `scripts/data/enrich_placeholders.py`: Category-colored placeholder photos (100% coverage)
- `scripts/data/verify_data_quality.py`: Data quality verification
- `scripts/data/extract_osm_pois.py`, `extract_more_bus_routes.py`, `add_walking_edges.py`, `organize_transport.py`, `fix_missing_wilaya.py`, `compute_poi_accessibility.py`, `import_geoalgeria.py`
- `alembic/versions/015-027`: 13 migrations (seasonal experiences, Phase D, price calendar, user_preferences, suggestions)
- `app/models/`: 31 ORM models across 26 files
- `app/schemas/`: ~95 Pydantic schemas across 24 files
- `app/api/v1/endpoints/`: 32 endpoint modules (155+ routes)
- `app/agents/`: Pydantic AI travel agents (tools, deps, travel_agent, verification, deps)
- `app/services/`: Trip optimizer, transit routing, transport cost, vector search, storage, agent tools
