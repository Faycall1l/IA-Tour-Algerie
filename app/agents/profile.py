"""Traveler profile mining — cross-session preference extraction from messages.

Deterministic, no-LLM heuristics that extract durable traveler preferences from
a conversation turn: budget level, interests, home wilaya, and travel style.
Mining is deliberately conservative — only strong keyword signals are recorded,
and ``merge`` only overwrites an existing field when a fresh signal is present,
so the profile accumulates preferences across sessions without churn.

``render`` produces a compact ``TRAVELER PROFILE`` block injected into every
agent system prompt (see deps.profile_context), giving the model durable
context about who it is talking to.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.user_profile import UserProfile

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

MAX_INTERESTS = 6

# Budget keywords → canonical level. Longest/specific phrases win by priority
# order (first match in this dict ordering is taken for a given keyword group).
_BUDGET_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("low cost", "budget"),
    ("pas cher", "budget"),
    ("economique", "budget"),
    ("economy", "budget"),
    ("budget", "budget"),
    ("cheap", "budget"),
    ("haut de gamme", "luxury"),
    ("haut standing", "luxury"),
    ("5 etoiles", "luxury"),
    ("5 étoiles", "luxury"),
    ("5 etoile", "luxury"),
    ("luxe", "luxury"),
    ("luxury", "luxury"),
    ("premium", "luxury"),
    ("mid range", "mid-range"),
    ("milieu de gamme", "mid-range"),
    ("confortable", "mid-range"),
    ("mid-range", "mid-range"),
)

_INTEREST_KEYWORDS: dict[str, tuple[str, ...]] = {
    "beach": ("plage", "beach", "baignade", "mer", "sea", "sable"),
    "history": (
        "histoire",
        "history",
        "ruines",
        "ruins",
        "romaine",
        "roman",
        "musee",
        "museum",
        "casbah",
        "patrimoine",
        "archaeolog",
        "archeolog",
        "timgad",
        "djemila",
        "tipasa",
    ),
    "nature": (
        "nature",
        "montagne",
        "mountain",
        "randonnee",
        "hiking",
        "parc national",
        "cascade",
        "sahara",
        "desert",
        "oasis",
        "gouffre",
        "grotte",
    ),
    "food": (
        "restaurant",
        "cuisine",
        "food",
        "gastronomie",
        "couscous",
        "manger",
        "eat",
        "street food",
        "cafe",
    ),
    "culture": (
        "culture",
        "festival",
        "artisan",
        "marche",
        "market",
        "souq",
        "tradition",
        "yennayer",
    ),
    "adventure": (
        "aventure",
        "adventure",
        "trek",
        "escalade",
        "parapente",
        "4x4",
        "safari",
        "expedition",
    ),
    "relax": ("detente", "relax", "hammam", "spa", "thermal", "plage tranquille"),
    "family": ("famille", "family", "enfants", "kids", "children"),
}

_STYLE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("affaires", "business"),
    ("business", "business"),
    ("conference", "business"),
    ("famille", "family"),
    ("family", "family"),
    ("kids", "family"),
    ("trek", "adventure"),
    ("aventure", "adventure"),
    ("adventure", "adventure"),
    ("escalade", "adventure"),
    ("4x4", "adventure"),
    ("hammam", "relax"),
    ("spa", "relax"),
    ("detente", "relax"),
    ("relax", "relax"),
    ("gastronomie", "food"),
    ("food tour", "food"),
    ("food", "food"),
    ("cuisine", "food"),
    ("histoire", "cultural"),
    ("history", "cultural"),
    ("culture", "cultural"),
    ("musee", "cultural"),
    ("casbah", "cultural"),
    ("montagne", "nature"),
    ("nature", "nature"),
    ("randonnee", "nature"),
    ("hiking", "nature"),
    ("sahara", "nature"),
    ("solo", "solo"),
    ("seul", "solo"),
)


def _fold(text: str) -> str:
    """Lowercase and strip accents for keyword matching."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


@dataclass
class MinedProfile:
    """Signals extracted from a single message."""

    budget_level: str | None = None
    interests: list[str] = field(default_factory=list)
    home_wilaya_id: int | None = None
    travel_style: str | None = None

    @property
    def is_empty(self) -> bool:
        return not (self.budget_level or self.interests or self.home_wilaya_id or self.travel_style)


def _mine_budget(folded: str) -> str | None:
    for phrase, level in _BUDGET_KEYWORDS:
        if phrase in folded:
            return level
    return None


def _mine_interests(folded: str) -> list[str]:
    found: list[str] = []
    for interest, keywords in _INTEREST_KEYWORDS.items():
        if any(kw in folded for kw in keywords):
            found.append(interest)
    return found[:MAX_INTERESTS]


def _mine_style(folded: str) -> str | None:
    for phrase, style in _STYLE_KEYWORDS:
        if phrase in folded:
            return style
    return None


async def _mine_wilaya(db: AsyncSession, folded: str) -> int | None:
    from app.models.wilaya import Wilaya

    result = await db.execute(select(Wilaya.id, Wilaya.name_fr, Wilaya.name_en, Wilaya.name_ar))
    best: tuple[int, int] | None = None  # (alias_len, wilaya_id)
    for wid, fr, en, ar in result.all():
        for alias in (fr, en, ar):
            if not alias:
                continue
            a = _fold(alias)
            if len(a) < 3 or a not in folded:
                continue
            if best is None or len(a) > best[0]:
                best = (len(a), wid)
    return best[1] if best else None


async def mine_profile(db: AsyncSession, message: str) -> MinedProfile:
    """Extract durable preferences from a message (deterministic, no LLM)."""
    folded = _fold(message)
    return MinedProfile(
        budget_level=_mine_budget(folded),
        interests=_mine_interests(folded),
        home_wilaya_id=await _mine_wilaya(db, folded),
        travel_style=_mine_style(folded),
    )


def merge(profile: UserProfile, mined: MinedProfile) -> list[str]:
    """Merge mined signals into an existing profile; return changed fields.

    Only non-None signals overwrite; interests are unioned (capped) so earlier
    interests survive later messages. Returns the list of changed field names
    so callers can skip the commit when nothing changed.
    """
    changed: list[str] = []

    def _set(name: str, value) -> None:
        if value is None:
            return
        current = getattr(profile, name)
        if current == value:
            return
        setattr(profile, name, value)
        changed.append(name)

    _set("budget_level", mined.budget_level)
    _set("travel_style", mined.travel_style)
    _set("home_wilaya_id", mined.home_wilaya_id)

    if mined.interests:
        existing = set(profile.interests or [])
        merged = list(existing)
        for interest in mined.interests:
            if interest not in existing:
                merged.append(interest)
        merged = merged[:MAX_INTERESTS]
        if merged != profile.interests:
            profile.interests = merged
            changed.append("interests")

    return changed


def render(profile: UserProfile, wilaya_name: str | None = None) -> str:
    """Render the profile as a compact prompt-injection block ("" when empty)."""
    lines: list[str] = []
    if profile.budget_level:
        lines.append(f"Budget: {profile.budget_level}")
    if profile.interests:
        lines.append(f"Interests: {', '.join(profile.interests)}")
    if profile.travel_style:
        lines.append(f"Travel style: {profile.travel_style}")
    if profile.preferred_language:
        lines.append(f"Preferred language: {profile.preferred_language}")
    if profile.home_wilaya_id:
        home = wilaya_name or profile.home_wilaya_id
        lines.append(f"Home wilaya: {home} (w{profile.home_wilaya_id})")
    if not lines:
        return ""
    return "\n\n## TRAVELER PROFILE\n" + "\n".join(lines)


async def load_or_create_profile(db: AsyncSession, user_id) -> UserProfile:
    """Load the user's profile, creating an empty one on first use."""
    profile = await db.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile
