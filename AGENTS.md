## Goal
Build ATHAR — the definitive agentic travel guide for Algeria. Not a social media platform, not a superapp. Think Google Maps + TripAdvisor + Wikivoyage, powered by AI agents that plan your trip.

**Core product (what users actually need):**
1. Discover — search any wilaya, see all POIs with photos, descriptions, fun facts
2. Plan — "I'm in Oran for 2 days" → optimized walking tour
3. Navigate — "Algiers to Tlemcen" → real train/taxi/flight options with schedules
4. Stay — "Where can I sleep near Timgad" → real hotels with prices

**What we are NOT:** A booking platform, a social network, an artisan marketplace, or a superapp. Data quality and AI-powered discovery are the moat — not transactional features.

**Keep:** POIs, stays, experiences, transport, tours, favorites, collections, trips (see other travelers' plans), artisans (with real scraped data).
**Kill:** Discussion threads, live posts, WhatsApp bot, mock visa OCR — social media bloat.
**Deprioritize:** Bookings (0 rows, nobody's booking through a guide), reviews (seeded, not real).

## Constraints & Preferences
- Use real/trusted sources — OSM Overpass API for POI extraction, Wikidata for enrichment, official operator data where available
- All POI data must be geolocated with wilaya_id for routing integration
- POIs should connect to the transit graph via walking edges from nearest transport nodes
- Systematic, scripted approach (like the transit data collection), not manual entry
- Cover all 58 wilayas progressively, starting with major cities
- **NEVER seed with fictional/synthetic data.** Every record must come from a real, verifiable source.

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
  - **529 experiences** across all 58 wilayas (31 tours, 14 cultural, 13 adventure, 7 hiking, 6 wellness, 2 food)
  - **10 local agencies** covering key regions (Kabylie, Sahara, Tassili, Hoggar, M'zab, etc.)
  - **4 provider users** (hotel, agency, guide, admin) + 3 provider profiles
- **POI description enrichment**: 52,997/52,997 (100%) POIs now have descriptions — originally 42,254 from Wikidata/tag-based; all 9,974 remaining (including unnamed POIs) now covered via tag-value mapping (`enrich_remaining_descriptions.py`)
- **Transport graph organization** (`organize_transport.py`): taxi edges into 361 named routes, SOGRAL consolidated, 187 inter-city connections added, station line lists populated. **DB seeded**: 3,795 stations + 636 transport lines. Fixed column name mismatch (`station_type` vs `type`).
- **Missing wilaya fix** (`fix_missing_wilaya.py`): 2,501/2,502 transit nodes assigned correct wilaya via nearest-center + name matching; remaining 10 are international airports/ferries outside Algeria. **DB stations all have wilaya_id** (0 NULLs).
- **Destination enrichment** (`enrich_wikivoyage.py`, `enrich_descriptions_auto.py`): All 69 wilayas now have French destination descriptions (16 from FR Wikivoyage, 4 EN, 49 auto-generated from OSM data). New `description`/`description_en` columns on `wilayas` table.
- **POI photo enrichment** (post-reseed restore + Aug 2026 expansion): **9,059 POIs** have real MinIO-hosted photos (17.2%), 43,626 have category placeholders:
  - **ATHAR MinIO** on `127.0.0.1:19000` (isolated from meddata's 9000), data dir `minio_data/` (gitignored, ~2.2GB, **2,394 objects**), compose base file ports updated
  - Photo passes: `enrich_photos_spatial.py` (Wikidata proximity 500m, **+3,870**), `enrich_photos_commons_category.py` (Commons GPS categories 200m, +62 — DB update was a stub, fixed), `enrich_photos_remaining.py` (~650 named POIs, +227), `enrich_photos_more2.py` (OSM wikidata + SPARQL, exhausted — 0), `enrich_photos_category_walk.py` (recursive Commons category walk: 700 cats, 3,907 images, **+161**)
  - `migrate_photos_minio.py` fixed (3 commits): raw URL tried first, double-encoded `%25C3` → `%C3` collapse, underscore-decode as 404 fallback, SVG support, **`_fix_thumbnail_url` no longer re-quotes percent-encoded filenames** (was `%28`→`%2528` → 404; +43 URLs recovered), URL length guard for `varchar(500)`, SPARQL retries (4×, backoff)
  - **0 Wikimedia URLs remain in DB**; all 9,059 photo-bearing POIs have MinIO `photo_url` primary
  - All 43,626 remaining POIs have category placeholders (`enrich_placeholders.py`)
- **POI transit routing** (`PoiTransitRouter`): GPS→POI multimodal routing with turn-by-turn directions. Combines walking + transit via Dijkstra on the in-memory TransitGraph. Returns structured steps: walking, transit (schedule/pricing), transfers (milestones for line changes). Handles walking-only, no-station-nearby, driving-recommended. New endpoints: `GET /transport/route-to-poi/{poi_id}`, enhanced `GET /transport/plan` (now includes walking segments). Service at `app/services/poi_transit_router.py`.
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
- **OSM bus stations** (`insert_osm_bus_stations.py`): 425 new `amenity=bus_station` nodes imported from OSM Overpass API — DB now has **4,329 stations** (3,660 bus, 301 train, 204 tram, 70 taxi, 27 airport, etc.)
- **MultiModalRouter generalized** (`multimodal_router.py`): SQL fixed to include ALL multi-wilaya transport lines (was train+flight only, now includes 354 taxi + 13 bus + 6 tram + 4 ferry). **444 total multi-wilaya lines** loaded (was 66). **3,918 adjacency edges** in connectivity graph. Almost every wilaya has 62+ direct connections. `walking` mode excluded from inter-wilaya segments. Bug fixed: missing `mode` key in `line_record` dict, `per_person` pricing for taxis.
- **POI graph service** (`app/services/poi_graph.py`): Networkx-based tourist routing with singleton pattern — 34,787 tourism POIs, 535,237 walking edges within 5km. Tour optimization with density-based cluster detection: Oran 9 POIs (4.1km), Tlemcen 10 (2.3km), Algiers 10 (3.2km), Blida 9 (0.8km), Batna 9 (5.5km), Constantine 7 (1.2km). API endpoints: `/pois/tour/optimize`, `/clusters`, `/hubs`.
- **Trip optimizer wired to POI graph** (`trip_optimizer.py`): `optimize_day()` uses POIGraphService walking times (haversine fallback). `detect_gaps()` and `suggest_fillers()` also use POI graph for cluster-based recommendations.
- **POI durations recalibrated**: historical 30min (was 90), museum 45min (was 120), natural 45min (was 180), mountain 90min (was 240) for realistic walking tours.
- **Fun facts enrichment** (`enrich_fun_facts.py` + `enrich_fun_facts_genai.py`): **3,796 POIs** with fun facts — 22 from Wikidata/Wikipedia, 3,774 from GenAI via vLLM Gemma 4 (97.9% success rate; second pass +1,030 with 0 errors). Migration 031: `fun_fact` + `fun_fact_source` columns.
- **Real artisan data** (commit `ad715fa`): **3,744 artisan shops** extracted from OSM Overpass API across 52/58 wilayas (craft=*, shop=craft/pottery/carpet/leather/jewelry). All geolocated with wilaya_id. Top: Tlemcen 1,710, Algiers 311, Ain Temouchent 273. DB seeded: 3,752 total (8 existing + 3,744 new).
- **Social media bloat killed** (commit `d1472d7`): Discussion threads, live posts, WhatsApp bot, mock visa OCR — all removed.
- **Bookings, circuits, notifications killed** (commit `180cd78`): 0 rows, not core to travel guide.
- **Reviews killed** (commit `0ab3625`): Seeded, not real user data. POI ratings return defaults (None/0).
- **8 dead features killed** (commit `9835797`): Price reports, price calendar, suggestions, visits, preferences, recommendations, stats, studio media — all 0 rows, not core.
- **API security hardening** (commit `12faa19`): OTP no longer hardcoded (uses `secrets` module), not returned in response body, `_otp_store` has TTL (5min) + size cap (1000) + auto-cleanup. `create_poi`/`upload_poi_photo` require provider/admin role. `register_provider` requires authentication. UUID type annotations on events/recommendations endpoints.

### Done (new)
- **Agent memory system**: Three-tier persistent memory for multi-turn conversations:
  - `agent_sessions` + `agent_memories` DB tables (migration `ef64db5de951`)
  - Episodic memory: stores conversation turns per session, reconstructed as `message_history`
  - Semantic memory: agent-controlled `remember(key, value)` / `recall(key)` tools
  - Context compression via `build_message_history()` — injects previous turns as structured text preamble
  - Session management: `GET /agent/sessions`, `DELETE /agent/sessions/{id}`
  - All 5 agents (travel, itinerary, search, transport, events) have memory tools registered
  - 21 new tests, 213 total
- **Agent resilience stack** (`app/agents/resilience.py`, 46 new tests, **270 total**): hardened the 5 Pydantic AI agents against transient LLM-backend failures per 2026 retry/fallback best practices:
  - **Retrying HTTP transport**: wrapper around httpx that silently retries 429/5xx/connect/timeout with exponential backoff + jitter, honoring `Retry-After`; used by `_make_model` in `travel_agent.py` (fixed a `_wait` bug where `outcome.result()` re-raised the HTTPStatusError instead of sleeping)
  - **Per-run hard timeout** (45s), **per-agent usage limits** (8–12 requests / 12–20k tokens), **tool retry budget** (`retries={'tools':2,'output':1}`) + `tool_timeout=20s` wired into all 5 agent factories
  - **`run_agent_safely()`**: circuit breaker check → timeout → usage limits → retries; returns `(output, trace)`, raises `AgentUnavailable` for 503 (breaker open / timeout); all endpoints in `agents.py` now route through it (503 instead of 500 during recovery)
  - **Injection detection expanded** (10→27 patterns): `ignore/forget/disregard` variants, role-switches, system-prompt disclosure, `[INST]`/`<<SYS>>`/`DAN mode`/`developer mode`, markup-based; **`sanitize_history()`** re-screens persisted conversation history (drops injection entries, redacts PII) before it enters the system prompt — wired into `build_message_history()`
  - **Memory hardening**: `remember()` caps (key ≤64, value ≤2000 chars, ≤100 semantic facts/session, trims input), `remember` tool returns a graceful error instead of raising; `security.py` now classifies `remember`/`recall` (WRITE/READ)
  - **eval.py fixed** for pydantic-ai 2.22: tool-call extraction now uses the defensive `tool_call_names()` (was dead `result.tool_call_names`); `reset_circuit_breakers()` added for test/restart isolation
- **Operator contacts enrichment**: **152 operators, 86 with real phones** (up from ~24). All 15 gobytaxi numbers verified on live pages. Fixed placeholder numbers (SOGRAL +213 21 77 00 66, ENTV, SNTF +213 21 71 15 10, ETUSA +213 21 66 74 14). Added 22 Air Algérie wilaya agencies + Contact Center (from airalgerie.dz, airalgerie.info), 4 SNTF regional offices + 4 station phones (from sntf.dz, guideoran.com), 2 SOGRAL gare phones (Tamanrasset 029 30 02 04, Souk Ahras 037 71 57 72 from sogral.dz), 5 ENTMV ferry agencies, 7 SETRAM units (all with direct operational unit phones from setram.dz — Algiers, Oran, Constantine, Sétif, SBA +213 560 60 23 27, Ouargla +213 560 60 16 27, Mostaganem +213 551 24 24 24), 22 taxi/VTC operators via gobytaxi.com (15 verified live) + guideoran.com, travel agencies (NEDJMA Mostaganem 045 30 71 99, Amal Voyages Tlemcen 043 20 42 49). ETUSA Call Center found: 0770 10 10 68. ETO Oran réclamation: 041 58 11 11. GobyTaxi contacts: Gare Routiere Tlemcen +213 43 22 29 00, Tamtam Annaba +213 671 06 76 02, Station Interstates Setif +213 774 29 39 00, Station Taxis Biskra +213 663 17 75 19, Taxi Ben Allal Miliana +213 555 00 09 29, Time Taxi Alger +213 553 61 02 03, Taxi Benali Tlemcen +213 43 21 11 11, Gare SNTF Tlemcen +213 555 76 89 23, Yassir Tlemcen +213 550 71 49 14, Rakba Oran +213 542 77 50 57, EURL Taxi Speed Amir Tiaret +213 660 66 22 60, Station Taxis Zenata Airport Tlemcen +213 542 86 55 00, Taxi Nou Chlef +213 560 02 40 24, Amane Taxi Tlemcen +213 772 30 23 17, Gare Routiere Sougueur +213 666 82 35 03. `update_operator_contacts.py`, `seed_operators.py` (auto-generated from DB)
- **Backend hardening** (7 commits, full audit):
  - **Dead code removal** (`87f77ba`): Deleted tracked `app/config.py` (hardcoded creds, 0 importers)
  - **JWT key persistence** (`d143945`): Ephemeral per-process Ed25519 keys → persisted to gitignored `secrets/jwt_ed25519.pem` (mode 600) for multi-worker/restart stability
  - **Storage hardening** (`e58dc5a`): `_sniffs_as_image` magic-byte validation (JPEG/PNG/WebP), content-type allowlist, honors `minio.public_url` config
  - **i18n cleanup** (`3a305b1`): Removed dead gettext scaffolding (empty locale dirs), rewrote `i18n.py` to honest locale detection + `Content-Language` header
  - **Test fix** (`9135b8f`): Stale `test_plan_route_no_route` mocked wrong dependency (`TransitRoutingService.find_route` vs `PoiTransitRouter.route_to`), AsyncMock leaked un-awaited coroutine → ResponseValidationError. Now mocks with real `RoutePlan`
  - **`.env.example` sync** (`ffda0b4`): DB port 5432→5434, MinIO 9000→19000 + `MINIO__PUBLIC_URL`, JWT comment updated (key persists to `secrets/jwt_ed25519.pem`)
  - **Docker hardening** (`8d9355b`): `--forwarded-allow-ips "*"` → env-configurable `FORWARDED_ALLOW_IPS` (empty default = loopback only; prevents X-Forwarded-For spoofing to bypass rate limits). DB container `user: "0:0"` → `"70:70"` (matches postgres:16-alpine UID; root got EPERM on chmod)
  - **Dependency set restored** (`11ea18b`): anaconda3 env was lost in disk cleanup → rebuilt with **uv + Python 3.12** (`uv venv --python 3.12 .venv && uv pip install -r requirements.txt -r requirements-dev.txt`). Fixed requirements.txt: added `pydantic-ai==2.22.0` (runtime dep, was missing), `cryptography==50.0.0` (`pyjwt[cryptography]` is a no-op in 2.x), bumped uvicorn 0.34→0.52, pyjwt 2.9→2.13, redis 5.3→8.1 (consistent resolving set). New `requirements-dev.txt`: pytest 8.3.5 + pytest-asyncio 0.25.3 (1.x ignores conftest's session `event_loop` fixture → cross-loop asyncpg errors)
  - **Settings env prefix** (`5a920a8`): `Settings` now uses `env_prefix="ATHAR_"` — a bare `AGENT=1` (agent/CI runtimes) crashed boot (collided with the `agent` field) and `DEBUG=1` silently flipped debug. **All env vars renamed**: `ATHAR_DATABASE__URL`, `ATHAR_MINIO__ENDPOINT`, `ATHAR_AUTH__JWT_PRIVATE_KEY`, etc. (`.env`, `.env.example`, docker-compose api service, docs updated). Scripts reading raw `DATABASE_URL` via `os.environ` are unaffected
  - **Infra health fixes**: base compose no longer publishes redis on 6379 (clashed with host's SSH tunnel) — redis is internal-only, override maps `127.0.0.1:6381` for local dev; `.env`/`.env.example` point local runs at redis `localhost:6381`, empty password (container runs no requirepass). Qdrant healthcheck used `curl` (absent from the image) → permanently unhealthy → blocked `depends_on: service_healthy`; replaced with a bash `/dev/tcp` HTTP check on `/healthz` (bash is present). All four containers now report healthy.
  - **Audit findings** (no changes needed): `limiter.py` (in-memory fallback intentional), `harness.py:186` (harmless cost estimate), `admin.py` (all admin-gated), `twilio.py` (graceful fallback), `logging.py` (structlog), `auth.py` (hashed refresh tokens, rate limits, secure OTP — no passwords), `embeddings.py`/`vector_search.py` (graceful fallbacks), agents (no hardcoded keys), tests (isolated `athar_test` DB)
  - **CI fix** (`2de7492`): workflow installed unpinned pytest-asyncio (1.x ignores the conftest `event_loop` fixture → cross-loop asyncpg errors). Now installs `requirements-dev.txt` (pins pytest-asyncio==0.25.3, pytest-cov, httpx). Env vars renamed to `ATHAR_` prefix; dropped never-read `REDIS__URL`/`AUTH__JWT_SECRET`/`DEBUG` (defaults match CI's postgres/redis services).
  - **Repo hygiene** (`1a0255d`): stopped tracking `.coverage` binary + gitignored it and `htmlcov/`. No hardcoded secrets in `scripts/` — enrichment scripts read the vLLM key from `settings`.
  - **Vector search live** (`6272c3d`, `bfd4d48`, `bfa3b7f`, `4df76c9`): `/pois/search` + `/experiences/search` return real hits. Fixed `UnboundLocalError` 500 (function-local imports shadowed module-level models); startup indexing now batched (256), idempotent (skip when `qdrant count ≥ DB count`), and the embedder loads `local_files_only=True` (ONNX) instead of blocking on HF retries; qdrant server aligned to client (compose image `v1.12.6`→`v1.18.2`, volume recreated, collections rebuilt: 52,685 POIs + 1,826 experiences — derived-only, safe to wipe); embedding model pre-warmed in a background task at boot so first search is fast (verified 8s vs ~25s block).
  - **Search ranking: named-first** (`c487404`, `f72e1e9`, `ef133e6`): 41,505 of 52,685 POIs (~79%) have literal placeholder names like `Ruins (non nommé)` whose generic descriptions embed well, so queries like "roman ruins Timgad" returned unnamed ruins on top. Index payload now carries a `has_name` bool (`has_real_name()`); Qdrant query is two-pass (named-only filter first via `MatchValue` — `Match` is a Union alias in client 1.18.0 and cannot be instantiated — then fills from the full index so unnamed POIs stay discoverable); SQL full-text fallback orders real names before placeholders. Bulk index also got an explicit 180s client timeout (60s default aborted a rebuild mid-way under CPU contention).
- **Security audit vs OWASP/NIST** (`SECURITY_STANDARDS.md`, 6 fixes + 11 tests, 224 total → 270 with agent-resilience suite):
  - **Critical — admin escalation blocked** (`c3a2971`): `PUT /users/me/role` accepted any `USER_ROLES` incl. `admin` → any user could become admin. Now restricted to `SELF_ASSIGNABLE_ROLES` (traveler/guide/agency/hotel) in schema + endpoint; mass-assignment path (`PUT /users/me`) verified benign.
  - **High — OTP brute-force/SMS-abuse** (`1a219a0`): per-phone lockout (5 wrong attempts invalidates code), `secrets.compare_digest` constant-time compare, per-phone send throttle (3/10min) on fallback.
  - **High — refresh-token replay** (`5b603b2`): presenting a revoked token now revokes the entire token family (theft detection, per OWASP).
  - **Medium — deactivated accounts** (`a77a38f`): `get_current_user`/optional now reject `is_active=False`.
  - **Medium — API surface lock-down** (`4356719`): `/docs`, `/redoc`, `/openapi.json` gated behind `debug` (API9); `allowed_hosts` default `["*"]` → loopback only (`ATHAR_ALLOWED_HOSTS` JSON override, `.env.example`/compose/docs updated, conftest pre-sets it); headers now include CSP `default-src 'none'; frame-ancestors 'none'`, HSTS (prod), `Cache-Control: no-store` on `/auth/*` + `/users/me`.
  - **Medium — shared rate limiting** (`714111c`): method-level sliding-window counter now Redis-backed (sorted-set, shared across workers) with in-memory fallback + fail-open.
- **Complete API documentation** (`0374699`→`26b1d6c`, 6 commits): `docs/specs/api.md` rewritten from the live OpenAPI inventory — **112 operations / 87 paths** (was stale at 106/81). Added missing routes (agent transport/events/sessions, admin/agent/stats, transport/route-to-poi, discover/experiences/by-poi), per-endpoint auth scopes read from code (public/optional/auth/provider-admin/admin — `[PUB]`/`[AUTH]` markers are unreliable since security only renders for OAuth2), and updated security docs. Every endpoint now carries an OpenAPI `summary`, `description`, and `responses=` error contract. Verified: schema builds clean, 0/112 ops missing a summary, **224 tests pass**.

### Blocked
- **Wasly.app REST API** is partner-only (B2B request required) — bus data publicly unavailable
- **Wasly SNTF schedule API** returns 404 without authentication
- **SNTF.dz website** times out via curl (Joomla site, server-side rendering only)
- **No GTFS feeds** for any Algerian city
- **No intercity coach routes in OSM** — OSM has zero `route=coach` relations for Algeria. SOGRAL network is unmapped. Only 2 SOGRAL bus stop nodes exist on OSM.

## Key Decisions
- OSM POI extraction uses bounding box queries per wilaya (center ±radius) — 53,948 POIs across all 58 wilayas
- POI classification uses OSM tags mapped to DB schema categories
- Hotels/guesthouses/hostels/camp_sites from OSM go to `stays` table, not `pois`
- POI descriptions enriched from Wikidata (where available) + auto-generated from OSM tags
- Schedule data stored both as nested `schedule` dict and top-level fields via `clean_schedule_data.py`
- Checkpointed extraction (per-wilaya files) to survive timeouts/rate limits

## Next Steps
1. ~~⬜ **Migrate Wikimedia photos to MinIO**~~ — **DONE**: 9,059 POIs migrated to MinIO; **0 Wikimedia URLs remain** in DB (Aug 2026 full pass: spatial +3,870, commons +62, remaining +227, more2 exhausted, category-walk +161)
2. **⬅️ More photos for remaining historical/cultural POIs**: 9,059 POIs have real MinIO photos; 43,626 have generated placeholders — Wikidata/Commons name+spatial matching + category walks exhausted; next lever is user-generated content or travel photo collections
3. ~~⬜ **Expand schedule/pricing**~~ — **DONE**: 854/855 transport lines have schedule + pricing data (walking excluded)
4. ~~⬜ **Add operator contacts for remaining wilaya taxi unions + major transport operators**~~ — **DONE**: 152 operators, 86 with real phones. Taxi: 95 syndicates/companies, 29 with real phones (up from 9). All 15 gobytaxi numbers verified on live pages. Added Air Algérie (22 agencies + Contact Center + Oran sub-agencies), SNTF (8 + Oran station phone), SOGRAL gares (2), ENTMV ferry (5), SETRAM (7 units — all with direct operational phones from setram.dz), taxi/VTC (22 via gobytaxi.com + guideoran.com), travel agencies (2). Fixed placeholder numbers on SOGRAL, ENTV, SNTF, ETUSA. `seed_operators.py` (auto-generated from DB)
5. ~~⬜ **More fun facts via GenAI**~~ — **DONE**: **3,796/52,997 POIs** have fun facts (22 Wikidata/Wikipedia + 3,774 GenAI via vLLM Gemma 4). Second pass enriched +1,030 with 0 errors.
6. ⬜ **Frontend** — the API is complete with ~125+ routes, 5 agent endpoints with multi-turn memory; needs a mobile/web frontend to be actually usable

## Critical Context
- Project is a full-stack FastAPI app (`athar-os-prototype/`) with PostgreSQL + Qdrant + MinIO + Redis
- All tourism tables now populated with real OSM and curated data
- **API routes** (270 passing tests): `/api/v1/pois`, `/stays`, `/experiences`, `/discover`, `/trips`, `/favorites`, `/collections`, `/artisans`, `/auth`, `/users`, `/admin`, `/providers`, `/agent/sessions`
- POI responses include TripAdvisor-style fields: ranking, price_level, suggested_duration_min, photo_urls[], subtype, name_ar/name_en, is_featured, average_score, total_reviews, fun_fact
- Vector search (Qdrant) configured but needs Docker running to work
- App has trip optimizer combining POIs + transport + stays + restaurants + experiences, now wired to POI graph for walking times
- **POI graph service**: 34,787 tourism POIs, 535,237 walking edges. Tour optimization works: Oran 9 POIs (4.1km), Tlemcen 10 (2.3km), Algiers 10 (3.2km), Blida 9 (0.8km), Batna 9 (5.5km), Constantine 7 (1.2km)
- MultiModalRouter loads 444 multi-wilaya transport lines with 3,918 adjacency edges
- **Fun facts enrichment**: **3,796 POIs** with real fun facts — 22 from Wikidata/Wikipedia (Timgad, Casbah, Fort Santa Cruz, etc.) + 3,774 generated via vLLM Gemma 4 (97.9% success rate)
- **Operator contacts**: **152 transport operators, 86 with real phones**. All 12 SETRAM units have verified operational phones (from setram.dz). Covers all modes: flight (22 Air Algérie agencies + Contact Center 3302), train (11 SNTF + Oran station phone 041 40 15 02), bus (6 SOGRAL + ETUSA + ETO + NEDJMA), taxi (95 syndicates/companies/agencies, 29 with phones — 15 from gobytaxi.com, all verified on live pages), tram (12 SETRAM units + line entries), ferry (5 ENTMV), cablecar (1). Key verified numbers: SOGRAL +213 21 77 00 66, SNTF +213 21 71 15 10, Air Algérie Contact Center +213 21 98 63 63 (3302), ETUSA +213 21 66 74 14 / Call Center 0770 10 10 68, TaxiAlger +213 772 15 87 94, SETRAM Oran +213 659 56 20 05 / +213 561 66 93 19, SETRAM Mostaganem +213 551 24 24 24.
- Seed scripts live in `scripts/data/`: `seed_pois_db.py`, `seed_providers.py`, `seed_stays_db.py`, `seed_experiences_db.py`, `seed_more_experiences.py`, `enrich_poi_descriptions.py`, `enrich_fun_facts.py`, `enrich_fun_facts_genai.py`, `migrate_photos_minio.py`, `extract_osm_artisans.py`, `seed_taxi_contacts.py`
- **Agent memory system**: `app/models/agent_memory.py` (AgentSession, AgentMemory), `app/agents/memory_service.py` (get_or_create_session, load_message_history, remember, recall), `app/agents/memory_tools.py` (remember/recall tools), `alembic/versions/ef64db5de951_add_agent_memory.py`, `tests/test_memory.py` (21 tests)
- **Agent resilience stack**: `app/agents/resilience.py` (retry transport, `run_agent_safely`, usage limits, `tool_call_names`), wired into `app/agents/travel_agent.py` (retries/tool_timeout), `app/api/v1/endpoints/agents.py` (503 on breaker/timeout), `app/agents/eval.py`, `tests/test_agent_robustness.py` (46 tests)

## Relevant Files
- `app/data/poi_nodes_enriched.json`: 53,948 standalone POI nodes
- `app/data/poi_edges_enriched.json`: 15,580 walking edges POI↔transit
- `app/data/transit_nodes_enriched.json`: 57,743 nodes (2,502 wilaya-fixed)
- `app/data/transit_edges_enriched.json`: 30,957 edges
- `app/data/osm_artisans.json`: 3,744 OSM artisan shops (gitignored, force-added)
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
- `scripts/data/extract_osm_artisans.py`: OSM artisan extraction + DB seeding (3,744 artisans)
- `scripts/data/insert_osm_bus_stations.py`: OSM bus_station import (425 new stations)
- `scripts/data/organize_transport.py`: Taxi/SOGRAL/inter-city routes + DB seeding
- `scripts/data/fix_missing_wilaya.py`: Assign wilaya to transit nodes via reverse geocoding
- `scripts/data/enrich_phase_a.py`: Rankings, price level, duration, POI↔experience links
- `scripts/data/enrich_photos_bulk.py`: Photo enrichment via Wikidata SPARQL matching
- `scripts/data/enrich_photos_more.py`: Enhanced photo enrichment (SPARQL + Commons API)
- `scripts/data/enrich_fun_facts.py`: Fun facts from Wikidata + OSM tags + category templates
- `scripts/data/migrate_photos_minio.py`: Wikimedia photo → MinIO migration
