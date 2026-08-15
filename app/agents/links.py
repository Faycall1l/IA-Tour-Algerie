"""Structured deep links attached to agent replies.

Every agent reply that references concrete entities (POIs, stays, experiences,
events, artisans, wilayas, transport routes) now carries a machine-readable
``links`` array so the frontend can render tappable cards and deep links next
to the answer.

Two producers feed the same extraction logic:

- **LLM path**: ``collect_links_from_result`` walks the tool messages a
  Pydantic AI run produced (``all_messages()``), parses each ``tool-return``
  payload (a JSON string of the validated tool output) and turns it into links.
  ``run_agent_safely`` stores the result on the run trace under
  ``metadata["links"]`` as plain dicts (the trace is JSON-logged).
- **Fallback path**: the rule-based responder calls the same validated tools,
  so ``links_from_tool_output`` reuses the extraction on the raw tool output —
  no LLM required.

Link URLs are frontend-facing deep links, not API calls. When no frontend URL
is configured (``ATHAR_APP_URL`` empty) they stay relative so a web client can
resolve them against its own origin.
"""

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

LinkType = Literal["poi", "stay", "experience", "event", "artisan", "wilaya", "transport"]


class AgentLink(BaseModel):
    """A single deep link surfaced to the client alongside an agent reply."""

    type: LinkType
    id: str
    name: str
    url: str
    wilaya_id: int | None = Field(
        None, description="Related wilaya (entity location / transport origin)"
    )


#: Max links returned per reply — enough for a rich answer without overwhelming
#: the client or the memory store.
MAX_LINKS = 8

#: Entity pages on the frontend, keyed by AgentLink.type.
_RESOURCE_PATHS: dict[str, str] = {
    "poi": "/pois/{id}",
    "stay": "/stays/{id}",
    "experience": "/experiences/{id}",
    "event": "/events/{id}",
    "artisan": "/artisans/{id}",
    "wilaya": "/wilayas/{id}",
}


def _base_url() -> str:
    """Frontend origin for deep links (empty string → relative URLs)."""
    try:
        from app.core.config import settings

        return (settings.app_url or "").rstrip("/")
    except Exception:  # pragma: no cover — never let link building crash the run
        return ""


def link_url(link_type: str, entity_id: Any) -> str:
    """Build the frontend deep link for an entity page."""
    path_tmpl = _RESOURCE_PATHS.get(link_type)
    if path_tmpl is None:
        return ""
    path = path_tmpl.format(id=entity_id)
    base = _base_url()
    return f"{base}{path}" if base else path


def transport_link(origin_wilaya: Any, dest_wilaya: Any) -> str:
    """Build the transport deep link between two wilayas."""
    path = f"/transport/plan?from_wilaya={origin_wilaya}&to_wilaya={dest_wilaya}"
    base = _base_url()
    return f"{base}{path}" if base else path


def _as_dict(value: Any) -> dict | None:
    """Normalize a tool output / message payload into a dict.

    pydantic-ai 2.x hands us outputs as Pydantic models, JSON strings, or plain
    dicts depending on the version and code path; accept all three.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:  # pragma: no cover
            return None
    return None


def _entity_links(
    items: Any,
    link_type: str,
    name_key: str,
    wilaya_id: int | None = None,
) -> list[AgentLink]:
    """Build links from a ``results``-style list of entity dicts."""
    links: list[AgentLink] = []
    for item in items or []:
        d = _as_dict(item)
        if not d:
            continue
        entity_id = d.get("id")
        if not entity_id:
            continue
        name = d.get(name_key) or f"{link_type.title()} {entity_id}"
        links.append(
            AgentLink(
                type=link_type,  # type: ignore[arg-type]
                id=str(entity_id),
                name=str(name),
                url=link_url(link_type, entity_id),
                wilaya_id=wilaya_id if wilaya_id is not None else d.get("wilaya_id"),
            )
        )
    return links


def _poi_links(d: dict, wilaya_id: int | None = None) -> list[AgentLink]:
    return _entity_links(d.get("results", d.get("featured_pois", [])), "poi", "name", wilaya_id)


def _stay_links(d: dict, wilaya_id: int | None = None) -> list[AgentLink]:
    return _entity_links(d.get("results", d.get("top_stays", [])), "stay", "name", wilaya_id)


def _experience_links(d: dict, wilaya_id: int | None = None) -> list[AgentLink]:
    return _entity_links(
        d.get("results", d.get("top_experiences", [])), "experience", "title", wilaya_id
    )


def _artisan_links(d: dict) -> list[AgentLink]:
    return _entity_links(d.get("results", []), "artisan", "name")


def _event_links(d: dict, wilaya_id: int | None = None) -> list[AgentLink]:
    return _entity_links(d.get("results", d.get("upcoming_events", [])), "event", "title", wilaya_id)


def _wilaya_guide_links(d: dict) -> list[AgentLink]:
    links: list[AgentLink] = []
    wid = d.get("wilaya_id")
    wname = d.get("wilaya_name")
    if wid:
        links.append(
            AgentLink(
                type="wilaya",
                id=str(wid),
                name=str(wname or f"Wilaya {wid}"),
                url=link_url("wilaya", wid),
                wilaya_id=int(wid),
            )
        )
    links += _poi_links(d, int(wid) if wid else None)
    for cat in d.get("categories") or []:
        cd = _as_dict(cat)
        if cd:
            links += _entity_links(cd.get("pois", []), "poi", "name", int(wid) if wid else None)
    links += _stay_links(d, int(wid) if wid else None)
    links += _experience_links(d, int(wid) if wid else None)
    links += _event_links(d, int(wid) if wid else None)
    return links


def _transport_links(d: dict) -> list[AgentLink]:
    o = d.get("origin_wilaya_id")
    t = d.get("dest_wilaya_id")
    if not o or not t:
        return []
    origin = d.get("origin_wilaya") or f"Wilaya {o}"
    dest = d.get("dest_wilaya") or f"Wilaya {t}"
    return [
        AgentLink(
            type="transport",
            id=f"{o}:{t}",
            name=f"Transport {origin} → {dest}",
            url=transport_link(o, t),
            wilaya_id=int(o),
        )
    ]


#: Tool name → extractor for its validated output model.
_TOOL_LINKERS: dict[str, callable] = {
    "search_pois": _poi_links,
    "search_stays": _stay_links,
    "search_experiences": _experience_links,
    "search_artisans": _artisan_links,
    "find_events": _event_links,
    "get_wilaya_guide": _wilaya_guide_links,
    "get_transport_route": _transport_links,
}


def links_from_tool_output(tool_name: str, output: Any) -> list[AgentLink]:
    """Extract structured links from a tool's validated output.

    Shared by the LLM path (tool-return payloads) and the rule-based fallback
    (direct tool calls) so both producers emit identical links.
    """
    d = _as_dict(output)
    if not d:
        return []
    linker = _TOOL_LINKERS.get(tool_name)
    if linker is None:
        return []
    try:
        return linker(d)
    except Exception as e:  # pragma: no cover — extraction must never fail a run
        logger.debug("Failed to extract links from %s output: %s", tool_name, e)
        return []


def collect_links_from_result(result, max_links: int = MAX_LINKS) -> list[AgentLink]:
    """Collect links from every ``tool-return`` message part of an agent run.

    Defensive across pydantic-ai message shapes (dict or object parts) and
    tolerant of mocked results with no messages. Deduplicates by ``(type, id)``
    and caps the list so it stays compact.
    """
    links: list[AgentLink] = []
    seen: set[tuple[str, str]] = set()
    try:
        for message in result.all_messages():
            for part in getattr(message, "parts", []) or []:
                if isinstance(part, dict):
                    kind = part.get("part_kind")
                    tool_name = part.get("tool_name")
                    content = part.get("content")
                else:
                    kind = getattr(part, "part_kind", None)
                    tool_name = getattr(part, "tool_name", None)
                    content = getattr(part, "content", None)
                if kind != "tool-return" or not tool_name:
                    continue
                for link in links_from_tool_output(tool_name, content):
                    key = (link.type, link.id)
                    if key in seen:
                        continue
                    seen.add(key)
                    links.append(link)
                    if len(links) >= max_links:
                        return links
    except Exception as e:  # pragma: no cover — observability must never break a run
        logger.debug("Failed to collect links from run result: %s", e)
    return links


def render_links_section(links: list[AgentLink], max_links: int = 5) -> str:
    """Render a plain-text footer of links to append to the chat reply.

    The structured ``links`` array is the primary consumer-facing surface; this
    footer only helps plain-text clients that cannot render structured data.
    """
    if not links:
        return ""
    lines = ["\n\nQuick links:"]
    for link in links[:max_links]:
        lines.append(f"- {link.name}: {link.url}")
    return "\n".join(lines)
