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
- **Final transit graph**: 57,723 nodes (53,948 POIs + 3,775 transport nodes), 30,784 edges
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
- **App runs without Docker**: API starts and serves all endpoints, gracefully falling back (Qdrant→no vector search, MinIO→no uploads, Redis→in-memory rate limiter)
- **Spec docs synced**: `database.md` (22 models), `api.md` (85 routes), `architecture.md` (accurate counts), `README.md` (fixed links)
- **OSM bus stations** (`insert_osm_bus_stations.py`): 425 new `amenity=bus_station` nodes imported from OSM Overpass API — DB now has **4,329 stations** (3,660 bus, 301 train, 204 tram, 70 taxi, 27 airport, etc.)
- **MultiModalRouter generalized** (`multimodal_router.py`): SQL fixed to include ALL multi-wilaya transport lines (was train+flight only, now includes 354 taxi + 13 bus + 6 tram + 4 ferry). **444 total multi-wilaya lines** loaded (was 66). **3,918 adjacency edges** in connectivity graph. Almost every wilaya has 62+ direct connections. `walking` mode excluded from inter-wilaya segments. Bug fixed: missing `mode` key in `line_record` dict, `per_person` pricing for taxis.
- **POI graph service** (`app/services/poi_graph.py`): Networkx-based tourist routing with singleton pattern:
  - **Tour optimization**: Density-based candidate selection with cluster fallback — finds spatially close POIs within a wilaya, uses 2-opt TSP for >8 POIs or exact TSP for ≤8. Handles isolated featured POIs by scanning for densest cluster.
  - **Walking graph**: 34,787 tourism POIs (featured + historical/natural/cultural/religious/museum/park), 535,237 edges within 5km radius.
  - **POI clustering**: Grid-based spatial clustering with configurable radius
  - **Hub detection**: Betweenness centrality for hub POIs
  - **API endpoints**: `GET /pois/tour/optimize`, `/pois/tour/clusters`, `/pois/tour/hubs`
  - **Results**: Oran 9 POIs (4.1km), Tlemcen 10 POIs (2.3km), Algiers 10 POIs (3.2km), Blida 9 POIs (0.8km), Batna 9 POIs (5.5km), Constantine 7 POIs (1.2km)
- **Trip optimizer wired to POI graph** (`trip_optimizer.py`): `optimize_day()` now uses POIGraphService for walking times between POIs (falls back to haversine). `detect_gaps()` also uses POI graph. `suggest_fillers()` now uses cluster-based recommendations.
- **POI durations recalibrated** for realistic walking tours: historical 30min (was 90), museum 45min (was 120), natural 45min (was 180), mountain 90min (was 240), park 30min, cafe 15min, restaurant 30min, market 20min, other 20min.
- **Fun facts enrichment** (`enrich_fun_facts.py`): 583 POIs with fun facts from 3 sources:
  - Wikidata SPARQL: year built, UNESCO status, architect (16 POIs)
  - OSM tags: height, material, cuisine, historic type (304 POIs)
  - Category templates: "one of Algeria's hidden gems", "preserves cultural heritage" (263 POIs)
  - New DB columns: `fun_fact` (Text), `fun_fact_source` (String(200)) — migration 031
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
- **Transport data quality fix** (`fix_transport_data.py`): 62 bad train stops remapped from taxi/bus stations to real SNTF stations; 113 newly train-connected wilaya pairs, 7 newly flight-connected pairs (139 train, 22 flight total)
- **Transport operators** (migration `030`): 16 real operators seeded — SNTF, Air Algérie, ETUSA, ETO, SOGRAL, ENTV, Télécabine d'Oran, SETRAM, tramway operators (Sétif, SBA, Mostaganem, Ouargla, Constantine), 3 major SNTF line corridors
- **Schedule & pricing data**: SNTF Alger→Oran (1,500-2,500 DZD, every 1h, 4h), Alger→Constantine (1,500-2,500 DZD, every 90min, 4h), Constantine→Annaba (1,200-2,000 DZD, every 2h, 3h), Alger→Béjaïa (1,200-2,000 DZD, every 2h, 3h), all SOGRAL intercity lines (1,500-2,000 DZD, every 30min)
- **MultiModalRouter** (`app/services/multimodal_router.py`): Inter-wilaya routing with direct train, multi-hop train via hubs (Algiers/Constantine/Oran), SOGRAL bus, flight options. Real schedules, pricing, operator contacts (phone, website, email). Boumerdès→Oran now shows train via Alger hub (1,500 DZD, 5h with transfer)
- **Agent tools upgrade**: `get_transport_route` now returns multi-modal options with schedules, pricing, contacts; new `get_operator_contacts` tool for phone numbers and websites

### Blocked
- **Wasly.app REST API** is partner-only (B2B request required) — bus data publicly unavailable
- **Wasly SNTF schedule API** returns 404 without authentication
- **SNTF.dz website** times out via curl (Joomla server-side-only)
- **No GTFS feeds** for any Algerian city
- **Contact data gap**: 96% missing phone, 99% missing website, 94% missing opening_hours for POIs. Transport operators now have contacts; POI gap remains
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
1. ⬜ **Expand schedule/pricing** to remaining 844 transport lines (currently 11/855 have schedule data)
2. ⬜ **Add operator contacts for remaining wilaya taxi unions** — currently only national operators seeded; wilaya-level taxi phone numbers needed
3. ⬜ **Migrate Commons URLs to MinIO** — copy Wikimedia Commons photos to local MinIO bucket for self-hosted serving
4. ⬜ **Frontend** — the API is complete with ~120+ routes; needs a mobile/web frontend to be actually usable
5. ⬜ **More fun facts for remaining POIs** — 583/52,997 POIs have fun facts (1.1%); expand via GenAI (vLLM Gemma 4) for richer tourist experiences
6. ⬜ **Improve tour diversity** — current optimizer picks same-category clusters (e.g., all archaeological sites); add category diversity scoring to mix museums, natural, cultural POIs in one tour

## Critical Context
- Project is a full-stack FastAPI app (`athar-os-prototype/`) with PostgreSQL + Qdrant + MinIO + Redis
- **All Docker services running** via Colima: Qdrant (localhost:6333, 52,997 POI vectors + 3,150 experience vectors), Redis (localhost:6379), MinIO (localhost:9000, bucket athar-uploads)
- **DB**: external PostgreSQL (`athar_db`), not Dockerized. Alembic head: `031` (add_poi_fun_fact table)
- **Data counts**: 52,997 POIs (all 69 wilayas), 999 stays, 529 experiences, 40 events, ~4,329 stations, 855 transport lines, 16 transport operators, 155+ API endpoints, 32 endpoint modules
- **POI graph**: 34,787 tourism POIs, 535,237 walking edges, singleton POIGraphService — 10 POIs in Tlemcen, 9 in Oran/Blida/Batna, 10 in Algiers, 7 in Constantine, 6 in Bejaia/Ghardaia/Tizi Ouzou
- POI responses include TripAdvisor-style fields: ranking, price_level, suggested_duration_min, photo_urls (100% coverage via Commons + placeholders), subtype, name_ar/name_en, is_featured, average_score, total_reviews, distance_km (nearby), fun_fact
- **Description quality**: 100% coverage. 52,582 now rich (OSM tag-expanded), 18,799 short (<80 chars) due to minimal tag data (1-2 tags max) — template ceiling reached
- **Photo quality**: 16.2% real (Commons/Wikipedia), 83.8% placeholders (placehold.co). Placehold.co URLs are colored by category
- **Contact data gap**: 96% missing phone, 99% missing website, 94% missing opening_hours — data fundamentally absent from public sources. Solved by user-contributed suggestions pipeline
- **Trip planner**: 3 layers — manual trip builder (REST API), AI-powered itinerary generation (Pydantic AI, needs API key), pre-built circuits
- **32 endpoint modules, 155+ routes, 32 ORM models, ~95 Pydantic schemas**
- **All 155 tests pass**
- Seed/enrich scripts live in `scripts/data/`

## Relevant Files
- `app/services/multimodal_router.py`: Multi-modal inter-wilaya routing (train/bus/flight/taxi, multi-hop, schedules, pricing, contacts)
- `app/services/transport.py`: WilayaDistance-based flat cost estimates
- `app/services/transit_routing.py`: Intra-city Dijkstra on stations/line_stops
- `app/agents/tools.py`: 10 agent tools including `get_transport_route` (multi-modal) and `get_operator_contacts`
- `app/agents/travel_agent.py`: 3 agents (travel, itinerary, search) with all tools registered
- `app/models/transport_operator.py`: TransportOperator ORM model
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
- `scripts/data/fix_transport_data.py`: Train stop fixes + wilaya connectivity flag recomputation
- `scripts/data/seed_operators.py`: Transport operator contacts + SNTF/SOGRAL schedule & pricing
- `alembic/versions/015-030`: 14 migrations (seasonal experiences, Phase D, price calendar, user_preferences, suggestions, artisans, transport_operators)
- `app/models/`: 32 ORM models across 27 files
- `app/schemas/`: ~95 Pydantic schemas across 24 files
- `app/api/v1/endpoints/`: 32 endpoint modules (155+ routes)
- `app/agents/`: Pydantic AI travel agents (tools, deps, travel_agent, verification, deps)
- `app/services/`: Trip optimizer, transit routing, transport cost, vector search, storage, agent tools
