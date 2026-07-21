"""Bulk Wikidata enrichment: descriptions, photos, phone, website, opening_hours.

Fetches ALL tourism-relevant Wikidata entities in Algeria (historic sites,
museums, natural features, cultural heritage, etc.) via SPARQL, then matches
them to local POIs by name (fr/ar/en) and osm_node_id cross-reference.

This is the most comprehensive Wikidata sweep we can do.
"""

import asyncio
import logging
import re

import aiohttp
from sqlalchemy import func, select, update

from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "ATHAR-OS/0.3 (data-collector; faycal@athar.dz) aiohttp/3"
CHUNK_SIZE = 500

SPARQL_QUERY = """
SELECT ?item ?itemLabel ?itemLabelAr ?itemLabelEn ?description ?descriptionFr ?descriptionEn
       ?phone ?website ?hours ?commonsImage ?coord ?osmNode ?article
WHERE {
  ?item wdt:P17 wd:Q262 .           # country: Algeria
  ?item wdt:P31/wdt:P279* ?type .   # instance/subclass of something
  FILTER(?type IN (
    wd:Q570116,   # historic site
    wd:Q33506,    # museum
    wd:Q16970,    # heritage site
    wd:Q41176,    # tourist attraction
    wd:Q133932,   # cultural property
    wd:Q23446,    # palace
    wd:Q16560,    # tomb
    wd:Q41177,    # archaeological site
    wd:Q839954,   # archaeological site (more specific)
    wd:Q811534,   # natural monument
    wd:Q109607,   # provincial park
    wd:Q2385804,   # museum building
    wd:Q1067166,  # geography
    wd:Q10742,    # mountain
    wd:Q47521,    # mountain range
    wd:Q22698,    # national park
    wd:Q108325,   # garden
    wd:Q23397,    # lake
    wd:Q165,     # beach
    wd:Q16521,   # bay
    wd:Q23401,   # cave
    wd:Q23393,   # waterfall
    wd:Q473972,  # oasis
    wd:Q171810,  # hot spring
    wd:Q378575,  # mosque
    wd:Q107648,  # church
    wd:Q16917,   # cathedral
    wd:Q182531,  # shrine
    wd:Q169565,  # zaouia
    wd:Q34627,   # theatre
    wd:Q1785071, # art museum
    wd:Q643126,  # national museum
    wd:Q625894,  # cultural centre
    wd:Q367443,  # public library
    wd:Q837323,  # market hall
    wd:Q1641634, # lighthouse
    wd:Q222538,  # dam
    wd:Q1197775  # randonnée
  ))
  OPTIONAL { ?item wdt:P1329 ?phone . }           # phone number
  OPTIONAL { ?item wdt:P856 ?website . }          # official website
  OPTIONAL { ?item wdt:P3027 ?hours . }           # opening hours
  OPTIONAL { ?item wdt:P18 ?commonsImage . }      # Commons image
  OPTIONAL { ?item wdt:P625 ?coord . }            # coordinates
  OPTIONAL { ?item wdt:P11693 ?osmNode . }        # OSM node ID (direct ref)
  OPTIONAL { ?item schema:description ?description . FILTER(LANG(?description) = 'fr') }
  OPTIONAL { ?item schema:description ?descriptionEn . FILTER(LANG(?descriptionEn) = 'en') }
  OPTIONAL { ?item schema:description ?descriptionFr . FILTER(LANG(?descriptionFr) = 'fr') }
  OPTIONAL { ?article schema:about ?item ; schema:isPartOf <https://fr.wikipedia.org/> . }
  SERVICE wikibase:label { bd:serviceParam wikibase:language 'fr,en,ar'. }
}
LIMIT 20000
"""

# Category mapping from Wikidata type to POI category
WD_CATEGORY_MAP: dict[str, str] = {
    # Historic / Heritage
    "Q570116": "historical", "Q16970": "historical", "Q41177": "historical",
    "Q839954": "historical", "Q16560": "historical", "Q23446": "historical",
    # Museums
    "Q33506": "museum", "Q1785071": "museum", "Q643126": "museum",
    # Cultural
    "Q133932": "cultural", "Q41176": "cultural", "Q34627": "cultural",
    "Q625894": "cultural", "Q367443": "cultural", "Q837323": "market",
    "Q1197775": "cultural",
    # Natural
    "Q811534": "natural", "Q1067166": "natural", "Q10742": "mountain",
    "Q47521": "mountain", "Q22698": "park", "Q108325": "park",
    "Q23397": "natural", "Q16521": "natural", "Q23401": "natural",
    "Q23393": "natural", "Q473972": "natural", "Q171810": "natural",
    # Religious
    "Q378575": "religious", "Q107648": "religious", "Q16917": "religious",
    "Q182531": "religious", "Q169565": "religious",
    # Beach
    "Q165": "beach",
    # Infrastructure
    "Q1641634": "other", "Q222538": "other",
}


def _normalize(name: str) -> str:
    name = re.sub(r"[\(\)\[\]\{\},\.!?;:'\"«»-]", " ", name)
    name = re.sub(r"\s+", " ", name).strip().lower()
    return name


def build_wikidata_index(wd_items: list[dict]) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    """Build OSM-node-ID → item and normalized-name → [items] indexes."""
    osm_index: dict[str, dict] = {}
    name_index: dict[str, list[dict]] = {}

    for item in wd_items:
        # OSM node index
        osm_node = item.get("osmNode", "")
        if osm_node:
            osm_index[osm_node] = item

        # Name index (by each available label)
        for label_key in ("itemLabel", "itemLabelAr", "itemLabelEn"):
            label = item.get(label_key, "")
            if label:
                key = _normalize(label)
                if key:
                    name_index.setdefault(key, []).append(item)

    return osm_index, name_index


def _match_poi_fast(
    poi: POI,
    osm_index: dict[str, dict],
    name_index: dict[str, list[dict]],
) -> dict | None:
    """Match a POI to Wikidata using pre-built indexes (O(1) lookups)."""
    # 1. OSM node ID match
    if poi.osm_node_id:
        item = osm_index.get(str(poi.osm_node_id))
        if item:
            return item

    # 2. Exact name match
    pn = _normalize(poi.name or "")
    if pn:
        candidates = name_index.get(pn)
        if candidates:
            return candidates[0]

    return None


async def fetch_wikidata_entities(session: aiohttp.ClientSession) -> list[dict]:
    """Fetch all tourism-relevant Wikidata entities in Algeria."""
    logger.info("Fetching Wikidata entities (this may take 30-60s)...")
    async with session.get(
        SPARQL_URL,
        params={"query": SPARQL_QUERY, "format": "json"},
        timeout=aiohttp.ClientTimeout(total=120),
    ) as resp:
        if resp.status != 200:
            logger.error("Wikidata SPARQL returned %d", resp.status)
            return []
        data = await resp.json()
        bindings = data.get("results", {}).get("bindings", [])
        logger.info("Got %d entities from Wikidata", len(bindings))

        items = []
        for b in bindings:
            item = {
                "id": b.get("item", {}).get("value", ""),
                "itemLabel": b.get("itemLabel", {}).get("value", ""),
                "itemLabelAr": b.get("itemLabelAr", {}).get("value", ""),
                "itemLabelEn": b.get("itemLabelEn", {}).get("value", ""),
                "description": b.get("description", {}).get("value", "")
                            or b.get("descriptionFr", {}).get("value", ""),
                "descriptionEn": b.get("descriptionEn", {}).get("value", ""),
                "phone": b.get("phone", {}).get("value", ""),
                "website": b.get("website", {}).get("value", ""),
                "hours": b.get("hours", {}).get("value", ""),
                "commonsImage": b.get("commonsImage", {}).get("value", ""),
                "coord": b.get("coord", {}).get("value", ""),
                "osmNode": b.get("osmNode", {}).get("value", ""),
                "article": b.get("article", {}).get("value", ""),
            }
            items.append(item)
        return items


async def main():
    headers = {"User-Agent": USER_AGENT, "Accept": "application/sparql-results+json"}
    async with aiohttp.ClientSession(headers=headers) as session:
        wd_items = await fetch_wikidata_entities(session)

    if not wd_items:
        logger.error("No Wikidata entities fetched")
        return

    async with async_session() as db:
        total = (await db.execute(select(func.count()).select_from(POI))).scalar() or 0

        # All POIs
        result = await db.execute(
            select(POI).where(
                (POI.description.is_(None)) | (func.length(POI.description) < 80) | POI.phone.is_(None) | POI.website.is_(None)
            ).order_by(POI.is_featured.desc())
        )
        pois = result.scalars().all()

    logger.info("Building Wikidata indexes...")
    osm_index, name_index = build_wikidata_index(wd_items)
    logger.info("Indexes built: %d OSM nodes, %d names", len(osm_index), len(name_index))

    matched = 0
    enriched_descriptions = 0
    enriched_phone = 0
    enriched_website = 0
    enriched_hours = 0
    enriched_photos = 0

    async with async_session() as db:
        for i, poi in enumerate(pois):
            match = _match_poi_fast(poi, osm_index, name_index)
            if not match:
                continue

            matched += 1
            updates = {}

            # Description (only if current is short/auto-generated)
            desc = match.get("description", "")
            if desc and len(desc) > 50:
                if not poi.description or len(poi.description) < 80:
                    updates["description"] = desc
                    enriched_descriptions += 1

            # Phone
            phone = match.get("phone", "")
            if phone and not poi.phone:
                updates["phone"] = phone
                enriched_phone += 1

            # Website
            website = match.get("website", "")
            if website and not poi.website:
                updates["website"] = website
                enriched_website += 1

            # Opening hours
            hours = match.get("hours", "")
            if hours and not poi.opening_hours:
                updates["opening_hours"] = hours
                enriched_hours += 1

            # Photo (only if no existing photo)
            photo = match.get("commonsImage", "")
            if photo and not poi.photo_url and not poi.photo_urls:
                # Convert Commons file name to URL
                filename = photo.split("/")[-1].replace("Special:FilePath/", "").replace("File:", "")
                if filename:
                    photo_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{filename}"
                    updates["photo_url"] = photo_url
                    updates["photo_urls"] = [photo_url]
                    enriched_photos += 1

            if updates:
                await db.execute(update(POI).where(POI.id == poi.id).values(**updates))

            if (i + 1) % CHUNK_SIZE == 0:
                await db.commit()
                logger.info(
                    "Processed %d/%d POIs: %d matched | desc=%d phone=%d web=%d hours=%d photos=%d",
                    i + 1, len(pois), matched,
                    enriched_descriptions, enriched_phone, enriched_website,
                    enriched_hours, enriched_photos,
                )

        await db.commit()

    logger.info("=" * 60)
    logger.info("WIKIDATA BULK ENRICHMENT COMPLETE")
    logger.info("=" * 60)
    logger.info("Total Wikidata entities fetched: %d", len(wd_items))
    logger.info("Total POIs processed: %d", len(pois))
    logger.info("Matched: %d", matched)
    logger.info("Descriptions enriched: %d", enriched_descriptions)
    logger.info("Phone numbers added: %d", enriched_phone)
    logger.info("Websites added: %d", enriched_website)
    logger.info("Opening hours added: %d", enriched_hours)
    logger.info("Photos added: %d", enriched_photos)


if __name__ == "__main__":
    asyncio.run(main())
