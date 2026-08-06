"""OpenAPI contract tests (S5): deterministic path-based operation ids."""

import re

from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def _operations():
    schema = app.openapi()
    ops = []
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            ops.append((method, path, op))
    return ops


def test_every_operation_has_unique_id():
    ids = [op["operationId"] for _, _, op in _operations()]
    assert len(ids) == len(set(ids)), "operationId must be unique"


def test_operation_ids_follow_scheme():
    for _, _, op in _operations():
        assert "operationId" in op
        assert op["operationId"] != "", "operationId must be non-empty"
        assert op["operationId"] == op["operationId"].lower()


def test_operation_ids_are_path_based():
    """Operation ids must derive from method+path, not function names."""
    for method, path, op in _operations():
        assert op["operationId"].startswith(f"{method.lower()}_"), f"{method} {path}"
        # id must not leak the api/v1 prefix or path braces
        assert "api_v1" not in op["operationId"]
        assert "{" not in op["operationId"]
        # method must appear exactly once at position 0
        stem = op["operationId"].split("_", 1)[1]
        assert stem, f"{method} {path}"
        # every literal path segment appears (normalized) within the id as a
        # whole token or underscore-joined piece (param names keep internal
        # underscores, e.g. user_id -> ..._user_id...)
        id_text = op["operationId"].split("_", 1)[1]
        for seg in path.split("/"):
            seg = seg.strip("{}").lower()
            if not seg or seg in ("api", "v1"):
                continue
            # mirror the generator's normalization (non-alphanum -> _)
            normalized = re.sub(r"[^a-z0-9]+", "_", seg).strip("_")
            assert f"_{normalized}_" in f"_{id_text}_", (
                f"{seg} -> {normalized} missing from operationId "
                f"{op['operationId']} ({method} {path})"
            )


def test_known_ids_stable():
    """Spot-check the ids generated clients depend on."""
    ids = {op["operationId"] for _, _, op in _operations()}
    assert "get_discover_wilayas" in ids
    assert "get_discover_wilayas_wilaya_id" in ids
    assert "post_agent_chat" in ids
    assert "post_auth_verify_otp" in ids
    assert "get_pois_search" in ids
    assert "get_pois_poi_id" in ids
    assert "get_health" in ids
