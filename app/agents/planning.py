"""Plan → verify for structured trip itineraries.

Two pieces:

- ``render_trip_plan`` turns a structured ``TripPlan`` (the itinerary agent's
  ``output_type``) into readable markdown for chat clients.
- ``verify_trip_plan`` is the "verify" half of the plan→verify loop: every
  place the model named in the itinerary is resolved against the real ATHAR
  database (POIs + stays in the destination wilaya). Places that match a real
  record are annotated with the record id; places that match nothing are
  flagged so the user is never told to visit an invented landmark.

Deterministic by design — no LLM in the verify path. Matching is
substring-based on folded names ("Visit the Casbah" → "Casbah"), longest
match wins, names shorter than 4 folded characters are ignored to avoid
noisy generic hits.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Iterable
from types import SimpleNamespace

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.travel_agent import TripPlan

logger = logging.getLogger(__name__)

FOOD_SUBTYPES = {"restaurant", "cafe", "cafeteria", "fast_food", "ice_cream", "bar", "pub"}


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _render_day(day) -> str:
    lines = [f"### Day {day.day}"]
    if day.date:
        lines[0] += f" ({day.date})"
    if day.morning:
        lines.append(f"- **Morning:** {day.morning}")
    if day.afternoon:
        lines.append(f"- **Afternoon:** {day.afternoon}")
    if day.evening:
        lines.append(f"- **Evening:** {day.evening}")
    if day.meals:
        lines.append(f"- **Meals:** {', '.join(day.meals)}")
    if day.accommodation:
        lines.append(f"- **Stay:** {day.accommodation}")
    return "\n".join(lines)


def render_trip_plan(plan: TripPlan) -> str:
    """Render a structured ``TripPlan`` as readable markdown."""
    head = f"# Trip to {plan.destination} — {plan.duration_days} day(s) ({plan.budget_level})"
    sections = [head]
    for day in plan.itinerary:
        sections.append(_render_day(day))
    if plan.key_attractions:
        sections.append("### Must-see\n- " + "\n- ".join(plan.key_attractions))
    if plan.tips:
        sections.append("### Tips\n- " + "\n- ".join(plan.tips))
    if plan.estimated_budget_dzd:
        sections.append(f"**Estimated budget:** {plan.estimated_budget_dzd:,.0f} DZD")
    return "\n\n".join(sections)


# ── Verification models ──


class VerifiedEntry(BaseModel):
    """One place the itinerary named, with its real-data resolution."""

    name: str = Field(..., description="Place as written in the plan")
    kind: str = Field(..., description="poi | stay")
    found: bool = Field(..., description="True when a real ATHAR record matched")
    match_id: str | None = Field(None, description="DB id of the matched record")
    match_name: str | None = Field(None, description="Canonical name of the matched record")
    subtype: str | None = Field(None, description="Record subtype (e.g. museum, hotel)")
    wilaya_id: int | None = Field(None, description="Wilaya of the matched record")
    note: str | None = Field(None, description="Why it did not match, when applicable")


class VerifiedDay(BaseModel):
    day: int = Field(..., ge=1)
    entries: list[VerifiedEntry] = Field(default_factory=list)


class PlanVerification(BaseModel):
    """Result of verifying a TripPlan against the ATHAR database."""

    destination: str
    destination_found: bool
    destination_wilaya_id: int | None = None
    days: list[VerifiedDay] = Field(default_factory=list)
    found_count: int = 0
    missing_count: int = 0
    verified_ratio: float = Field(0.0, ge=0.0, le=1.0)


# ── Verifier ──


class _Candidate:
    """A folded name to search for inside itinerary text."""

    __slots__ = ("kind", "record_id", "display", "subtype", "wilaya_id", "folded", "length")

    def __init__(self, kind, record_id, display, subtype, wilaya_id, folded):
        self.kind = kind
        self.record_id = record_id
        self.display = display
        self.subtype = subtype
        self.wilaya_id = wilaya_id
        self.folded = folded
        self.length = len(folded)


async def _load_candidates(db: AsyncSession, wilaya_id: int) -> list[_Candidate]:
    """Load POI + stay names for a wilaya as folded match candidates."""
    candidates: list[_Candidate] = []
    try:
        rows = await db.execute(
            text(
                "SELECT id::text, name, name_en, subtype, wilaya_id "
                "FROM pois WHERE wilaya_id = :w AND name IS NOT NULL "
                "ORDER BY LENGTH(name) DESC LIMIT 1200"
            ),
            {"w": wilaya_id},
        )
        for rid, name, name_en, subtype, w in rows.all():
            for raw in (name, name_en):
                folded = _fold(raw or "")
                if len(folded) >= 4:
                    candidates.append(_Candidate("poi", rid, name, subtype, int(w), folded))
    except Exception as exc:  # noqa: BLE001 — verifier is best-effort
        logger.warning("Failed to load POI candidates: %s", exc)

    try:
        rows = await db.execute(
            text(
                "SELECT id::text, name, property_type, wilaya_id "
                "FROM stays WHERE wilaya_id = :w AND name IS NOT NULL "
                "ORDER BY LENGTH(name) DESC LIMIT 600"
            ),
            {"w": wilaya_id},
        )
        for rid, name, ptype, w in rows.all():
            folded = _fold(name or "")
            if len(folded) >= 4:
                candidates.append(_Candidate("stay", rid, name, ptype, int(w), folded))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load stay candidates: %s", exc)

    candidates.sort(key=lambda c: c.length, reverse=True)
    return candidates


def _split_items(field: str | None) -> list[str]:
    if not field:
        return []
    parts = re.split(r"[,;•·\n-]+", field)
    return [p.strip() for p in parts if p.strip()]


def _find_match(item: str, candidates: list[_Candidate], kinds: set[str]) -> _Candidate | None:
    folded = _fold(item)
    if len(folded) < 4:
        return None
    for cand in candidates:
        if cand.kind not in kinds:
            continue
        if f" {cand.folded} " in f" {folded} ":
            return cand
    return None


def _pick(
    item: str,
    candidates: list[_Candidate],
    preferred: set[str] | None,
) -> _Candidate | None:
    """Match an itinerary item, preferring a specific record kind when given."""
    if preferred:
        match = _find_match(item, candidates, preferred)
        if match:
            return match
    return _find_match(item, candidates, {"poi", "stay"})


def _verify_items(
    items: Iterable[str],
    candidates: list[_Candidate],
    *,
    preferred: set[str] | None = None,
    cap: int = 4,
) -> list[VerifiedEntry]:
    entries: list[VerifiedEntry] = []
    for item in items:
        if len(entries) >= cap:
            break
        match = _pick(item, candidates, preferred)
        if match:
            entries.append(
                VerifiedEntry(
                    name=item,
                    kind=match.kind,
                    found=True,
                    match_id=match.record_id,
                    match_name=match.display,
                    subtype=match.subtype,
                    wilaya_id=match.wilaya_id,
                )
            )
        else:
            entries.append(
                VerifiedEntry(
                    name=item,
                    kind="poi",
                    found=False,
                    note="Not found in ATHAR data",
                )
            )
    return entries


async def verify_trip_plan(db: AsyncSession, plan: TripPlan) -> PlanVerification:
    """Verify every named place in a TripPlan against the ATHAR database."""
    from app.agents.fallback import _resolve_wilaya

    wilaya_id: int | None = None
    try:
        resolved = await _resolve_wilaya(SimpleNamespace(db=db), _fold(plan.destination))
        if resolved:
            wilaya_id = resolved[0]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Destination wilaya resolution failed: %s", exc)

    candidates = await _load_candidates(db, wilaya_id) if wilaya_id else []

    days: list[VerifiedDay] = []
    for day in plan.itinerary:
        entries: list[VerifiedEntry] = []
        fields = [
            (day.morning, None, False),
            (day.afternoon, None, False),
            (day.evening, None, False),
            (day.accommodation, {"stay"}, False),
            (", ".join(day.meals), {"poi"}, True),
        ]
        for field, preferred, is_meals in fields:
            items = _split_items(field)
            if not items:
                continue
            for entry in _verify_items(
                items,
                candidates,
                preferred={"poi"} if is_meals else preferred,
                cap=3,
            ):
                entries.append(entry)
        # drop near-duplicate items that matched the same record
        seen: set[tuple[str, str]] = set()
        unique: list[VerifiedEntry] = []
        for e in entries:
            key = (e.kind, e.match_id or e.name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(e)
        days.append(VerifiedDay(day=day.day, entries=unique))

    found = sum(1 for d in days for e in d.entries if e.found)
    missing = sum(1 for d in days for e in d.entries if not e.found)
    total = found + missing
    return PlanVerification(
        destination=plan.destination,
        destination_found=wilaya_id is not None,
        destination_wilaya_id=wilaya_id,
        days=days,
        found_count=found,
        missing_count=missing,
        verified_ratio=round(found / total, 2) if total else 1.0,
    )


# ── Render verification ──


def render_verification(verification: PlanVerification) -> str:
    """Render verification as a concise, honest addendum to the plan text."""
    if verification.destination_found:
        head = f"### Verification — {verification.destination}"
        if verification.destination_wilaya_id:
            head += f" (wilaya {verification.destination_wilaya_id})"
    else:
        head = f"### Verification — {verification.destination} (destination not recognised)"
    lines = [head]
    for day in verification.days:
        parts: list[str] = []
        for entry in day.entries:
            if entry.found:
                parts.append(f"{entry.name} ✓")
            else:
                parts.append(f"{entry.name} ✗ not in ATHAR data")
        if parts:
            lines.append(f"- Day {day.day}: " + " · ".join(parts))
    if verification.found_count or verification.missing_count:
        total = verification.found_count + verification.missing_count
        lines.append(
            f"{verification.found_count} of {total} places confirmed against ATHAR data "
            f"({verification.verified_ratio:.0%})."
        )
    return "\n".join(lines)
