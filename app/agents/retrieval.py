"""Retrieval-Augmented Generation (RAG) grounding for ATHAR agents.

Retrieves real, verifiable travel records (POIs, stays, experiences) from the
Qdrant vector index with a PostgreSQL full-text fallback, then renders them as
a compact, cited ``REAL DATA`` block that gets injected into the agent system
prompt. The agent is instructed that every entry is real and can be referenced
directly, grounding answers even when the model decides not to call tools.

Why: tool calls are powerful but the model may skip them (or budget them out);
a grounded context block lets the model answer from real records with IDs the
frontend can deep-link to, without extra round-trips. The SQL fallback covers
stays too (Qdrant only indexes POIs and experiences).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.experience import Experience
from app.models.poi import POI
from app.models.stay import Stay

if TYPE_CHECKING:
    from app.services.vector_search import VectorSearchService

logger = logging.getLogger(__name__)

MAX_HITS = 4
DESCRIPTION_MAX_CHARS = 140
_PLACEHOLDER_SUFFIX = "%(non nommé)%"

_KIND_LABELS = {"poi": "POI", "stay": "Hebergement", "experience": "Experience"}

_TRANSPORT_HINTS = (
    "how do i get",
    "how to get",
    "how can i get",
    "comment aller",
    "comment me rendre",
    "bus from",
    "bus de",
    "train from",
    "taxi from",
    "flight",
    "vol de",
    "vol vers",
    "gare",
    "horaires",
    "schedule",
    "from algiers to",
    "from oran to",
    "from constantine to",
)
_OFF_TOPIC = ("hello", "bonjour", "hi ", "salut", "thanks", "merci", "help", "who are you")


@dataclass(frozen=True)
class RetrievalHit:
    """A single retrieved, verifiable travel record."""

    kind: str  # poi | stay | experience
    id: UUID
    name: str
    category: str
    description: str
    wilaya_id: int
    fun_fact: str | None = None

    def render(self) -> str:
        label = _KIND_LABELS.get(self.kind, self.kind)
        desc = self.description.strip() if self.description else "(pas de description)"
        if self.fun_fact:
            desc = f"{desc} (fun fact: {self.fun_fact})"
        return f"- [{label} w{self.wilaya_id}] {self.name} ({self.category}): {desc} [id:{self.id}]"


def _hit_from_poi(poi: POI) -> RetrievalHit:
    return RetrievalHit(
        kind="poi",
        id=poi.id,
        name=poi.name,
        category=poi.category,
        description=(poi.description or "")[:DESCRIPTION_MAX_CHARS],
        wilaya_id=poi.wilaya_id,
        fun_fact=(poi.fun_fact or "")[:DESCRIPTION_MAX_CHARS] or None,
    )


def _hit_from_stay(stay: Stay) -> RetrievalHit:
    return RetrievalHit(
        kind="stay",
        id=stay.id,
        name=stay.name,
        category=stay.property_type,
        description=(stay.description or "")[:DESCRIPTION_MAX_CHARS],
        wilaya_id=stay.wilaya_id,
    )


def _hit_from_experience(experience: Experience) -> RetrievalHit:
    return RetrievalHit(
        kind="experience",
        id=experience.id,
        name=experience.title,
        category=experience.category,
        description=(experience.description or "")[:DESCRIPTION_MAX_CHARS],
        wilaya_id=experience.wilaya_id,
    )


async def _poi_hits(db: AsyncSession, tsq, limit: int) -> list[RetrievalHit]:
    stmt = (
        select(POI)
        .where(POI.search_vector.op("@@")(tsq))
        .order_by(
            POI.name.not_like(_PLACEHOLDER_SUFFIX).desc(),
            func.ts_rank(POI.search_vector, tsq).desc(),
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_hit_from_poi(p) for p in result.scalars().all()]


async def _stay_hits(db: AsyncSession, tsq, limit: int) -> list[RetrievalHit]:
    stmt = (
        select(Stay)
        .where(Stay.search_vector.op("@@")(tsq))
        .order_by(func.ts_rank(Stay.search_vector, tsq).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_hit_from_stay(s) for s in result.scalars().all()]


async def _experience_hits(db: AsyncSession, tsq, limit: int) -> list[RetrievalHit]:
    stmt = (
        select(Experience)
        .where(Experience.search_vector.op("@@")(tsq))
        .order_by(func.ts_rank(Experience.search_vector, tsq).desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return [_hit_from_experience(e) for e in result.scalars().all()]


async def retrieve_grounding_context(
    db: AsyncSession,
    query: str,
    vector_search: VectorSearchService | None = None,
    limit: int = MAX_HITS,
) -> list[RetrievalHit]:
    """Retrieve real records relevant to ``query``.

    Order of preference:
    1. Qdrant semantic hits (POIs + experiences).
    2. PostgreSQL full-text hits (POIs, then stays, then experiences) to fill
       remaining slots — always available, and covers stays.

    Never raises: retrieval failures degrade to an empty list so the agent
    still runs. Hits are deduplicated by ``(kind, id)``.
    """
    hits: list[RetrievalHit] = []
    seen: set[tuple[str, str]] = set()

    def add(hit: RetrievalHit) -> None:
        key = (hit.kind, str(hit.id))
        if key not in seen:
            seen.add(key)
            hits.append(hit)

    if vector_search is not None:
        try:
            for poi_id in vector_search.search(query, limit=limit):
                poi = await db.get(POI, poi_id)
                if poi:
                    add(_hit_from_poi(poi))
            for exp_id in vector_search.search_experiences(query, limit=limit):
                exp = await db.get(Experience, exp_id)
                if exp:
                    add(_hit_from_experience(exp))
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG vector retrieval failed, using SQL fallback: %s", exc)

    if len(hits) >= limit:
        return hits[:limit]

    missing = limit - len(hits)
    tsq = func.plainto_tsquery("french", query)
    try:
        for hit in await _poi_hits(db, tsq, missing):
            add(hit)
        for hit in await _stay_hits(db, tsq, missing):
            add(hit)
        for hit in await _experience_hits(db, tsq, missing):
            add(hit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG SQL retrieval failed: %s", exc)

    return hits[:limit]


def render_grounding_context(query: str, hits: list[RetrievalHit]) -> str:
    """Render hits as a compact markdown block for prompt injection."""
    if not hits:
        return ""
    lines = [
        "\n\n## REAL DATA (retrieval grounding)",
        f"Real records from the ATHAR database matching '{query[:120]}'. "
        "Rely on these and cite them by name; prefer them over general knowledge:",
    ]
    lines.extend(h.render() for h in hits)
    return "\n".join(lines)


def should_ground(message: str) -> bool:
    """Heuristic gate: skip RAG for off-topic greetings and pure transport queries.

    Transport questions are answered through ``get_transport_route``/schedules
    and don't need POI grounding; greetings add noise and waste tokens.
    """
    text = " ".join(message.strip().lower().split())
    if len(text) < 6:
        return False
    if any(token in text for token in _OFF_TOPIC):
        return False
    return not any(token in text for token in _TRANSPORT_HINTS)
