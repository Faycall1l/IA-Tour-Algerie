#!/usr/bin/env python3
"""
Enrich POIs with REAL fun facts from Wikidata + Wikipedia + OSM tags.

Only adds facts that are specific, verifiable, and unique to each POI.
NO templates, NO generic descriptions. If no real fact exists, the POI stays empty.

Sources (in priority order):
1. Wikidata — year built, UNESCO status, height, architect, population, etc.
2. Wikipedia — real sentences from articles with specific facts
3. OSM tags — ONLY when they contain real data (height, material, cuisine, elevation, start_date)

Usage:
  python scripts/data/enrich_fun_facts.py [--limit N] [--featured-only] [--resume]
"""

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from sqlalchemy import create_engine, text

DB_URL = "postgresql://athar:athar_pass@localhost:5434/athar_db"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

WILAYA_NAMES = {
    1: "Adrar", 2: "Chlef", 3: "Laghouat", 4: "Oum El Bouaghi", 5: "Batna",
    6: "Béjaïa", 7: "Biskra", 8: "Béchar", 9: "Blida", 10: "Bouira",
    11: "Tamanrasset", 12: "Tébessa", 13: "Tlemcen", 14: "Tiaret",
    15: "Tizi Ouzou", 16: "Alger", 17: "Djelfa", 18: "Jijel", 19: "Sétif",
    20: "Saïda", 21: "Skikda", 22: "Sidi Bel Abbès", 23: "Annaba",
    24: "Guelma", 25: "Constantine", 26: "Médéa", 27: "Mostaganem",
    28: "M'sila", 29: "Mascara", 30: "Ouargla", 31: "Oran",
    32: "El Bayadh", 33: "Illizi", 34: "Bordj Bou Arréridj", 35: "Boumerdès",
    36: "El Tarf", 37: "Tindouf", 38: "Tissemsilt", 39: "El Oued",
    40: "Khenchela", 41: "Souk Ahras", 42: "Tipaza", 43: "Mila",
    44: "Aïn Defla", 45: "Naâma", 46: "Aïn Témouchent", 47: "Ghardaïa",
    48: "Relizane", 49: "El M'Ghair", 50: "El Meniaa", 51: "Ouled Djellal",
    52: "Bordj Badji Mokhtar", 53: "Béni Abbès", 54: "Timimoun",
    55: "Touggourt", 56: "Djanet", 57: "In Salah", 58: "In Guezzam",
}

ALGERIA_KEYWORDS = [
    "algeria", "algerian", "algérie", "algérien", "algérienne",
    "oran", "constantine", "algiers", "annaba", "tlemcen", "batna",
    "béjaïa", "setif", "sétif", "blida", "tizi ouzou", "djelfa",
    "biskra", "ghardaïa", "tlemcen", "tipaza", "timgad", "djemila",
    "ghardaia", "mzab", "sahara", "atlas", "kabyle", "kabylie",
    "m'zab", "hoggar", "tassili", "aures", "chelif", "oued",
    "wilaya", "commune", "daira", "baladiya",
]

HEADERS = {"User-Agent": "ATHAR-Tourism/1.0 (https://athar-os.com)"}

# Session for connection pooling
_session = requests.Session()
_session.headers.update(HEADERS)


def _is_algeria_context(text: str) -> bool:
    lower = text.lower()
    if any(kw in lower for kw in ALGERIA_KEYWORDS):
        return True
    non_algeria = ["morocco", "maroc", "marrakech", "casablanca", "fez", "tunisia", "tunisie"]
    if any(kw in lower for kw in non_algeria):
        return False
    return False


def is_real_name(name: str) -> bool:
    if not name or len(name) < 3:
        return False
    generic = [
        "non nommé", "unnamed", "unknown", "archaeological site", "peak",
        "mountain", "spring", "well", "ruins", "building", "structure",
        "monument", "memorial", "mosque", "church", "fort", "tomb",
        "refuge", "la mairie", "sbiat", "ain ferhat", "issoghla",
    ]
    lower = name.lower().strip()
    if lower in generic:
        return False
    for g in generic:
        if lower.startswith(g) and len(lower) < len(g) + 5:
            return False
    return True


def _search_wikidata_entity(search_name: str) -> dict | None:
    try:
        r = _session.get(
            WIKIDATA_API,
            params={
                "action": "wbsearchentities",
                "search": search_name,
                "language": "en",
                "type": "item",
                "limit": 3,
                "format": "json",
            },
            timeout=8,
        )
        if r.status_code != 200:
            return None
        results = r.json().get("search", [])
        if not results:
            return None

        for sr in results[:2]:
            entity_id = sr["id"]
            r2 = _session.get(
                WIKIDATA_API,
                params={
                    "action": "wbgetentities",
                    "ids": entity_id,
                    "props": "claims|labels|descriptions",
                    "languages": "en|fr|ar",
                    "format": "json",
                },
                timeout=8,
            )
            if r2.status_code != 200:
                continue
            entity = r2.json().get("entities", {}).get(entity_id, {})
            claims = entity.get("claims", {})
            desc = entity.get("descriptions", {}).get("en", {}).get("value", "")
            label = entity.get("labels", {}).get("en", {}).get("value", "")

            in_algeria = False
            p17 = claims.get("P17")
            if p17:
                try:
                    country_qid = p17[0]["mainsnak"]["datavalue"]["value"]["id"]
                    if country_qid == "Q262":
                        in_algeria = True
                except (KeyError, IndexError):
                    pass

            if not in_algeria and _is_algeria_context(desc + " " + label):
                in_algeria = True

            if in_algeria:
                return {"entity_id": entity_id, "claims": claims, "desc": desc, "label": label}

    except Exception:
        pass
    return None


def _extract_fact_from_claims(claims: dict, poi_name: str) -> str | None:
    # UNESCO World Heritage (P1411)
    unesco = claims.get("P1411")
    if unesco:
        try:
            qid = unesco[0]["mainsnak"]["datavalue"]["value"]["id"]
            year = ""
            qualifiers = unesco[0].get("qualifiers", {})
            start = qualifiers.get("P580")
            if start:
                val = start[0]["datavalue"]["value"]["time"]
                year = val.lstrip("+").split("-")[0]
            if year:
                return f"UNESCO World Heritage Site since {year}."
            return f"UNESCO World Heritage Site ({qid})."
        except (KeyError, IndexError):
            return "UNESCO World Heritage Site."

    inception = claims.get("P571")
    year = None
    if inception:
        try:
            val = inception[0]["mainsnak"]["datavalue"]["value"]["time"]
            year_str = val.lstrip("+").split("-")[0]
            if year_str.isdigit() and int(year_str) > 0:
                year = int(year_str)
        except (KeyError, IndexError):
            pass

    height = claims.get("P2048")
    if height:
        try:
            h = height[0]["mainsnak"]["datavalue"]["value"]["amount"]
            unit = height[0]["mainsnak"]["datavalue"]["value"].get("unit", "")
            if "meter" in unit or "11571" in unit:
                fact = f"Stands {h} meters tall"
                if year:
                    fact += f", built in {year}"
                return fact + "."
        except (KeyError, IndexError):
            pass

    architect = claims.get("P84")
    if architect:
        try:
            arch_id = architect[0]["mainsnak"]["datavalue"]["value"].get("id", "")
            r = _session.get(
                WIKIDATA_API,
                params={"action": "wbgetentities", "ids": arch_id, "props": "labels",
                        "languages": "en", "format": "json"},
                timeout=5,
            )
            if r.status_code == 200:
                label = r.json().get("entities", {}).get(arch_id, {}).get("labels", {}).get("en", {}).get("value", "")
                if label:
                    fact = f"Designed by architect {label}"
                    if year:
                        fact += f" in {year}"
                    return fact + "."
        except Exception:
            pass

    creator = claims.get("P112")
    if creator:
        try:
            creator_id = creator[0]["mainsnak"]["datavalue"]["value"].get("id", "")
            r = _session.get(
                WIKIDATA_API,
                params={"action": "wbgetentities", "ids": creator_id, "props": "labels",
                        "languages": "en", "format": "json"},
                timeout=5,
            )
            if r.status_code == 200:
                label = r.json().get("entities", {}).get(creator_id, {}).get("labels", {}).get("en", {}).get("value", "")
                if label:
                    fact = f"Founded by {label}"
                    if year:
                        fact += f" in {year}"
                    return fact + "."
        except Exception:
            pass

    # Elevation (P2044) — for natural features
    elevation = claims.get("P2044")
    if elevation:
        try:
            ele = elevation[0]["mainsnak"]["datavalue"]["value"]["amount"]
            ele_str = str(ele).lstrip("+")
            return f"Located at {ele_str} meters above sea level."
        except (KeyError, IndexError):
            pass

    # Population (P1082) — only for settlements
    population = claims.get("P1082")
    instance_of = claims.get("P31")
    is_settlement = False
    if instance_of:
        try:
            for claim in instance_of[:5]:
                qid = claim["mainsnak"]["datavalue"]["value"]["id"]
                if qid in ("Q515", "Q3957", "Q532", "Q317557", "Q2099524", "Q15284", "Q486972"):
                    is_settlement = True
                    break
        except (KeyError, IndexError):
            pass
    if population and is_settlement:
        try:
            pop = int(population[0]["mainsnak"]["datavalue"]["value"]["amount"])
            if pop > 0:
                return f"Home to {pop:,} people according to the last census."
        except (KeyError, IndexError, ValueError):
            pass

    if year and year > 100:
        age = 2026 - year
        if age > 500:
            return f"Dates back to {year} — over {age} years of history."
        elif age > 200:
            return f"Built in {year}."

    return None


def _fetch_wikipedia_extract(title: str, sentences: int = 4) -> str | None:
    try:
        r = _session.get(
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
            timeout=10,
        )
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for page in pages.values():
                extract = page.get("extract", "")
                if extract and len(extract) > 50:
                    return extract.strip()
    except Exception:
        pass
    return None


def search_wikipedia(query: str, expected_name: str = "") -> str | None:
    try:
        r = _session.get(
            WIKIPEDIA_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
            },
            timeout=10,
        )
        if r.status_code == 200:
            results = r.json().get("query", {}).get("search", [])
            for result in results:
                title = result["title"]
                snippet = result.get("snippet", "")
                if not _is_algeria_context(snippet + " " + title):
                    continue
                if expected_name:
                    title_lower = title.lower()
                    name_lower = expected_name.lower()
                    name_words = [w for w in name_lower.split() if len(w) > 2]
                    if name_words and not any(w in title_lower for w in name_words[:2]):
                        continue
                return _fetch_wikipedia_extract(title)
    except Exception:
        pass
    return None


def extract_fun_fact_from_wikipedia(wikipedia_text: str, poi_name: str = "") -> str | None:
    if not wikipedia_text:
        return None

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', wikipedia_text)]

    specific_keywords = [
        "built", "constructed", "founded", "established", "oldest", "largest", "first",
        "UNESCO", "ancient", "medieval", "remains", "ruins",
        "discovered", "archaeological", "monument", "mosque", "cathedral",
        "fortress", "palace", "tomb", "amphitheater", "bath", "population",
        "altitude", "highest", "deepest", "longest", "tallest", "meters",
        "century", "centuries", "dynasty", "roman", "phoenician", "berber",
        "ottoman", "colonial", "independence", "war", "battle", "siege",
        "spring", "cave", "gorge", "canyon", "harbor", "port", "lighthouse",
        "bridge", "aqueduct", "library", "university", "market", "souk",
    ]

    for sentence in sentences:
        lower = sentence.lower()
        if not any(kw in lower for kw in specific_keywords):
            continue
        has_number = bool(re.search(r'\d{3,}', sentence))
        if not has_number:
            continue
        cleaned = re.sub(r'\[.*?\]', '', sentence)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if 40 < len(cleaned) < 300:
            return cleaned

    return None


def generate_fun_fact_from_tags(osm_tags: dict) -> str | None:
    if not osm_tags:
        return None
    tags = osm_tags if isinstance(osm_tags, dict) else {}

    year = tags.get("start_date") or tags.get("built") or tags.get("year")
    if year:
        try:
            y = int(str(year)[:4])
            if y > 100 and y < 2030:
                age = 2026 - y
                if age > 50:
                    return f"Established in {y}, this site is over {age} years old."
        except (ValueError, TypeError):
            pass

    height = tags.get("height") or tags.get("building:height")
    if height:
        try:
            h = float(str(height).replace("m", "").strip())
            if h > 5:
                return f"Stands {h} meters tall."
        except (ValueError, TypeError):
            pass

    elevation = tags.get("ele")
    if elevation:
        try:
            e = float(str(elevation).replace("m", "").strip())
            if e > 10:
                return f"Located at {e} meters above sea level."
        except (ValueError, TypeError):
            pass

    material = tags.get("material") or tags.get("building:material")
    if material and len(str(material)) > 2:
        return f"Built primarily from {material}."

    architect = tags.get("architect")
    if architect and len(str(architect)) > 3:
        return f"Designed by {architect}."

    cuisine = tags.get("cuisine")
    if cuisine and len(str(cuisine)) > 2:
        return f"Specializes in {cuisine} cuisine."

    return None


def enrich_poi(poi: dict) -> tuple[int, str | None, str | None]:
    """Try to find a real fun fact for a POI. Returns (poi_id, fact, source)."""
    poi_id = poi["id"]
    name = poi["name"]
    name_en = poi.get("name_en") or name
    wilaya_id = poi.get("wilaya_id")
    wilaya_name = WILAYA_NAMES.get(wilaya_id, "")
    osm_tags = poi.get("osm_tags") or {}
    if isinstance(osm_tags, str):
        try:
            osm_tags = json.loads(osm_tags)
        except (json.JSONDecodeError, TypeError):
            osm_tags = {}

    search_name = name_en if any(c.isascii() and c.isalpha() for c in str(name_en)) else name
    search_name = str(search_name).strip()
    if not is_real_name(search_name):
        return poi_id, None, None

    # 1. Wikidata
    wd = _search_wikidata_entity(search_name)
    if wd:
        fact = _extract_fact_from_claims(wd["claims"], search_name)
        if fact:
            return poi_id, fact, f"wikidata:{wd['entity_id']}"

    if name != name_en and is_real_name(name) and any(c.isascii() and c.isalpha() for c in str(name)):
        wd2 = _search_wikidata_entity(name)
        if wd2:
            fact = _extract_fact_from_claims(wd2["claims"], name)
            if fact:
                return poi_id, fact, f"wikidata:{wd2['entity_id']}"

    # 2. Wikipedia
    wiki_text = search_wikipedia(f"{search_name} {wilaya_name} Algeria", expected_name=search_name)
    if not wiki_text:
        wiki_text = search_wikipedia(f"{search_name} Algeria", expected_name=search_name)
    if wiki_text:
        fact = extract_fun_fact_from_wikipedia(wiki_text, search_name)
        if fact:
            lower = fact.lower()
            if "morocco" not in lower and "maroc" not in lower and "tunisia" not in lower and "tunisie" not in lower:
                return poi_id, fact, "wikipedia"

    # 3. OSM tags
    if osm_tags:
        fact = generate_fun_fact_from_tags(osm_tags)
        if fact:
            return poi_id, fact, "osm_tags"

    return poi_id, None, None


def main():
    limit = 5000
    featured_only = False
    resume = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--limit" and i + 1 < len(args):
            limit = int(args[i + 1])
        if arg == "--featured-only":
            featured_only = True
        if arg == "--resume":
            resume = True

    engine = create_engine(DB_URL)

    query = """
        SELECT id, name, name_en, category, subtype, wilaya_id,
               historic_civilization, osm_tags, is_featured
        FROM pois
        WHERE fun_fact IS NULL
          AND latitude IS NOT NULL
          AND name IS NOT NULL AND LENGTH(name) > 3
          AND name NOT LIKE '%non nommé%'
          AND name NOT LIKE '%Unnamed%'
          AND name NOT LIKE '%unknown%'
    """
    if featured_only:
        query += " AND is_featured = true"
    query += """
        ORDER BY is_featured DESC,
                 category IN ('historical','cultural','museum','religious') DESC,
                 name
        LIMIT :limit
    """

    with engine.connect() as conn:
        rows = conn.execute(text(query), {"limit": limit})
        pois = [dict(r._mapping) for r in rows]

    print(f"POIs to enrich: {len(pois)}")

    enriched = 0
    skipped = 0
    wiki_hits = 0
    wikidata_hits = 0
    tag_hits = 0
    errors = 0
    start_time = time.time()

    # Process with ThreadPoolExecutor — 4 workers to avoid hammering APIs
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(enrich_poi, poi): poi for poi in pois}

        for i, future in enumerate(as_completed(futures)):
            try:
                poi_id, fact, source = future.result()
                if fact and source:
                    with engine.connect() as conn:
                        conn.execute(
                            text("UPDATE pois SET fun_fact = :fact, fun_fact_source = :source WHERE id = :id"),
                            {"fact": fact, "source": source, "id": poi_id},
                        )
                        conn.commit()
                    enriched += 1
                    if "wikidata" in source:
                        wikidata_hits += 1
                    elif source == "wikipedia":
                        wiki_hits += 1
                    elif source == "osm_tags":
                        tag_hits += 1
                    poi_name = futures[future]["name"][:35]
                    print(f"  [{enriched}] {poi_name} → {fact[:55]}... ({source})")
                else:
                    skipped += 1
            except Exception as e:
                errors += 1

            done = i + 1
            if done % 100 == 0:
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                print(f"\n  === Progress: {done}/{len(pois)} ({rate:.1f} POIs/sec, enriched: {enriched}, skipped: {skipped}) ===\n")

    elapsed = time.time() - start_time
    print(f"\n=== SUMMARY ({elapsed:.0f}s) ===")
    print(f"Total POIs processed: {len(pois)}")
    print(f"Enriched: {enriched}")
    print(f"  Wikidata: {wikidata_hits}")
    print(f"  Wikipedia: {wiki_hits}")
    print(f"  OSM tags: {tag_hits}")
    print(f"Skipped (no real fact found): {skipped}")
    print(f"Errors: {errors}")

    engine.dispose()


if __name__ == "__main__":
    main()
