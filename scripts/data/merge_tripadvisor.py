#!/usr/bin/env python3
"""Merge & dedupe all TripAdvisor crawl JSONs into tripadvisor_v2.json + QA report.

Reads scripts/data/tripadvisor_*.json (city crawls), dedupes by d_id (newest
verified_at wins; geo_name list merged), and writes:
- scripts/data/tripadvisor_v2.json  (merged POIs)
- scripts/data/tripadvisor_qa.json  (QA report: counts, freshness, coverage)

Usage: python scripts/data/merge_tripadvisor.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "scripts" / "data"

SKIP_SOURCES = {"tripadvisor_pois.json", "tripadvisor_v2.json", "tripadvisor_qa.json"}


def main() -> int:
    merged: dict[str, dict] = {}
    sources: dict[str, int] = {}
    for f in sorted(DATA.glob("tripadvisor_*.json")):
        if f.name in SKIP_SOURCES:
            continue
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"  ! {f.name}: bad JSON ({exc})", file=sys.stderr)
            continue
        sources[f.name] = len(rows)
        for p in rows:
            d_id = str(p.get("d_id") or p.get("location_id") or "")
            if not d_id:
                continue
            prev = merged.get(d_id)
            if prev is None or (p.get("verified_at") or "") > (prev.get("verified_at") or ""):
                if prev is not None:
                    # keep geos seen across crawls
                    geos = {prev.get("geo_name"), p.get("geo_name")}
                    geos.discard(None)
                    p.setdefault("geo_names", sorted(geos))
                merged[d_id] = p

    out = list(merged.values())
    Data = DATA / "tripadvisor_v2.json"
    Data.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    qa = {
        "total_pois": len(out),
        "per_source": sources,
        "verified_at": dict(Counter(p.get("verified_at") or "none" for p in out)),
        "categories": dict(sorted(Counter(p.get("category") or "none" for p in out).items())),
        "with_photos": sum(1 for p in out if p.get("photo_url")),
        "with_description": sum(1 for p in out if p.get("description")),
        "with_rating": sum(1 for p in out if p.get("rating") is not None),
        "geo_names": dict(Counter(p.get("geo_name") or "none" for p in out)),
    }
    (DATA / "tripadvisor_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"merged {len(out)} unique POIs from {len(sources)} crawls")
    print(f"photos {qa['with_photos']} | desc {qa['with_description']} | rating {qa['with_rating']}")
    print(f"wrote {Data} + tripadvisor_qa.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())