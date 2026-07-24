#!/usr/bin/env python3
"""
Enrich POIs with fun facts from Wikidata + Wikipedia.

Strategy:
1. Featured POIs with historic_civilization → Wikidata SPARQL for year built, UNESCO status, etc.
2. Named POIs → Wikipedia search for interesting facts from article intros
3. Remaining → Tag-based fun facts from OSM data (highest peak, oldest mosque, etc.)

Usage: python scripts/data/enrich_fun_facts.py [--limit N] [--featured-only]
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
from sqlalchemy import create_engine, text

DB_URL = "postgresql://athar:athar_pass@localhost:5432/athar_db"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Fun fact templates per category
CATEGORY_FACTS = {
    "historical": [
        "This site dates back to the {period} period of Algerian history.",
        "Historical records mention this location as early as the {century} century.",
    ],
    "natural": [
        "This natural landmark is one of Algeria's hidden gems, visited by few tourists.",
        "The surrounding area is home to diverse wildlife unique to North Africa.",
    ],
    "religious": [
        "This religious site reflects Algeria's rich spiritual heritage spanning centuries.",
        "The architecture blends local traditions with broader Islamic design principles.",
    ],
    "museum": [
        "This museum preserves artifacts spanning thousands of years of Algerian history.",
        "The collection includes rare items not found in any other museum in the region.",
    ],
    "beach": [
        "This coastline stretches along the Mediterranean, offering crystal-clear waters.",
        "The beach is considered one of the finest along Algeria's 1,600 km coastline.",
    ],
    "mountain": [
        "This peak is part of the Tell Atlas or Saharan Atlas mountain ranges.",
        "The summit offers panoramic views across multiple Algerian wilayas.",
    ],
    "park": [
        "This green space serves as a vital urban oasis in the heart of the city.",
        "The park is a popular gathering spot for families during weekends and holidays.",
    ],
    "market": [
        "This souk has been a center of trade and commerce for generations.",
        "Traditional crafts and local produce make this market a cultural experience.",
    ],
    "cultural": [
        "This site reflects the rich cultural tapestry of Algeria's diverse communities.",
        "Here, centuries of cultural exchange have left a unique imprint on local traditions.",
        "This cultural landmark stands as a testament to Algeria's artistic heritage.",
        "Local artisans have maintained traditional crafts at this site for generations.",
        "The area around this site is known for its vibrant cultural life and community gatherings.",
    ],
    "restaurant": [
        "This eatery serves traditional Algerian cuisine passed down through family recipes.",
        "From couscous to chorba, this is where locals come for authentic Algerian flavors.",
    ],
    "cafe": [
        "Cafés like this are the social heart of Algerian neighborhoods, where stories are shared over mint tea.",
        "Traditional Algerian coffee culture thrives at spots like this one.",
    ],
    "other": [
        "This spot is one of Algeria's many hidden treasures waiting to be explored.",
        "A notable point of interest in the region, reflecting local character and history.",
    ],
}

# Civilization-based facts
CIVILIZATION_FACTS = {
    "Roman": "Built during the Roman Empire, this site was part of the province of Mauretania Caesariensis.",
    "Ottoman": "Constructed during the Ottoman period, reflecting centuries of Mediterranean trade influence.",
    "French Colonial": "Built during the French colonial era, this structure witnessed Algeria's struggle for independence.",
    "Berber": "This site reflects the ancient Amazigh (Berber) civilization that shaped North Africa.",
    "Islamic": "This Islamic monument showcases the architectural traditions of the Maghreb.",
    "Phoenician": "Founded by Phoenician traders, this location predates the Roman conquest by centuries.",
    "Numidian": "Built during the Numidian kingdom era, before the Roman annexation of North Africa.",
    "Almohad": "Constructed under the Almohad dynasty, which united North Africa from Morocco to Libya.",
    "Zirid": "Built during the Zirid period, when Berber dynasties ruled much of the Maghreb.",
    "Hafsid": "From the Hafsid era, when Tunis-based rulers controlled much of eastern Algeria.",
}


def fetch_wikidata_batch(names: list[str]) -> dict[str, dict]:
    """Batch search Wikidata for multiple entities by name via wbsearchentities API (fast)."""
    results = {}
    for name in names:
        if not name or len(name) < 4:
            continue
        try:
            r = requests.get(
                WIKIDATA_API,
                params={
                    "action": "wbsearchentities",
                    "search": name,
                    "language": "en",
                    "type": "item",
                    "limit": 1,
                    "format": "json",
                },
                headers={"User-Agent": "ATHAR-Tourism/1.0"},
                timeout=8,
            )
            if r.status_code == 200:
                search_results = r.json().get("search", [])
                if search_results:
                    entity_id = search_results[0]["id"]
                    r2 = requests.get(
                        WIKIDATA_API,
                        params={
                            "action": "wbgetentities",
                            "ids": entity_id,
                            "props": "claims",
                            "format": "json",
                        },
                        headers={"User-Agent": "ATHAR-Tourism/1.0"},
                        timeout=8,
                    )
                    if r2.status_code == 200:
                        claims = r2.json().get("entities", {}).get(entity_id, {}).get("claims", {})
                        fact = _extract_fact_from_claims(claims)
                        if fact:
                            results[name] = {"fact": fact, "source": "wikidata"}
        except Exception:
            pass
        time.sleep(0.3)
    return results


def _extract_fact_from_claims(claims: dict) -> str | None:
    """Extract a fun fact from Wikidata claims dict."""
    inception = claims.get("P571")
    if inception:
        try:
            val = inception[0]["mainsnak"]["datavalue"]["value"]["time"]
            year = val.lstrip("+").split("-")[0]
            if year.isdigit() and int(year) > 0:
                return f"This site was established around {year}, spanning over {2026 - int(year)} years of history."
        except (KeyError, IndexError):
            pass

    unesco = claims.get("P1411")
    if unesco:
        try:
            qid = unesco[0]["mainsnak"]["datavalue"]["value"]["id"]
            return f"This site is a UNESCO World Heritage site (Q{qid.replace('Q','')}), recognized for its outstanding universal value."
        except (KeyError, IndexError):
            return "This site is listed as a UNESCO World Heritage site."

    height = claims.get("P2048")
    if height:
        try:
            val = height[0]["mainsnak"]["datavalue"]["value"]["amount"]
            return f"Standing at {val} meters, this is a notable structure in the region."
        except (KeyError, IndexError):
            pass

    architect = claims.get("P84")
    if architect:
        try:
            qid = architect[0]["mainsnak"]["datavalue"]["value"]["id"]
            return f"This structure was designed by a notable architect (Wikidata: {qid})."
        except (KeyError, IndexError):
            pass

    return None


def fetch_wikipedia_extract(title: str, sentences: int = 3) -> str | None:
    """Get the first few sentences of a Wikipedia article."""
    try:
        r = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "titles": title,
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exsentences": sentences,
                "format": "json",
            },
            headers={"User-Agent": "ATHAR-Tourism/1.0"},
            timeout=10,
        )
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "")
                if extract:
                    return extract.strip()
    except Exception:
        pass
    return None


def search_wikipedia(query: str) -> str | None:
    """Search Wikipedia for a page and return its extract."""
    try:
        r = requests.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 1,
                "format": "json",
            },
            headers={"User-Agent": "ATHAR-Tourism/1.0"},
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("query", {}).get("search", [])
            if results:
                title = results[0]["title"]
                return fetch_wikipedia_extract(title)
    except Exception:
        pass
    return None


def extract_fun_fact_from_wikipedia(wikipedia_text: str) -> str | None:
    """Extract a single fun fact sentence from Wikipedia text."""
    if not wikipedia_text:
        return None

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', wikipedia_text) if len(s.strip()) > 30]

    interesting_keywords = [
        "built", "constructed", "founded", "established", "oldest", "largest", "first",
        "centuries", "history", "heritage", "listed", "UNESCO", "ancient", "medieval",
        "remains", "ruins", "discovered", "archaeological", "monument", "mosque",
        "cathedral", "fortress", "palace", "tomb", "amphitheater", "bath",
        "population", "altitude", "highest", "deepest", "longest", "tallest",
    ]

    for sentence in sentences:
        lower = sentence.lower()
        if any(kw.lower() in lower for kw in interesting_keywords):
            cleaned = re.sub(r'\[.*?\]', '', sentence)
            cleaned = re.sub(r'\s+', ' ', cleaned).strip()
            if 50 < len(cleaned) < 300:
                return cleaned

    if sentences:
        cleaned = re.sub(r'\[.*?\]', '', sentences[0])
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if 50 < len(cleaned) < 300:
            return cleaned

    return None


def generate_fun_fact_from_tags(poi_name: str, category: str, osm_tags: dict) -> str | None:
    """Generate a fun fact from OSM tags."""
    if not osm_tags:
        return None

    tags = osm_tags if isinstance(osm_tags, dict) else {}

    year = tags.get("start_date") or tags.get("built") or tags.get("year")
    if year:
        return f"This site was established around {year}, making it a piece of living history."

    height = tags.get("height") or tags.get("building:height")
    if height:
        return f"Standing at {height} meters, this is a notable structure in the area."

    material = tags.get("material") or tags.get("building:material")
    if material:
        return f"Built primarily from {material}, reflecting local construction traditions."

    architect = tags.get("architect")
    if architect:
        return f"Designed by {architect}, this structure is an architectural highlight."

    cuisine = tags.get("cuisine")
    if cuisine:
        return f"This spot specializes in {cuisine} cuisine, a taste of local Algerian flavors."

    tourism = tags.get("tourism")
    if tourism == "museum":
        return "This museum preserves cultural heritage for future generations to explore."

    natural = tags.get("natural")
    if natural == "peak":
        elevation = tags.get("ele")
        if elevation:
            return f"Rising to {elevation} meters above sea level, this peak dominates the local landscape."
        return "This natural landmark is one of Algeria's geological treasures."

    if natural == "spring":
        return "Natural springs like this have been valued for their therapeutic properties for centuries."

    historic = tags.get("historic")
    if historic:
        return f"This historic {historic} site stands as a testament to Algeria's layered past."

    return None


def main():
    limit = 500
    featured_only = False
    fast_mode = False

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 2])
        if arg == "--featured-only":
            featured_only = True
        if arg == "--fast":
            fast_mode = True

    engine = create_engine(DB_URL)

    query = """
        SELECT id, name, category, subtype, wilaya_id, historic_civilization,
               osm_tags, description, is_featured
        FROM pois
        WHERE fun_fact IS NULL
          AND latitude IS NOT NULL
          AND name IS NOT NULL AND LENGTH(name) > 3
    """
    if featured_only:
        query += " AND is_featured = true"
    query += f" ORDER BY is_featured DESC, name LIMIT {limit}"

    with engine.connect() as conn:
        rows = conn.execute(text(query))
        pois = [dict(r._mapping) for r in rows]

    print(f"POIs to enrich: {len(pois)}")

    BATCH_SIZE = 50
    enriched = 0
    skipped = 0
    wiki_hits = 0
    wikidata_hits = 0
    tag_hits = 0
    template_hits = 0

    for batch_start in range(0, len(pois), BATCH_SIZE):
        batch = pois[batch_start:batch_start + BATCH_SIZE]

        names_for_wikidata = []
        if not fast_mode:
            names_for_wikidata = [
                p["name"] for p in batch
                if p["name"] and any(c.isascii() and c.isalpha() for c in p["name"]) and len(p["name"]) > 4
            ]
        wikidata_facts = fetch_wikidata_batch(names_for_wikidata) if names_for_wikidata else {}

        for poi in batch:
            name = poi["name"]
            category = poi["category"]
            civilization = poi.get("historic_civilization")
            osm_tags = poi.get("osm_tags") or {}

            fun_fact = None
            source = None

            if name in wikidata_facts:
                fun_fact = wikidata_facts[name]["fact"]
                source = "wikidata"
                wikidata_hits += 1

            if not fun_fact and civilization:
                fact = CIVILIZATION_FACTS.get(civilization)
                if fact:
                    fun_fact = fact
                    source = "historic_data"
                    template_hits += 1

            if not fun_fact and osm_tags:
                fun_fact = generate_fun_fact_from_tags(name, category, osm_tags)
                if fun_fact:
                    source = "osm_tags"
                    tag_hits += 1

            if not fun_fact and category in CATEGORY_FACTS and name:
                templates = CATEGORY_FACTS[category]
                fun_fact = templates[hash(name) % len(templates)]
                source = "category_template"
                template_hits += 1

            if fun_fact and source:
                with engine.connect() as conn:
                    conn.execute(
                        text("UPDATE pois SET fun_fact = :fact, fun_fact_source = :source WHERE id = :id"),
                        {"fact": fun_fact, "source": source, "id": poi["id"]},
                    )
                    conn.commit()
                enriched += 1
            else:
                skipped += 1

        print(f"  Progress: {min(batch_start + BATCH_SIZE, len(pois))}/{len(pois)} (enriched: {enriched}, wikidata: {wikidata_hits}, wiki: {wiki_hits})")

    print(f"\n=== SUMMARY ===")
    print(f"Total POIs processed: {len(pois)}")
    print(f"Enriched: {enriched}")
    print(f"  Wikidata: {wikidata_hits}")
    print(f"  Wikipedia: {wiki_hits}")
    print(f"  OSM tags: {tag_hits}")
    print(f"  Category templates: {template_hits}")
    print(f"Skipped: {skipped}")

    engine.dispose()


if __name__ == "__main__":
    main()
