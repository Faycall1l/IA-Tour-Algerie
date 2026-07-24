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


def fetch_wikidata_sparql(entity_name: str) -> dict | None:
    """Search Wikidata for an entity by name and return interesting claims."""
    query = f"""
    SELECT ?item ?itemLabel ?inception ?unescoStatus ?height ?architect ?population WHERE {{
      ?item rdfs:label ?label .
      FILTER(CONTAINS(LCASE(?label), LCASE("{entity_name}")))
      OPTIONAL {{ ?item wdt:P571 ?inception . }}
      OPTIONAL {{ ?item wdt:P1411 ?unescoStatus . }}
      OPTIONAL {{ ?item wdt:P2048 ?height . }}
      OPTIONAL {{ ?item wdt:P84 ?architect . }}
      OPTIONAL {{ ?item wdt:P1082 ?population . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,fr,ar" . }}
    }} LIMIT 1
    """
    try:
        r = requests.get(
            "https://query.wikidata.org/sparql",
            params={"query": query, "format": "json"},
            headers={"User-Agent": "ATHAR-Tourism/1.0"},
            timeout=15,
        )
        if r.status_code == 200:
            results = r.json().get("results", {}).get("bindings", [])
            if results:
                return results[0]
    except Exception:
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


def extract_fun_fact_from_wikidata(result: dict) -> str | None:
    """Convert a Wikidata SPARQL result binding into a fun fact string."""
    if not result:
        return None

    inception = result.get("inception", {}).get("value")
    if inception:
        year = inception[:4]
        if year.isdigit() and int(year) > 0:
            return f"This site was established around {year}, spanning over {2026 - int(year)} years of history."

    unesco = result.get("unescoStatus", {}).get("label")
    if unesco:
        return f"This site is listed as a UNESCO World Heritage site ({unesco}), recognized for its outstanding universal value."

    height = result.get("height", {}).get("value")
    if height:
        return f"Standing at {height} meters, this is a notable structure in the region."

    architect = result.get("architect", {}).get("label")
    if architect:
        return f"Designed by {architect}, this structure is an architectural highlight."

    population = result.get("population", {}).get("value")
    if population:
        return f"As of the last census, this area has a population of {int(population):,}."

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

    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 2])
        if arg == "--featured-only":
            featured_only = True

    engine = create_engine(DB_URL)

    query = """
        SELECT id, name, category, subtype, wilaya_id, historic_civilization,
               osm_tags, description, is_featured
        FROM pois
        WHERE fun_fact IS NULL
          AND latitude IS NOT NULL
    """
    if featured_only:
        query += " AND is_featured = true"
    query += f" ORDER BY is_featured DESC, name LIMIT {limit}"

    with engine.connect() as conn:
        rows = conn.execute(text(query))
        pois = [dict(r._mapping) for r in rows]

    print(f"POIs to enrich: {len(pois)}")

    enriched = 0
    skipped = 0
    wiki_hits = 0
    sparql_hits = 0
    tag_hits = 0
    template_hits = 0

    for i, poi in enumerate(pois):
        name = poi["name"]
        category = poi["category"]
        civilization = poi.get("historic_civilization")
        osm_tags = poi.get("osm_tags") or {}
        description = poi.get("description") or ""
        is_featured = poi.get("is_featured", False)

        fun_fact = None
        source = None

        if name and len(name) > 3:
            wiki_text = search_wikipedia(f"{name} Algeria")
            if wiki_text:
                fun_fact = extract_fun_fact_from_wikipedia(wiki_text)
                if fun_fact:
                    source = "wikipedia"
                    wiki_hits += 1

        if not fun_fact and name and len(name) > 3:
            sparql_result = fetch_wikidata_sparql(name)
            if sparql_result:
                fun_fact = extract_fun_fact_from_wikidata(sparql_result)
                if fun_fact:
                    source = "wikidata"
                    sparql_hits += 1

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
            fun_fact = templates[0]
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

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(pois)} (enriched: {enriched})")

        if (i + 1) % 20 == 0:
            time.sleep(1)

    print(f"\n=== SUMMARY ===")
    print(f"Total POIs processed: {len(pois)}")
    print(f"Enriched: {enriched}")
    print(f"  Wikipedia: {wiki_hits}")
    print(f"  Wikidata SPARQL: {sparql_hits}")
    print(f"  OSM tags: {tag_hits}")
    print(f"  Category templates: {template_hits}")
    print(f"Skipped: {skipped}")

    engine.dispose()


if __name__ == "__main__":
    main()
