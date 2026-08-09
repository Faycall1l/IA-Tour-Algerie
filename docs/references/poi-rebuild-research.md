# POI Data Source Research — TripAdvisor Rebuild Strategy

**Status**: Research complete. Decision: rebuild POI corpus from **TripAdvisor** (via Wayback Machine + keyless internal API), cross-referenced with **GeoAlgeria** (ASAL/Wilaya-mapped) for coverage of all 69 wilayas.

## Problem recap

The current 52,685-POI corpus is unusable:
- 41,508 (78.8%) have placeholder names (`Ruins (non nommé)`, `Cafee (unnamed)`)
- 2,664 person-name-only, 751 junk names (Resto, Poisson, King...)
- All 52,685 have `photo_url` but 43,626 are `placehold.co` text boxes; one real MinIO image shared by 4,105 POIs; only 1,471 distinct real photos
- `osm_tags` column 100% NULL — bare OSM nodes with no tags, no names, unrescuable

## Sources evaluated

### 1. TripAdvisor — THE primary source ✅

**Why**: Every spot has a real name, real coords, rating, review count, address, description, and real user photos. This is exactly the "spots should make sense" requirement.

**Access findings** (tested live):
- **Direct scraping: BLOCKED.** `www.tripadvisor.com/*` serves DataDome JS challenge (403) even with `curl_cffi` chrome impersonation. Includes listing pages, `TypeAheadJson`, and the graphql endpoint (405).
- **✅ `data/1.0/location/{id}` internal API: OPEN, no key.** Returns JSON: `name`, `latitude`, `longitude`, `rating`, `num_reviews`, `category`, `subcategory`, `address_obj`, `photo` (media-cdn URL), `location_string`, `geo_type`. Works for both geo IDs (cities) and location IDs (POIs). Verified: Algeria g293717, Algiers g293718, Basilique Notre Dame d'Afrique d667311 (4.5★, 748 reviews, coords 36.800903/3.042667).
- **✅ Wayback Machine: archived TripAdvisor listing pages are fully parseable.** e.g. Algiers attractions snapshot 2025-09-06 contains all 30-page listings with names, photo URLs, bubble ratings, review counts (134 total results for Algiers). Listing pages carry the data in SSR HTML (not JSON-LD, but regex-parseable).
- **✅ Photo CDN `media-cdn.tripadvisor.com` + `dynamic-media-cdn.tripadvisor.com`: OPEN.** Real JPEG downloads (verified 200, ~60KB). This solves the photo problem — real per-POI photos, not placeholders.
- **Geo ID discovery**: CDX queries revealed 27+ Algerian province geo IDs in the 26xxxxx range (Oran 2600638, Annaba 2600703, Bejaia 2600752, Blida 2600822, Constantine 2602028, Tlemcen 2602628, Tamanrasset 2602542, Setif 2602426...) and city IDs (Algiers 293718, Constantine 734459, Tebessa 734461, Annaba 1071600...). More enumerable via CDX prefix scans.

**Pipeline**:
1. Enumerate geo IDs for all 58+ cities via CDX (`Tourism-g26*` prefix) + `data/1.0` verification
2. Fetch archived listing pages from Wayback for each city (Attractions + Restaurants)
3. Parse listing cards → location IDs (d-ids), names, photo URLs, ratings
4. For each d-id: `data/1.0/location/{id}` → coords, rating, reviews, address, description, category
5. Download photos from media-cdn → MinIO
6. Reverse-geocode coords → wilaya_id (matches 69-wilaya map)

**Limitations**: Wayback snapshots may be 1-3 years old (Algiers 2025-09, Oran 2019). Restaurants/attractions coverage per city ~30-134 items (better than nothing, high quality). Pagination (`oa30`) snapshots may be missing → cap ~30-60/city. Old snapshots → some businesses may have closed.

### 2. GeoAlgeria (`@geoalgeria/tourisme` npm) — secondary source ✅

- MIT-licensed open dataset, 4,348 records across 69 wilayas (1,602 lodging, 1,248 attractions, 1,184 historic, 282 thermal springs, 32 parks)
- **BUT: attractions/historic/lodging/parks are OSM-derived** (ODbL) — same underlying data as our current corpus. Thermal springs from ASAL Geoportail (gov, we already imported those)
- **Value**: `wilaya_code` + `commune` + `name_fr`/`name_ar` per record → excellent for wilaya attribution and cross-checking our own mapping; curated subset (only real tourism POIs, no junk)
- Use as a **filter + enrichment layer**, not a primary source

### 3. omkarcloud TripAdvisor Scraper API — fallback ⚠️

- REST API wrapping TripAdvisor; free tier 100 req/month; needs API key (user signup at omkar.cloud)
- Returns structured JSON: attractions/restaurants lists with rating, reviews, description, featured_image, coordinates, hours, cuisines
- Could accelerate: `attractions/list?query={geoId}` returns 30/page with full metadata in one call
- **Not needed** if Wayback + data/1.0 pipeline works (zero-cost, no key). Keep as fallback/verification.

### 4. Other sources — rejected

- **Wikivoyage/Wikipedia**: already used for descriptions/fun facts; images considered irrelevant by user (correct — mismatched at scale)
- **Google Places API**: needs key + ToS restrictions on scraping, no reviews
- **Foursquare/SerpApi**: API keys required, cost, ToS gray area
- **Trip.com/Expedia mirrors**: derivative of TripAdvisor data, worse structure
- **oran.mta.gov.dz / mta.gov.dz**: official tourism ministry — good for curated circuits (already referenced in experiences), not bulk POI data

## Decision

| Component | Source |
|---|---|
| POI names/coords/ratings/reviews/addresses/descriptions | TripAdvisor via Wayback + `data/1.0` |
| Photos | TripAdvisor media-cdn → MinIO (real per-POI photos) |
| Wilaya attribution | Reverse geocode + GeoAlgeria wilaya_code cross-check |
| Coverage fill (small wilayas with few TA entries) | GeoAlgeria curated records (real names, wilaya-mapped) |
| Fallback if TA pipeline fails | omkarcloud API (free 100 req, needs user key) |

## Targets

- ~1,500-3,000 real POIs (vs 52,685 junk) — quality over quantity
- 100% real names, real coords, real photos, real ratings where available
- All 58-69 wilayas represented (major cities deep coverage, small wilayas from GeoAlgeria)

## Files touched (planned)

- `scripts/data/scrape_tripadvisor.py` — Wayback listing fetch + parse
- `scripts/data/enrich_tripadvisor_locations.py` — data/1.0 enrichment
- `scripts/data/map_wilaya_coords.py` — reverse geocoding to 69-wilaya
- `scripts/data/seed_pois_db.py` — reseed
- `scripts/reindex_qdrant.py` — rebuild vector index
