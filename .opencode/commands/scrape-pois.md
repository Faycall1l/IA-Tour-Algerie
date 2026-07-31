---
description: Scrape more POI data from real sources (OSM, Wikidata, Commons, GeoAlgeria) to fill gaps in photos, descriptions, fun facts, pricing, opening hours, or contact info.
---

Your task: scrape more POI data for ATHAR — the agentic travel guide for Algeria.

**What you're working with:**
- 52,997 POIs in the `pois` table across all 58 wilayas
- 8,533 have real MinIO photos (16.1%), 44,464 have category placeholders
- 2,911 have fun facts (5.5%), rest are NULL
- All have descriptions (100%), but many are auto-generated from OSM tags
- 39,102 have entry fees, but many are estimates
- 294 have operator info, 4,122 have Arabic names, 11,300 have English names
- 0 have real opening hours scraped — all are from OSM tags (spotty)

**Backend context (consult these always):**
- POI schema: `app/models/poi.py` (35+ columns), `app/schemas/poi.py` (POICreate/POIUpdate shapes)
- POI API: `app/api/v1/endpoints/pois.py` (create, update, bulk operations)
- DB spec: `docs/specs/database.md` (POI table at line 73)
- Existing enrichment scripts: `scripts/data/enrich_*.py`
- Constraints: NO synthetic/fictional data — every record must come from a real, verifiable source

**The user wants:** $ARGUMENTS

**Your workflow:**
1. Read `app/models/poi.py` and `app/schemas/poi.py` to understand required fields and validation
2. Query the DB to understand the current gap (which fields are NULL, which POIs need enrichment)
3. Identify the best real data source for the gap:
   - **Photos**: Wikimedia Commons via Wikidata SPARQL or Wikipedia pageimage API
   - **Descriptions**: Wikidata entity labels/descriptions, Wikipedia extracts
   - **Fun facts**: Wikidata properties (P18, P569, P571, etc.) or GenAI from real sources
   - **Opening hours**: OSM tags or operator websites
   - **Pricing**: Operator websites, travel blogs, official tourism sites
   - **Contact info**: Operator websites, Wikidata (P1329, P6375), Yellow Pages
   - **Arabic names**: Wikidata native labels (`wdt:P1705`), OSM `name:ar` tags
   - **English names**: Wikidata labels, OSM `name:en` tags
   - **New POIs**: OSM Overpass API queries for missing categories per wilaya
   - **Operator/phone**: Websites, Wikidata, gobytaxi.com, official directories
4. Write a Python script in `scripts/data/` following existing patterns:
   - Async SQLAlchemy session, batch operations (500-1000 per commit)
   - Checkpointing to survive API timeouts/rate limits
   - `if __name__ == "__main__": asyncio.run(main())` pattern
   - Logging with `logging.basicConfig(level=logging.INFO)`
5. Run the script with `python -m scripts.data.YOUR_SCRIPT`
6. Verify the DB was updated correctly with SQL queries
7. Update `AGENTS.md` "Done" section and commit with a descriptive message

**Key constraints:**
- NEVER seed fictional/synthetic data — every record from real verifiable sources
- Use `enrich_*` naming convention for enrichment scripts, `seed_*` for new records
- Handle rate limits (Wikimedia 429, Wikidata throttling, OSM Overpass fair use)
- Batch DB updates with commits after each batch
- Respect the POI schema — all required fields must be provided
- POIs with OSM `tourism=hotel/guest_house/hostel/camp_site` go to `stays` table, not `pois`
