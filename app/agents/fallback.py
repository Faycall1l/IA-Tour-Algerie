"""Rule-based degradation fallback for the agent endpoints.

When the LLM backend is down (circuit breaker open, run timeout, or no API
key configured) the agent endpoints would otherwise answer 503. This module
implements a *conservative* rule-based responder that answers the most common
query shapes directly — by calling the exact same validated tools the agents
use, with no LLM in the loop.

It only answers when the intent is clear and data is actually returned;
anything it can't classify confidently falls through to a 503 so clients are
never handed a confident-sounding but wrong answer. The itinerary planner is
intentionally excluded: a day-by-day plan needs real reasoning.
"""

import logging
import re
import unicodedata
from typing import TYPE_CHECKING

from sqlalchemy import text

from app.agents.links import AgentLink, links_from_tool_output
from app.agents.resilience import RunContextProvider
from app.agents.tools import (
    EventSearchParams,
    ExperienceSearchParams,
    OperatorContactsParams,
    POISearchParams,
    StaySearchParams,
    TransportRouteParams,
    WilayaGuideParams,
    find_events,
    get_operator_contacts,
    get_transport_route,
    get_wilaya_guide,
    search_experiences,
    search_pois,
    search_stays,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5

# ── Handler result unpacking ──
# Handlers return ``(text | None, links)``. Some tests monkeypatch a handler
# with a plain-string stub (older shape), so callers must unpack defensively.


def _unpack_handler(out) -> tuple[str | None, list[AgentLink]]:
    if isinstance(out, tuple):
        return out
    return out, []

# ── Text folding ──
# Normalize the user message so keyword/name matching is accent- and
# case-insensitive: "Béjaïa" -> "bejaia", "musée" -> "musee".


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


# ── Wilaya resolution ──
# Names come from the DB (id + name_en/name_ar/name_fr), folded, so aliases
# like "Sétif"/"setif" and "أدرار" (Arabic folds to empty, harmless) resolve.


async def _wilaya_alias_table(deps) -> dict[int, list[str]]:
    aliases: dict[int, list[str]] = {}
    try:
        rows = await deps.db.execute(text("SELECT id, name_en, name_ar, name_fr FROM wilayas"))
        for r in rows.all():
            names = {str(x) for x in (r[1], r[2], r[3]) if x}
            aliases[int(r[0])] = [_fold(n) for n in names if _fold(n)]
    except Exception as e:  # pragma: no cover — degraded path must never throw
        logger.warning("Failed to load wilaya aliases: %s", e)
    return aliases


async def _resolve_wilaya(deps, folded: str) -> tuple[int, str] | None:
    """Return ``(wilaya_id, matched_alias)`` for the most specific match, if any."""
    if not folded:
        return None
    table = await _wilaya_alias_table(deps)
    best: tuple[int, int, str] | None = None  # (alias_len, id, alias)
    for id_, names in table.items():
        for alias in names:
            if (
                len(alias) >= 3
                and f" {alias} " in f" {folded} "
                and (best is None or len(alias) > best[0])
            ):
                best = (len(alias), id_, alias)
    if best is None:
        return None
    return best[1], best[2]


async def _resolve_wilayas_in_order(deps, folded: str) -> list[tuple[int, str]]:
    """Resolve wilayas ordered by first occurrence, longest alias wins per id."""
    if not folded:
        return []
    table = await _wilaya_alias_table(deps)
    matches: list[tuple[int, int, int, str]] = []  # (pos, alias_len, id, alias)
    for id_, names in table.items():
        for alias in names:
            if len(alias) < 3:
                continue
            m = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", folded)
            if m:
                matches.append((m.start(), len(alias), id_, alias))
    best_by_id: dict[int, tuple[int, int, str]] = {}
    for pos, alen, id_, alias in matches:
        cur = best_by_id.get(id_)
        if cur is None or alen > cur[1]:
            best_by_id[id_] = (pos, alen, alias)
    ordered = sorted(best_by_id.items(), key=lambda kv: kv[1][:2])
    return [(id_, t[2]) for id_, t in ordered]


def _remove_alias(folded: str, alias: str) -> str:
    if not alias:
        return folded
    return re.sub(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", " ", folded).strip()


#: Words that add no signal to a full-text query. PostgreSQL's French config
#: does not treat these as stopwords, so AND-chaining them into the query (e.g.
#: `plainto_tsquery('french', 'beaches in')` -> `'beach' & 'in'`) silently kills
#: otherwise-valid matches. The fallback strips them before searching.
_STOPWORDS = {
    "a",
    "about",
    "am",
    "an",
    "and",
    "any",
    "are",
    "around",
    "as",
    "at",
    "au",
    "aux",
    "avec",
    "be",
    "by",
    "can",
    "ce",
    "ces",
    "cette",
    "d",
    "dans",
    "de",
    "des",
    "do",
    "does",
    "du",
    "en",
    "et",
    "for",
    "from",
    "get",
    "go",
    "has",
    "have",
    "how",
    "i",
    "in",
    "is",
    "it",
    "l",
    "la",
    "le",
    "les",
    "me",
    "my",
    "near",
    "next",
    "of",
    "on",
    "or",
    "ou",
    "pour",
    "que",
    "qui",
    "s",
    "se",
    "show",
    "some",
    "sur",
    "t",
    "tell",
    "the",
    "there",
    "these",
    "they",
    "to",
    "un",
    "une",
    "vers",
    "want",
    "was",
    "what",
    "where",
    "which",
    "with",
    "you",
}


def _content_query(folded: str, alias: str | None = None) -> str:
    """Build a full-text query from the folded message, minus stopwords.

    Removes the resolved wilaya alias (so ``search_vector`` rows don't need to
    mention the wilaya name) and strips function words that the French tsquery
    parser would otherwise AND into the query as hard terms.
    """
    text_ = _remove_alias(folded, alias) if alias else folded
    tokens = [t for t in text_.split() if t not in _STOPWORDS]
    return " ".join(tokens) or text_


# ── Keyword helpers ──


def _has_keywords(folded: str, pattern: str) -> bool:
    return re.search(rf"\b({pattern})\w*\b", folded) is not None


_POI_WORDS = (
    "poi|attraction|sight|site|monument|mosque|museum|musee|beach|plage|"
    "restaurant|cafe|coffee|park|garden|market|souq|souk|bazar|fort|palace|"
    "ruin|histor|roman|archaeol|cathedral|hammam|spring|mountain|peak|"
    "waterfall|canyon|grotto|oasis|theatre|theater|culture|food|eat|dinner|lunch"
)

_STAY_WORDS = "hotel|stay|sleep|accommodat|riad|guesthouse|hostel|auberge|bed.and.breakfast|camp"

_EVENT_WORDS = (
    "festival|event|concert|celebration|fair|feast|fete|mawlid|ramadan|eid|yennayer|gala|week"
)

_EXPERIENCE_WORDS = (
    "experience|tour|excursion|hike|trek|safari|workshop|day.trip|boat|camel|quad|wander"
)

_GUIDE_WORDS = (
    "see|do|visit|guide|attraction|explore|must.see|tourist|discover|things.to|what.to|about|info"
)

_OPERATOR_NAMES = (
    "sntf|air.algerie|sogral|etusa|setram|entmv|ento|goby.taxi|yassir|time.taxi|taxi|operator"
)

_OPERATOR_INTENT_WORDS = (
    "phone|contact|number|call|helpline|hotline|reachable|reach|ticket|reservation|where.can.i.call"
)


def _has_operator_intent(folded: str) -> bool:
    return (
        _has_keywords(folded, _OPERATOR_INTENT_WORDS)
        or re.search(rf"\b({_OPERATOR_NAMES})\b", folded) is not None
    )


_TRANSPORT_WORDS = (
    "bus|train|flight|fly|flying|plane|airplane|taxi|tram|ferry|coach|"
    "drive|driving|metro|commute|transport|route|connection|transfer|"
    "vol|navette|avion|transfert|bateau"
)

_TRANSPORT_PHRASES = (
    "how do i get to",
    "how to get to",
    "how do i reach",
    "how to reach",
    "best way to reach",
    "way to reach",
    "get to",
    "get from",
    "go from",
    "go to",
    "travel to",
    "journey to",
)


def _has_transport_intent(folded: str) -> bool:
    """True when the query is primarily about getting somewhere."""
    if _has_keywords(folded, _TRANSPORT_WORDS):
        return True
    return any(p in folded for p in _TRANSPORT_PHRASES)


async def _ordered_route_wilayas(
    deps, folded: str, from_wilaya: int | None, to_wilaya: int | None
) -> tuple[int, int] | None:
    """Resolve (origin, destination) honoring 'to X from Y' phrasing."""
    if from_wilaya and to_wilaya:
        return from_wilaya, to_wilaya
    resolved = await _resolve_wilayas_in_order(deps, folded)
    if len(resolved) < 2:
        return None
    fw, tw = resolved[0][0], resolved[1][0]
    from_pos = folded.find(" from ")
    if from_pos >= 0:
        origin = next((w for w, alias in resolved if folded.find(alias) > from_pos), None)
        if origin is not None and origin != fw:
            fw, tw = origin, fw
    if fw == tw:
        return None
    return fw, tw


# ── Category/field detection (for precise tool filters) ──

_POI_CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "beach": ("beach", "plage", "seaside"),
    "museum": ("museum", "musee"),
    "restaurant": ("restaurant", "food", "eat", "dinner", "lunch", "brunch"),
    "cafe": ("cafe", "coffee", "tea"),
    "historical": (
        "histor",
        "ruin",
        "roman",
        "monument",
        "fort",
        "palace",
        "castle",
        "archaeol",
        "antiqu",
    ),
    "religious": (
        "mosque",
        "church",
        "cathedral",
        "mausole",
        "zawiya",
        "synagog",
        "shrine",
        "tomb",
    ),
    "mountain": ("mountain", "peak", "summit", "ridge", "jebel"),
    "park": ("park", "garden"),
    "market": ("market", "souq", "souk", "bazaar", "bazar", "medina"),
    "thermal": ("thermal", "hot spring", "spa"),
    "natural": ("waterfall", "canyon", "gorge", "oasis", "grotto", "cave", "lake", "forest"),
    "cultural": ("theatre", "theater", "opera", "library", "casbah", "kasbah", "hammam"),
}


def _detect_poi_category(text: str) -> str | None:
    folded = _fold(text)
    if not folded:
        return None
    for category, words in _POI_CATEGORY_WORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\w*\b", folded):
                return category
    return None


_EVENT_CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "music": ("music", "concert", "jazz", "rai", "festival de musique"),
    "food": ("food", "cuisine", "couscous", "gastronom", "taste"),
    "religious": ("religious", "mawlid", "eid", "ramadan", "islamic"),
    "hiking": ("hike", "trek", "mountain", "trail"),
    "beach": ("beach", "sea", "surf", "coast"),
    "adventure": ("adventure", "desert", "safari", "rally", "race"),
    "cultural": ("cultural", "tradition", "heritage", "craft", "dance"),
}


def _detect_event_category(text: str) -> str | None:
    folded = _fold(text)
    if not folded:
        return None
    for category, words in _EVENT_CATEGORY_WORDS.items():
        for w in words:
            if re.search(rf"\b{re.escape(w)}\w*\b", folded):
                return category
    return None


_MONTHS = {
    "january": 1,
    "janvier": 1,
    "february": 2,
    "fevrier": 2,
    "février": 2,
    "march": 3,
    "mars": 3,
    "april": 4,
    "avril": 4,
    "may": 5,
    "mai": 5,
    "june": 6,
    "juin": 6,
    "july": 7,
    "juillet": 7,
    "august": 8,
    "aout": 8,
    "août": 8,
    "september": 9,
    "septembre": 9,
    "october": 10,
    "octobre": 10,
    "november": 11,
    "novembre": 11,
    "december": 12,
    "decembre": 12,
    "décembre": 12,
}


def _detect_month(text: str) -> int | None:
    folded = _fold(text)
    if not folded:
        return None
    for name, month in _MONTHS.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(_fold(name))}(?![a-z0-9])", folded):
            return month
    return None


# ── Handlers (call the same tools the agents use) ──


async def _handle_wilaya_guide(deps, wilaya_id: int) -> tuple[str | None, list[AgentLink]]:
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await get_wilaya_guide(
            ctx, WilayaGuideParams(wilaya_id=wilaya_id, top_per_category=3)
        )
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback wilaya guide failed: %s", e)
        return None, []
    if not (
        out.featured_pois
        or out.categories
        or out.top_stays
        or out.top_experiences
        or out.upcoming_events
    ):
        return None, []

    links = links_from_tool_output("get_wilaya_guide", out)
    lines = [f"{out.wilaya_name} — travel guide"]
    if out.description:
        lines.append(out.description)
    for tip in out.tips:
        lines.append(f"- {tip}")
    if out.featured_pois:
        lines.append("\nMust-see:")
        for p in out.featured_pois[:_MAX_RESULTS]:
            fee = f" ({p.price_level})" if p.price_level else ""
            lines.append(f"• {p.name} — {p.category}{fee}")
    for cat in out.categories:
        lines.append(f"\n{cat.category} ({cat.count}):")
        for p in cat.pois[:_MAX_RESULTS]:
            fee = f" ({p.price_level})" if p.price_level else ""
            snippet = f" — {p.description}" if p.description else ""
            lines.append(f"• {p.name}{fee}{snippet}")
    if out.top_stays:
        lines.append("\nWhere to stay:")
        for s in out.top_stays[:3]:
            lines.append(f"• {s.name} ({s.property_type}) — {s.price_per_night_dzd:.0f} DZD/night")
    if out.top_experiences:
        lines.append("\nExperiences:")
        for x in out.top_experiences[:3]:
            price = f" — {x.price_dzd:.0f} DZD" if x.price_dzd else ""
            lines.append(f"• {x.title} ({x.category}){price}")
    if out.upcoming_events:
        lines.append("\nUpcoming events:")
        for ev in out.upcoming_events[:3]:
            lines.append(f"• {ev.title} — month {ev.month}")
    lines.append("\n(Offline guide — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


async def _handle_poi_search(
    folded: str, deps, wilaya: tuple[int, str] | None
) -> tuple[str | None, list[AgentLink]]:
    query = _content_query(folded, wilaya[1] if wilaya else None)[:200] or folded[:200]
    params = POISearchParams(
        query=query,
        wilaya_id=wilaya[0] if wilaya else None,
        category=_detect_poi_category(folded),
        limit=_MAX_RESULTS,
    )
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await search_pois(ctx, params)
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback POI search failed: %s", e)
        return None, []
    if not out.results:
        return None, []

    links = links_from_tool_output("search_pois", out)
    lines = [f'Points of interest matching "{query}":']
    for r in out.results[:_MAX_RESULTS]:
        price = r.price_level or "Free"
        duration = f", ~{r.suggested_duration_min} min" if r.suggested_duration_min else ""
        snippet = f" — {r.description}" if r.description else ""
        lines.append(f"• {r.name} ({r.category}) — {price}{duration}{snippet}")
    lines.append("\n(Offline search — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


async def _handle_stays(
    folded: str, deps, wilaya: tuple[int, str] | None
) -> tuple[str | None, list[AgentLink]]:
    query = _content_query(folded, wilaya[1] if wilaya else None)[:200] or folded[:200]
    params = StaySearchParams(
        query=query,
        wilaya_id=wilaya[0] if wilaya else None,
        limit=_MAX_RESULTS,
    )
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await search_stays(ctx, params)
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback stay search failed: %s", e)
        return None, []
    if not out.results:
        return None, []

    links = links_from_tool_output("search_stays", out)
    where = f" in wilaya {wilaya[0]}" if wilaya else ""
    lines = [f'Accommodation{where} matching "{query}":']
    for r in out.results[:_MAX_RESULTS]:
        lines.append(f"• {r.name} ({r.property_type}) — {r.price_per_night_dzd:.0f} DZD/night")
    lines.append("\n(Offline search — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


async def _handle_experiences(
    folded: str, deps, wilaya: tuple[int, str] | None
) -> tuple[str | None, list[AgentLink]]:
    query = _content_query(folded, wilaya[1] if wilaya else None)[:200] or folded[:200]
    params = ExperienceSearchParams(
        query=query,
        wilaya_id=wilaya[0] if wilaya else None,
        limit=_MAX_RESULTS,
    )
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await search_experiences(ctx, params)
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback experience search failed: %s", e)
        return None, []
    if not out.results:
        return None, []

    links = links_from_tool_output("search_experiences", out)
    lines = [f'Experiences matching "{query}":']
    for r in out.results[:_MAX_RESULTS]:
        price = f", {r.price_dzd:.0f} DZD" if r.price_dzd else ""
        duration = f", ~{r.duration_hours:.0f}h" if r.duration_hours else ""
        lines.append(f"• {r.title} ({r.category}){price}{duration}")
    lines.append("\n(Offline search — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


async def _handle_transport_route(
    deps, from_wilaya: int, to_wilaya: int
) -> tuple[str | None, list[AgentLink]]:
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await get_transport_route(
            ctx, TransportRouteParams(origin_wilaya_id=from_wilaya, dest_wilaya_id=to_wilaya)
        )
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback transport route failed: %s", e)
        return None, []
    if not out.options:
        return None, []

    links = links_from_tool_output("get_transport_route", out)
    lines = [f"How to get from {out.origin_wilaya} to {out.dest_wilaya}:"]
    for o in out.options[:_MAX_RESULTS]:
        cost = f", {o.cost_dzd:.0f} DZD" if o.cost_dzd else ""
        duration = ""
        if o.duration_min:
            h, m = divmod(o.duration_min, 60)
            duration = f", ~{h}h{m:02d}" if m else f", ~{h}h"
        op = f" ({o.operator})" if o.operator else ""
        transfers = f", {o.transfers} transfer(s)" if o.transfers else ""
        lines.append(f"• {o.mode}: {o.line_name or '—'}{op}{cost}{duration}{transfers}")
        if o.contacts and o.contacts[0].phone:
            phones = "; ".join(c.phone for c in o.contacts[:2] if c.phone)
            if phones:
                lines.append(f"  tel: {phones}")
    if out.best_recommendation:
        lines.append(f"\nBest: {out.best_recommendation}")
    lines.append("\n(Offline schedule — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


async def _handle_operators(folded: str, deps) -> tuple[str | None, list[AgentLink]]:
    mode = None
    for m in ("train", "flight", "bus", "taxi", "tram", "cablecar"):
        if re.search(rf"\b{m}\w*\b", folded):
            mode = m
            break
    wilaya = await _resolve_wilaya(deps, folded)
    params = OperatorContactsParams(
        mode=mode,
        wilaya_id=wilaya[0] if wilaya else None,
    )
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await get_operator_contacts(ctx, params)
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback operator contacts failed: %s", e)
        return None, []
    if not out.results:
        return None, []

    title = f"Transport operator contacts ({mode})" if mode else "Transport operator contacts"
    lines = [title]
    for r in out.results[:_MAX_RESULTS]:
        parts = [r.name]
        if r.phone:
            parts.append(f"tel: {r.phone}")
        if r.website:
            parts.append(r.website)
        if r.mode and r.mode != mode:
            parts.append(f"[{r.mode}]")
        lines.append("• " + " — ".join(parts))
    lines.append("\n(Offline directory — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), []


async def _handle_events(
    folded: str, deps, wilaya: tuple[int, str] | None
) -> tuple[str | None, list[AgentLink]]:
    params = EventSearchParams(
        wilaya_id=wilaya[0] if wilaya else None,
        category=_detect_event_category(folded),
        month=_detect_month(folded),
        limit=_MAX_RESULTS,
    )
    ctx = RunContextProvider.for_tool(deps)
    try:
        out = await find_events(ctx, params)
    except Exception as e:  # pragma: no cover
        logger.warning("Fallback events search failed: %s", e)
        return None, []
    if not out.results:
        return None, []

    links = links_from_tool_output("find_events", out)
    lines = ["Events & festivals:"]
    for r in out.results[:_MAX_RESULTS]:
        desc = f" — {r.description}" if r.description else ""
        lines.append(f"• {r.title} ({r.category}, month {r.month}){desc}")
    lines.append("\n(Offline calendar — the AI assistant is temporarily unavailable)")
    return "\n".join(lines), links


# ── Per-agent fallback routing ──


async def _travel_fallback(folded: str, deps) -> tuple[str | None, list[AgentLink]]:
    # Most specific intents first.
    if _has_transport_intent(folded):
        route = await _ordered_route_wilayas(deps, folded, None, None)
        if route:
            out = await _handle_transport_route(deps, route[0], route[1])
            text, links = _unpack_handler(out)
            if text:
                return text, links
    if _has_operator_intent(folded):
        out = await _handle_operators(folded, deps)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _STAY_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_stays(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _EVENT_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_events(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _POI_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_poi_search(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _GUIDE_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        if wilaya:
            out = await _handle_wilaya_guide(deps, wilaya[0])
            text, links = _unpack_handler(out)
            if text:
                return text, links
    return None, []


async def _search_fallback(folded: str, deps) -> tuple[str | None, list[AgentLink]]:
    if _has_keywords(folded, _STAY_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_stays(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _POI_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_poi_search(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_keywords(folded, _EXPERIENCE_WORDS):
        wilaya = await _resolve_wilaya(deps, folded)
        out = await _handle_experiences(folded, deps, wilaya)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_operator_intent(folded):
        out = await _handle_operators(folded, deps)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    # Anything about a specific wilaya → its curated guide.
    wilaya = await _resolve_wilaya(deps, folded)
    if wilaya:
        out = await _handle_wilaya_guide(deps, wilaya[0])
        text, links = _unpack_handler(out)
        if text:
            return text, links
    return None, []


async def _transport_fallback(
    folded: str,
    deps,
    from_wilaya: int | None,
    to_wilaya: int | None,
) -> tuple[str | None, list[AgentLink]]:
    route = await _ordered_route_wilayas(deps, folded, from_wilaya, to_wilaya)
    if route:
        out = await _handle_transport_route(deps, route[0], route[1])
        text, links = _unpack_handler(out)
        if text:
            return text, links
    if _has_operator_intent(folded):
        out = await _handle_operators(folded, deps)
        text, links = _unpack_handler(out)
        if text:
            return text, links
    return None, []


async def _events_fallback(folded: str, deps) -> tuple[str | None, list[AgentLink]]:
    wilaya = await _resolve_wilaya(deps, folded)
    out = await _handle_events(folded, deps, wilaya)
    text, links = _unpack_handler(out)
    return text, links


async def attempt_fallback_with_links(
    agent_name: str,
    message: str,
    deps,
    *,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> tuple[str | None, list[AgentLink]]:
    """Try to answer ``message`` without the LLM. Returns ``(text, links)`` or ``(None, [])``."""
    folded = _fold(message)
    if not folded:
        return None, []
    try:
        if agent_name == "transport_agent":
            return await _transport_fallback(folded, deps, from_wilaya, to_wilaya)
        if agent_name == "events_agent":
            return await _events_fallback(folded, deps)
        if agent_name == "search_agent":
            return await _search_fallback(folded, deps)
        if agent_name == "travel_agent":
            return await _travel_fallback(folded, deps)
    except Exception as e:  # pragma: no cover — degraded path must never throw
        logger.warning("Fallback responder failed for %s: %s", agent_name, e)
        return None, []
    # itinerary_agent: planning requires real reasoning — always fall through.
    return None, []


async def attempt_fallback(
    agent_name: str,
    message: str,
    deps,
    *,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> str | None:
    """Text-only fallback (backwards compatible). Returns text or ``None`` (no match)."""
    text, _links = await attempt_fallback_with_links(
        agent_name, message, deps, from_wilaya=from_wilaya, to_wilaya=to_wilaya
    )
    return text
