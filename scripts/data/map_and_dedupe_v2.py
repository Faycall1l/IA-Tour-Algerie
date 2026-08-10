#!/usr/bin/env python3
"""Map staged v2 corpus to 69 wilayas and deduplicate within each wilaya.

Inputs:
    scripts/data/pois_v2.json
    scripts/data/stays_v2.json
    scripts/data/raw/wilayas_centers.json

Outputs:
    scripts/data/pois_v2_mapped.json
    scripts/data/stays_v2_mapped.json
    scripts/data/pois_v2_deduped.json
    scripts/data/stays_v2_deduped.json
    scripts/data/dedup_qa.json

Mapping strategy:
  1. Use the source's wilaya_code when present and valid (1-69).
  2. Fall back to the nearest wilaya center (haversine).

Deduplication strategy:
  - Exact duplicate keys: (source, source_id, wilaya_id) drop identical source ids.
  - Fuzzy duplicate key: (wilaya_id, normalized name, lat rounded 4, lng rounded 4).
  - Priority (highest wins): tripadvisor > geoalgeria-* > wikivoyage-fr > osm.
  - Merges photo_urls and refs from dropped duplicates into the keeper when safe.
"""

import json
import math
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "scripts" / "data"
RAW = DATA / "raw"

SOURCE_PRIORITY = {
    "tripadvisor": 0,
    "geoalgeria-culture": 1,
    "geoalgeria-tourisme": 1,
    "geoalgeria-asal": 1,
    "wikivoyage-fr": 2,
    "osm": 3,
}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", (s or "").lower()))


def hav(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_centers(path: Path) -> dict[int, tuple[float, float]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {int(r["id"]): (float(r["latitude"]), float(r["longitude"])) for r in rows}


def nearest_wilaya(lat: float, lng: float, centers: dict[int, tuple[float, float]]) -> int:
    best_id, best_d = None, None
    for wid, (clat, clon) in centers.items():
        d = hav(lat, lng, clat, clon)
        if best_d is None or d < best_d:
            best_id, best_d = wid, d
    return best_id


def resolve_wilaya_id(record: dict, centers: dict[int, tuple[float, float]]) -> tuple[int, str]:
    """Return (wilaya_id, method_used)."""
    code = record.get("wilaya_code")
    if code is not None:
        try:
            code_int = int(code)
            if 1 <= code_int <= 69:
                return code_int, "code"
        except (ValueError, TypeError):
            pass
    lat = record.get("lat")
    lng = record.get("lng")
    if lat is None or lng is None:
        return None, "missing"
    return nearest_wilaya(float(lat), float(lng), centers), "nearest"


def merge_photos(keeper: dict, drop: dict) -> list[str]:
    combined = list(keeper.get("photo_urls") or [])
    seen = set(combined)
    for url in drop.get("photo_urls") or []:
        if url and url not in seen:
            combined.append(url)
            seen.add(url)
    return combined


def merge_refs(keeper: dict, drop: dict) -> dict:
    krefs = dict(keeper.get("refs") or {})
    drefs = drop.get("refs") or {}
    for k, v in drefs.items():
        if k not in krefs:
            krefs[k] = v
    return krefs


def dedupe_records(records: list[dict], kind: str) -> tuple[list[dict], dict]:
    # 1. Exact duplicate by (source, source_id, wilaya_id)
    exact_seen: set[tuple[str, str, int]] = set()
    unique: list[dict] = []
    exact_dups = 0
    for r in records:
        wid = r.get("wilaya_id")
        if wid is None:
            continue
        key = (r.get("source") or "", str(r.get("source_id") or ""), wid)
        if key in exact_seen:
            exact_dups += 1
            continue
        exact_seen.add(key)
        unique.append(r)

    # 2. Fuzzy duplicate by (wilaya_id, norm(name), rounded coords)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in unique:
        name = r.get("name_fr") or r.get("name_en") or r.get("name_ar") or ""
        key = (
            r.get("wilaya_id"),
            norm(name),
            round(float(r.get("lat") or 0), 4),
            round(float(r.get("lng") or 0), 4),
        )
        groups[key].append(r)

    kept: list[dict] = []
    fuzzy_dups = 0
    for group in groups.values():
        if len(group) == 1:
            kept.append(group[0])
            continue
        def _num(value):
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        group_sorted = sorted(
            group,
            key=lambda r: (
                SOURCE_PRIORITY.get(r.get("source"), 99),
                -_num(r.get("rating")),
                -_num(r.get("num_reviews")),
                len(r.get("photo_urls") or []),
            ),
        )
        winner = group_sorted[0].copy()
        for drop in group_sorted[1:]:
            fuzzy_dups += 1
            winner["photo_urls"] = merge_photos(winner, drop)
            winner["refs"] = merge_refs(winner, drop)
            if not winner.get("description") and drop.get("description"):
                winner["description"] = drop["description"]
            if not winner.get("url") and drop.get("url"):
                winner["url"] = drop["url"]
            # Carry best rating/num_reviews if winner lacks them
            if not winner.get("rating") and drop.get("rating"):
                winner["rating"] = drop["rating"]
            if not winner.get("num_reviews") and drop.get("num_reviews"):
                winner["num_reviews"] = drop["num_reviews"]
        kept.append(winner)

    method_counts = Counter(r.get("_wilaya_method") for r in kept)
    source_counts = Counter(r.get("source") for r in kept)
    per_wilaya = Counter(r.get("wilaya_id") for r in kept)
    low_wilayas = [wid for wid, c in per_wilaya.items() if c < 50]

    qa = {
        "kind": kind,
        "input": len(records),
        "exact_duplicates_removed": exact_dups,
        "fuzzy_duplicates_removed": fuzzy_dups,
        "output": len(kept),
        "mapping_method": dict(method_counts),
        "by_source": dict(source_counts),
        "wilayas_covered": len(per_wilaya),
        "wilayas_under_50": sorted(low_wilayas),
        "per_wilaya": dict(sorted(per_wilaya.items())),
    }
    return kept, qa


def main() -> int:
    centers = load_centers(RAW / "wilayas_centers.json")

    def map_items(path: Path, kind: str) -> list[dict]:
        rows = json.loads(path.read_text(encoding="utf-8"))
        mapped = []
        missing_coords = 0
        fallback_to_nearest = 0
        for r in rows:
            wid, method = resolve_wilaya_id(r, centers)
            if wid is None:
                missing_coords += 1
                continue
            r["wilaya_id"] = wid
            r["_wilaya_method"] = method
            if method == "nearest":
                fallback_to_nearest += 1
            mapped.append(r)
        print(f"{kind}: mapped {len(mapped)}, {fallback_to_nearest} fallback-to-nearest, {missing_coords} missing coords")
        return mapped

    pois_mapped = map_items(DATA / "pois_v2.json", "pois")
    stays_mapped = map_items(DATA / "stays_v2.json", "stays")

    (DATA / "pois_v2_mapped.json").write_text(
        json.dumps(pois_mapped, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "stays_v2_mapped.json").write_text(
        json.dumps(stays_mapped, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    pois_deduped, poi_qa = dedupe_records(pois_mapped, "pois")
    stays_deduped, stay_qa = dedupe_records(stays_mapped, "stays")

    (DATA / "pois_v2_deduped.json").write_text(
        json.dumps(pois_deduped, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "stays_v2_deduped.json").write_text(
        json.dumps(stays_deduped, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    qa = {
        "pois": poi_qa,
        "stays": stay_qa,
        "generated_at": date.today().isoformat(),
    }
    (DATA / "dedup_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
