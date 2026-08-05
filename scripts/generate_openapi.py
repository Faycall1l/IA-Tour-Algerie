"""Dump the live FastAPI OpenAPI schema to docs/specs/openapi.json.

Runs offline — no server, no DB, no Docker. Imports the app object and asks
FastAPI to build the schema the same way the (debug-gated) /openapi.json
endpoint would.

This file is the single source of truth for client SDK generation and CI
contract checks. Regenerate it after any route/schema change:

    python scripts/generate_openapi.py

and commit the result. CI regenerates and fails on drift (see
.github/workflows/ci.yml, "contract" job).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "docs" / "specs" / "openapi.json"


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    # Importing app.main builds the FastAPI app (settings loaded from env or
    # defaults; no connections are opened at import time).
    from app.main import app

    schema = app.openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    operations = sum(len(paths) for paths in schema["paths"].values())
    schemas = len(schema.get("components", {}).get("schemas", {}))
    print(f"Wrote {OUT.relative_to(REPO_ROOT)}")
    print(f"  {len(schema['paths'])} paths, {operations} operations, {schemas} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
