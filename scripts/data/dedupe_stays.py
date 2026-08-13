"""Deduplicate near-identical stays (quality pass, Aug 2026).

The v2 merge seeded the same physical hotel twice when GeoAlgeria and OSM
carried it under the same name at slightly different coordinates (OSM node
vs way centroid). Rule: same wilaya + same normalized name + <150 m apart
= duplicate. Union-find merges chains (e.g. 3 campsite nodes → 1 stay).

The row with the most populated metadata fields is kept; missing fields are
merged in from the dropped rows. Deleted rows are backed up to a JSON report
so the pass is reversible. No FK references to ``stays`` exist, so deletes
are safe.

Usage:
    python scripts/data/dedupe_stays.py --dry-run
    python scripts/data/dedupe_stays.py --run
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

DIST_M = 150.0

# Field priority for choosing the survivor. Higher = more valuable.
FIELD_SCORE: dict[str, int] = {
    "description": 3,
    "address": 3,
    "amenities": 3,
    "photos": 2,
    "source_id": 1,
    "verified_at": 1,
}

MERGE_FIELDS = ("description", "address", "amenities", "photos", "verified_at")


def haversine_m(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    if a_lat is None or a_lng is None or b_lat is None or b_lng is None:
        return float("inf")
    r = 6_371_000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = math.radians(b_lat - a_lat)
    dl = math.radians(b_lng - a_lng)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(x))


def normalize_name(name: str | None) -> str:
    return " ".join((name or "").lower().split())


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def groups(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = {}
        for k in self.parent:
            out.setdefault(self.find(k), []).append(k)
        return out


def score_row(row: dict) -> int:
    score = 0
    for field, w in FIELD_SCORE.items():
        value = row.get(field)
        if value not in (None, "", [], ()):
            score += w
    if row.get("source") == "geoalgeria-tourisme":
        score += 1
    return score


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute(
        """SELECT id::text, wilaya_id, name, description, address, latitude,
                  longitude, amenities, photos, price_per_night_dzd, source,
                  source_id, verified_at
           FROM stays"""
    )
    cols = [d.name for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    print(f"stays loaded: {len(rows)}")

    by_key: dict[tuple[int, str], list[dict]] = {}
    for r in rows:
        by_key.setdefault((r["wilaya_id"], normalize_name(r["name"])), []).append(r)

    uf = UnionFind()
    pair_count = 0
    for key, group in by_key.items():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                d = haversine_m(a["latitude"], a["longitude"], b["latitude"], b["longitude"])
                if d < DIST_M:
                    uf.union(a["id"], b["id"])
                    pair_count += 1
    print(f"near-duplicate pairs (<{DIST_M:.0f}m): {pair_count}")

    groups = [g for g in uf.groups().values() if len(g) > 1]
    print(f"duplicate clusters: {len(groups)}")

    keep_ids: set[str] = set()
    delete_ids: list[str] = []
    backup: list[dict] = []
    merged_updates: list[tuple[str, dict]] = []

    for g in sorted(groups, key=len, reverse=True):
        members = [r for r in rows if r["id"] in g]
        keeper = max(members, key=score_row)
        keep_ids.add(keeper["id"])
        for r in members:
            if r["id"] == keeper["id"]:
                continue
            delete_ids.append(r["id"])
            backup.append(r)
            merges: dict[str, object] = {}
            for field in MERGE_FIELDS:
                if keeper.get(field) in (None, "", []) and r.get(field) not in (None, "", []):
                    merges[field] = r[field]
            if merges:
                merged_updates.append((keeper["id"], merges))

    print(f"to keep:  {len(keep_ids)}")
    print(f"to delete: {len(delete_ids)}")
    print(f"keepers receiving merged fields: {len(merged_updates)}")

    if args.dry_run or not args.run:
        for r in rows:
            if r["id"] in delete_ids:
                print(
                    f"  DEL w{r['wilaya_id']} {r['name'][:50]!r:54} "
                    f"{r['source']}/{r['source_id']} @ {r['latitude']},{r['longitude']}"
                )
        conn.close()
        return

    report = {
        "deduped_stays": len(delete_ids),
        "clusters": len(groups),
        "deleted": backup,
        "merged_updates": [
            {"id": rid, "fields": {k: v for k, v in m.items()}}
            for rid, m in merged_updates
        ],
    }
    out_path = REPORTS_DIR / "dedupe_stays.json"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print(f"backup written: {out_path}")

    cur.execute("BEGIN")
    for rid, merges in merged_updates:
        sets = ", ".join(f"{k} = %s" for k in merges)
        if sets:
            cur.execute(f"UPDATE stays SET {sets} WHERE id = %s", (*merges.values(), rid))
    cur.executemany("DELETE FROM stays WHERE id = %s", [(i,) for i in delete_ids])
    conn.commit()
    cur.execute("SELECT count(*) FROM stays")
    print(f"stays after dedup: {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
