#!/usr/bin/env python3
"""Enrich short POI descriptions using Gemma 4 via vLLM.

Queries POIs with descriptions < 80 chars, generates richer 2-3 sentence
tourist descriptions from OSM tags via the vLLM endpoint, updates DB.

Usage:
    python -m scripts.data.enrich_descriptions_genai
    python -m scripts.data.enrich_descriptions_genai --batch 50 --dry-run
"""

import asyncio
import logging
import sys
import time
from argparse import ArgumentParser
from pathlib import Path

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            import os
            os.environ.setdefault(k.strip(), v.strip())

from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

VLLM_BASE_URL = settings.agent.vllm.base_url or "http://41.106.129.230:8080/v1"
VLLM_API_KEY = settings.agent.vllm.api_key or ""
VLLM_MODEL = settings.agent.vllm.model or "Gemma-4-31B-it"

WILAYA_NAMES: dict[int, str] = {}

SYSTEM_PROMPT = """You write short tourist descriptions for Algerian points of interest.
Write a concise, engaging 2-3 sentence description in French suitable for a travel app.
Include: what the place is, why it's worth visiting, and any notable detail from the tags.
Do NOT use markdown. Do NOT repeat the POI name. Start directly with the description.
If the POI has almost no useful tags, write a generic but plausible description for its category in Algeria."""


def build_user_prompt(name: str, category: str, subtype: str | None, commune: str | None, wilaya_id: int, tags: dict | None) -> str:
    wilaya_name = WILAYA_NAMES.get(wilaya_id, f"wilaya {wilaya_id}")
    loc = f"{commune}, {wilaya_name}" if commune else wilaya_name

    tag_parts = []
    if tags:
        for key in ("amenity", "tourism", "historic", "natural", "leisure", "building",
                     "cuisine", "religion", "material", "start_date", "artist_name",
                     "architect", "heritage", "wheelchair", "website", "phone"):
            if key in tags:
                tag_parts.append(f"{key}={tags[key]}")
    tag_str = "; ".join(tag_parts[:8]) if tag_parts else "no tags"

    sub = f" ({subtype})" if subtype else ""
    return (
        f"POI: {name}{sub}\n"
        f"Category: {category}\n"
        f"Location: {loc}\n"
        f"OSM tags: {tag_str}\n"
        f"\nWrite a 2-3 sentence French tourist description:"
    )


async def call_llm(client: httpx.AsyncClient, prompts: list[str]) -> list[str]:
    """Call vLLM for a batch of prompts, return list of generated descriptions."""
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
                    "temperature": 0.4,
                    "max_tokens": 250,
                },
                headers={"Authorization": f"Bearer {VLLM_API_KEY}"},
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            results.append(content)
        except Exception as e:
            log.warning("LLM call failed: %s", e)
            results.append("")
    return results


async def fetch_short_pois(db: AsyncSession, limit: int, offset: int) -> list[dict]:
    """Fetch POIs with short descriptions."""
    rows = await db.execute(
        text("""
            SELECT id, name, category, subtype, wilaya_id, commune,
                   description, osm_tags
            FROM pois
            WHERE length(description) < 80
            ORDER BY id
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    return [
        {
            "id": str(r[0]), "name": r[1], "category": r[2], "subtype": r[3],
            "wilaya_id": r[4], "commune": r[5], "description": r[6],
            "osm_tags": r[7] or {},
        }
        for r in rows.all()
    ]


async def load_wilaya_names(db: AsyncSession):
    global WILAYA_NAMES
    rows = await db.execute(text("SELECT id, name_en FROM wilayas"))
    WILAYA_NAMES = {r[0]: r[1] for r in rows.all()}
    log.info("Loaded %d wilaya names", len(WILAYA_NAMES))


async def update_descriptions(db: AsyncSession, updates: list[tuple[str, str]]):
    """Batch update descriptions by (poi_id, new_description)."""
    if not updates:
        return
    for poi_id, desc in updates:
        await db.execute(
            text("UPDATE pois SET description = :desc, updated_at = NOW() WHERE id = :id"),
            {"id": poi_id, "desc": desc},
        )
    await db.commit()


async def enrich(batch_size: int = 20, dry_run: bool = False, max_total: int = 0):
    url = os.environ.get("DATABASE_URL", "postgresql+asyncpg://athar:athar@localhost:5434/athar_db")
    engine = create_async_engine(url)

    async with AsyncSession(engine) as db:
        await load_wilaya_names(db)

        total_short = (await db.execute(
            text("SELECT COUNT(*) FROM pois WHERE length(description) < 80")
        )).scalar()
        log.info("Found %d POIs with short descriptions", total_short)

        if max_total > 0:
            total_short = min(total_short, max_total)

        enriched = 0
        skipped = 0
        errors = 0
        offset = 0

        async with httpx.AsyncClient() as client:
            while offset < total_short:
                pois = await fetch_short_pois(db, batch_size, offset)
                if not pois:
                    break

                # Skip unnamed/unknown POIs
                valid = [p for p in pois if p["name"] and "non nommé" not in p["name"].lower()
                         and p["name"].lower() not in ("unknown", "inconnu", "point d'intérêt")]
                skipped += len(pois) - len(valid)

                if not valid:
                    offset += batch_size
                    continue

                prompts = [
                    build_user_prompt(p["name"], p["category"], p["subtype"],
                                      p["commune"], p["wilaya_id"], p["osm_tags"])
                    for p in valid
                ]

                if dry_run:
                    log.info("[DRY RUN] Would process %d POIs", len(valid))
                    for i, p in enumerate(valid[:3]):
                        log.info("  [%s] %s → prompt:\n%s", p["category"], p["name"], prompts[i][:200])
                    break

                descriptions = await call_llm(client, prompts)
                updates = []
                for poi, desc in zip(valid, descriptions):
                    if desc and len(desc) > 30:
                        updates.append((poi["id"], desc))
                    else:
                        errors += 1

                await update_descriptions(db, updates)
                enriched += len(updates)
                offset += batch_size

                log.info("Progress: %d/%d enriched, %d skipped, %d errors",
                         enriched, total_short, skipped, errors)

                # Rate limit: ~2 req/sec
                await asyncio.sleep(0.5)

        log.info("DONE: %d enriched, %d skipped, %d errors out of %d total",
                 enriched, skipped, errors, total_short)

    await engine.dispose()


def main():
    parser = ArgumentParser()
    parser.add_argument("--batch", type=int, default=20, help="Batch size")
    parser.add_argument("--dry-run", action="store_true", help="Show prompts without calling LLM")
    parser.add_argument("--max", type=int, default=0, help="Max POIs to process (0=all)")
    args = parser.parse_args()
    asyncio.run(enrich(batch_size=args.batch, dry_run=args.dry_run, max_total=args.max))


if __name__ == "__main__":
    main()
