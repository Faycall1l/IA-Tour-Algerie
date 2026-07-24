#!/usr/bin/env python3
"""Enrich POIs with fun facts using vLLM Gemma 4.

For each tourism-relevant POI without a fun fact, sends its name, category,
wilaya, and OSM tags to Gemma 4 which generates a single interesting fact.
Facts are marked with source='ai:vllm' to distinguish from hand-curated ones.

Usage:
    python -m scripts.data.enrich_fun_facts_genai [--limit N] [--batch N] [--dry-run]
"""

import asyncio
import logging
import os
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VLLM_BASE_URL = settings.agent.vllm.base_url or "http://41.106.129.230:8080/v1"
VLLM_API_KEY = settings.agent.vllm.api_key or ""
VLLM_MODEL = settings.agent.vllm.model or "Gemma-4-31B-it"

WILAYA_NAMES: dict[int, str] = {}

SYSTEM_PROMPT = """You write fun facts for Algerian tourist attractions.
Given a POI name, category, wilaya (province), and OSM tags, write ONE short, specific, interesting fun fact.

Rules:
- Write in English
- 1-2 sentences, under 200 characters
- Be specific: include dates, numbers, names, or superlatives when possible
- Only state things you are confident about — do NOT invent dates or statistics
- If you cannot think of a specific interesting fact, respond with just: SKIP
- Do NOT write generic filler like "a beautiful place to visit" or "one of Algeria's hidden gems"
- Focus on what makes THIS place unique or noteworthy"""

CATEGORY_CONTEXT = {
    "historical": "This is a historical/archaeological site.",
    "cultural": "This is a cultural landmark or heritage site.",
    "museum": "This is a museum or cultural institution.",
    "natural": "This is a natural landmark or scenic site.",
    "mountain": "This is a mountain or mountain-related site.",
    "park": "This is a national park or protected area.",
    "religious": "This is a religious site (mosque, church, shrine, etc.).",
    "beach": "This is a beach or coastal site.",
    "market": "This is a market or commercial area.",
    "restaurant": "This is a restaurant or food establishment.",
    "cafe": "This is a cafe or coffee shop.",
    "other": "This is a general point of interest.",
}

TARGET_CATEGORIES = {
    "historical", "cultural", "museum", "natural", "mountain",
    "park", "religious", "beach", "other",
}


def build_user_prompt(poi: dict) -> str:
    name = poi["name"]
    category = poi["category"]
    subtype = poi.get("subtype") or ""
    wilaya_id = poi.get("wilaya_id")
    wilaya_name = WILAYA_NAMES.get(wilaya_id, f"Wilaya {wilaya_id}")
    description = poi.get("description") or ""
    name_en = poi.get("name_en") or ""
    osm_tags = poi.get("osm_tags") or {}
    if isinstance(osm_tags, str):
        import json
        try:
            osm_tags = json.loads(osm_tags)
        except (json.JSONDecodeError, TypeError):
            osm_tags = {}

    cat_ctx = CATEGORY_CONTEXT.get(category, "")

    tag_parts = []
    for key in sorted(osm_tags.keys()):
        val = osm_tags[key]
        if key.startswith("name:") and not key.startswith("name:en") and not key.startswith("name:ar"):
            continue
        tag_parts.append(f"{key}={val}")

    tag_str = "; ".join(tag_parts[:15]) if tag_parts else "no extra tags"

    sub = f" ({subtype})" if subtype else ""
    en = f" (English: {name_en})" if name_en and name_en != name else ""

    prompt = f"POI: {name}{sub}{en}\nCategory: {category}\n{cat_ctx}\nLocation: {wilaya_name}, Algeria\nOSM data: {tag_str}"
    if description and len(description) > 20:
        desc_clean = description[:300].strip()
        prompt += f"\nDescription: {desc_clean}"
    prompt += "\n\nWrite ONE fun fact about this specific place:"
    return prompt


async def call_llm_batch(client: httpx.AsyncClient, prompts: list[str]) -> list[str]:
    """Call vLLM for each prompt sequentially."""
    results = []
    for prompt in prompts:
        try:
            resp = await client.post(
                f"{VLLM_BASE_URL}/chat/completions",
                json={
                    "model": VLLM_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 150,
                },
                headers={"Authorization": f"Bearer {VLLM_API_KEY}"},
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            results.append(content)
        except Exception as e:
            log.warning("LLM call failed: %s", e)
            results.append("SKIP")
        await asyncio.sleep(0.5)
    return results


def validate_fact(fact: str) -> str | None:
    """Validate that a generated fact is useful and not garbage."""
    if not fact or len(fact) < 15:
        return None
    if fact.strip().upper() == "SKIP":
        return None
    lower = fact.lower()

    skip_phrases = [
        "skip", "i don't know", "i cannot", "no information",
        "i'm not sure", "uncertain", "no specific",
    ]
    if any(phrase in lower for phrase in skip_phrases):
        return None

    generic_phrases = [
        "beautiful place to visit",
        "hidden gem",
        "worth visiting",
        "great place to",
        "wonderful place",
        "lovely place",
        "must-visit",
        "one of algeria's",
        "algeria's hidden",
        "a popular destination",
        "a great spot",
    ]
    if any(phrase in lower for phrase in generic_phrases):
        return None

    if len(fact) > 250:
        sentences = [s.strip() for s in fact.replace("\n", " ").split(". ") if s.strip()]
        if len(sentences) > 1:
            fact = sentences[0] + "."
        else:
            fact = fact[:247] + "..."

    if not fact.endswith("."):
        fact += "."

    return fact


async def fetch_target_pois(db: AsyncSession, limit: int, offset: int) -> list[dict]:
    """Fetch POIs without fun facts, prioritizing those with meaningful context."""
    rows = await db.execute(
        text("""
            SELECT id, name, name_en, category, subtype, wilaya_id, osm_tags,
                   description, is_featured
            FROM pois
            WHERE fun_fact IS NULL
              AND name IS NOT NULL AND LENGTH(name) > 3
              AND name NOT LIKE '%non nommé%'
              AND name NOT LIKE '%Unnamed%'
              AND name NOT LIKE '%unknown%'
              AND name NOT LIKE '%Inconnu%'
              AND name NOT LIKE '%Bibliothèque%'
              AND name NOT LIKE '%Bibliotheque%'
              AND name NOT LIKE '%mactab%'
              AND name NOT LIKE '%مكتبة%'
              AND category = ANY(:cats)
              AND (
                (description IS NOT NULL AND LENGTH(description) > 100)
                OR (name_en IS NOT NULL AND name_en ~ '[A-Z][a-z]')
                OR (osm_tags::text LIKE '%heritage%')
                OR (osm_tags::text LIKE '%start_date%')
                OR (osm_tags::text LIKE '%historic%')
                OR (is_featured = true AND name NOT LIKE '%ONAT%' AND name NOT LIKE '%ديوان%')
              )
            ORDER BY
                (osm_tags::text LIKE '%heritage%') DESC,
                (osm_tags::text LIKE '%start_date%') DESC,
                (osm_tags::text LIKE '%historic%') DESC,
                (name_en IS NOT NULL AND name_en ~ '^[A-Z][a-z]' AND LENGTH(name_en) > 8) DESC,
                (description IS NOT NULL AND LENGTH(description) > 150) DESC,
                category IN ('museum','natural','mountain','park','religious','beach','historical') DESC,
                is_featured DESC,
                name
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset, "cats": list(TARGET_CATEGORIES)},
    )
    return [
        {
            "id": str(r[0]),
            "name": r[1] or r[2] or "Unknown",
            "name_en": r[2],
            "category": r[3],
            "subtype": r[4],
            "wilaya_id": r[5],
            "osm_tags": r[6] or {},
            "description": r[7] or "",
            "is_featured": r[8],
        }
        for r in rows.all()
    ]


async def load_wilaya_names(db: AsyncSession):
    global WILAYA_NAMES
    rows = await db.execute(text("SELECT id, name_en FROM wilayas"))
    WILAYA_NAMES = {r[0]: r[1] for r in rows.all()}
    log.info("Loaded %d wilaya names", len(WILAYA_NAMES))


async def update_fun_facts(db: AsyncSession, updates: list[tuple[str, str]]):
    if not updates:
        return
    for poi_id, fact in updates:
        await db.execute(
            text("UPDATE pois SET fun_fact = :fact, fun_fact_source = :source WHERE id = :id"),
            {"id": poi_id, "fact": fact, "source": "ai:vllm"},
        )
    await db.commit()


async def enrich(batch_size: int = 10, dry_run: bool = False, max_total: int = 0):
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://athar:athar@localhost:5432/athar_db")
    engine = create_async_engine(url)

    async with AsyncSession(engine) as db:
        await load_wilaya_names(db)

        count_q = await db.execute(text("""
            SELECT COUNT(*) FROM pois
            WHERE fun_fact IS NULL
              AND name IS NOT NULL AND LENGTH(name) > 3
              AND name NOT LIKE '%non nommé%'
              AND name NOT LIKE '%Unnamed%'
              AND name NOT LIKE '%unknown%'
              AND name NOT LIKE '%Inconnu%'
              AND category = ANY(:cats)
        """), {"cats": list(TARGET_CATEGORIES)})
        total = count_q.scalar() or 0
        log.info("Target POIs (tourism categories, no fun fact): %d", total)

        if max_total > 0:
            total = min(total, max_total)

        enriched = 0
        skipped = 0
        errors = 0
        offset = 0

        async with httpx.AsyncClient() as client:
            while offset < total:
                pois = await fetch_target_pois(db, batch_size, offset)
                if not pois:
                    break

                prompts = [build_user_prompt(p) for p in pois]

                if dry_run:
                    log.info("[DRY RUN] Would process %d POIs", len(pois))
                    for i, p in enumerate(pois[:3]):
                        log.info("  [%s] %s\n%s", p["category"], p["name"][:40], prompts[i][:300])
                    break

                facts = await call_llm_batch(client, prompts)
                updates = []
                for poi, raw_fact in zip(pois, facts):
                    fact = validate_fact(raw_fact)
                    if fact:
                        updates.append((poi["id"], fact))
                        enriched += 1
                        log.info("  [%d] %s → %s", enriched, poi["name"][:35], fact[:80])
                    else:
                        skipped += 1
                        log.debug("  SKIP %s: raw=%r", poi["name"][:35], raw_fact[:80] if raw_fact else None)

                await update_fun_facts(db, updates)
                offset += batch_size

                log.info(
                    "Progress: %d/%d enriched, %d skipped, %d errors",
                    enriched, total, skipped, errors,
                )

        log.info("DONE: %d enriched, %d skipped, %d errors out of %d total",
                 enriched, skipped, errors, total)

    await engine.dispose()


def main():
    parser = ArgumentParser(description="GenAI fun fact enrichment via vLLM Gemma 4")
    parser.add_argument("--batch", type=int, default=10, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts without calling LLM")
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to process (0=all)")
    args = parser.parse_args()
    asyncio.run(enrich(batch_size=args.batch, dry_run=args.dry_run, max_total=args.limit))


if __name__ == "__main__":
    main()
