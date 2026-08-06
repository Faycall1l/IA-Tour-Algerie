"""Deterministic, path-based OpenAPI operation ids (S5).

FastAPI's default unique-id generator embeds the full path with the `api/v1`
prefix and path-parameter squiggles (e.g. `list_wilayas_api_v1_discover_wilayas_get`),
which pollutes generated client method names (dashboard's openapi-typescript
type names, mobile's openapi_flutter_gen API classes).

This scheme produces stable ids from the *route path + method* only, so IDs
survive function renames and read cleanly in SDKs:

    GET  /api/v1/discover/wilayas            -> get_discover_wilayas
    GET  /api/v1/discover/wilayas/{id}       -> get_discover_wilayas_id

Rules:
- method prefix: get/post/put/patch/delete
- `/api/v1` prefix stripped
- path/param segments underscored + joined
- lowercased
"""

from __future__ import annotations

import re
from collections.abc import Callable

from fastapi.routing import APIRoute

UniqueIdFunction = Callable[[APIRoute], str]


def _normalize(segment: str) -> str:
    """Lowercase a path/param segment and keep it `[a-z0-9_]`-safe."""
    s = segment.strip("{}").strip().lower()
    # replace any runs of non-alphanumeric (incl. hyphens) with underscore
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s


def generate_unique_id_function(route: APIRoute) -> str:
    methods = sorted(
        m.lower() for m in (route.methods or []) if m.lower() not in {"head", "options"}
    )
    method = methods[0] if methods else "get"

    path = (route.path or "").split("?")[0]
    segments = []
    for segment in path.split("/"):
        segment = _normalize(segment)
        if not segment or segment in ("api", "v1"):
            continue
        segments.append(segment)

    # Include a trailing verb-ish hint when the last segment is a path param:
    # /discover/wilayas/{id} -> get_discover_wilayas_id
    return "_".join([method, *segments])
