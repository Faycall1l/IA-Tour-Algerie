#!/usr/bin/env python3
"""Geocode PagesMaghreb artisan street addresses.

Geocoder: Photon (photon.komoot.io) — the OSM-based free geocoding API
(Nominatim's public instance is unreachable from this host; Photon works and
honors a lightweight usage policy ~1 req/s for our scale).

Two-stage strategy:
  1. Full query: "street, commune, wilaya, Algeria" with a wilaya-centroid
     lat/lon bias so street resolution stays in the right region.
  2. Fallback: commune-only query (same bias) → commune centroid. Every
     record keeps its verified street/commune text from the source page even
     when Photon can't resolve the exact building.

Checkpointed JSONL: re-runs only geocode what's missing. Output records get
`latitude`, `longitude`, `geocode_display`, `geocode_stage` (street|commune|none).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent.parent

PM_JSON = REPO / "app" / "data" / "pagesmaghreb_artisans.json"
CKPT = REPO / "scripts" / "data" / "reports" / "pm_geocode.jsonl"
PHOTON = "https://photon.komoot.io/api/"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ATHAR-data-collector/1.0"
)

WILAYA_CENTERS = {
    1: (27.87, -0.29), 2: (36.15, 1.33), 3: (33.80, 2.88), 4: (35.87, 7.11),
    5: (35.55, 6.17), 6: (36.75, 5.06), 7: (34.85, 5.73), 8: (31.62, -2.22),
    9: (36.47, 2.82), 10: (36.37, 3.89), 11: (22.79, 5.53), 12: (35.40, 8.12),
    13: (34.88, -1.32), 14: (35.37, 1.32), 15: (36.72, 4.05), 16: (36.75, 3.06),
    17: (34.67, 3.26), 18: (36.82, 5.77), 19: (36.19, 5.41), 20: (34.84, 0.15),
    21: (36.87, 6.91), 22: (35.20, -0.63), 23: (36.90, 7.77), 24: (36.46, 7.43),
    25: (36.37, 6.61), 26: (36.27, 2.75), 27: (35.93, 0.09), 28: (35.71, 4.54),
    29: (35.40, 0.14), 30: (31.95, 5.33), 31: (35.70, -0.65), 32: (33.68, 1.02),
    33: (26.57, 8.48), 34: (36.07, 4.76), 35: (36.77, 3.48), 36: (36.77, 8.31),
    37: (27.67, -8.15), 38: (35.60, 1.81), 39: (33.37, 6.86), 40: (35.43, 7.14),
    41: (36.28, 7.95), 42: (36.59, 2.45), 43: (36.45, 6.27), 44: (36.26, 2.20),
    45: (33.27, -0.31), 46: (35.30, -1.14), 47: (32.49, 3.67), 48: (35.75, 0.63),
    49: (29.28, 0.24), 50: (21.33, 0.95), 51: (34.44, 5.06), 52: (30.08, -2.17),
    53: (27.22, 2.47), 54: (27.05, 5.47), 55: (33.11, 6.06), 56: (24.55, 9.48),
    57: (33.95, 6.15), 58: (30.57, 2.88), 59: (34.11, 2.10), 60: (35.38, 5.37),
    61: (35.24, 5.71), 62: (34.73, 8.05), 63: (32.50, -0.83), 64: (35.87, 2.32),
    65: (35.55, 3.25), 66: (34.18, 3.53), 67: (35.71, 4.54), 68: (35.21, 4.54),
    69: (32.90, 0.58),
}


class GeoCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._by_key: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    self._by_key[rec["query"]] = rec
                except Exception:
                    pass

    def get(self, query: str) -> dict | None:
        return self._by_key.get(query)

    def save(self, rec: dict) -> None:
        self._by_key[rec["query"]] = rec
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def photon_search(
    session: requests.Session, q: str, wilaya_id: int, limit: int = 3
) -> list[dict]:
    params = {"q": q, "limit": limit, "countrycode": "dz", "lang": "fr"}
    center = WILAYA_CENTERS.get(wilaya_id)
    if center:
        params["lat"] = center[0]
        params["lon"] = center[1]
    r = session.get(PHOTON, params=params, timeout=20)
    r.raise_for_status()
    out = []
    for f in r.json().get("features", []):
        lon, lat = f["geometry"]["coordinates"]
        p = f["properties"]
        out.append({
            "lat": float(lat),
            "lon": float(lon),
            "display_name": p.get("name") or "",
            "osm_type": p.get("osm_type"),
            "osm_id": p.get("osm_id"),
            "ftype": p.get("type"),
            "city": p.get("city") or p.get("district") or p.get("state") or "",
        })
    return out


def best_match(results: list[dict], city: str) -> dict | None:
    """Prefer a street-level hit whose city is plausibly ours."""
    if not results:
        return None
    # Street candidates first
    streets = [
        r for r in results if r["ftype"] in ("street", "house", "building", "place", "locality")
    ]
    pool = streets or results
    city_low = city.lower()
    for r in pool:
        if city_low and city_low in r["city"].lower():
            return r
    return pool[0]


def geocode_one(
    session: requests.Session, rec: dict, wilaya_id: int
) -> dict:
    addr = rec["addresses"][0]
    city = addr.get("city") or ""
    street = addr.get("street") or ""
    wilaya_name = addr.get("wilaya") or ""

    full_q = ", ".join(p for p in [street, city, wilaya_name, "Algérie"] if p)
    res = photon_search(session, full_q, wilaya_id)
    hit = best_match(res, city)
    stage = "street" if hit and hit["ftype"] in ("street", "house", "building") else None

    if not hit:
        city_q = ", ".join(p for p in [city, wilaya_name, "Algérie"] if p)
        res = photon_search(session, city_q, wilaya_id)
        hit = best_match(res, city)
        stage = "commune"

    if not hit:
        return {"lat": None, "lon": None, "display": "", "stage": "none"}
    return {
        "lat": hit["lat"],
        "lon": hit["lon"],
        "display": hit.get("display_name", ""),
        "stage": stage or "street",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-checkpoint", action="store_true")
    args = ap.parse_args()

    if args.reset_checkpoint:
        CKPT.unlink(missing_ok=True)

    with open(PM_JSON) as fh:
        data = json.load(fh)
    cache = GeoCache(CKPT)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})

    to_do = [r for r in data if not (r.get("latitude") and r.get("longitude"))]
    print(f"[*] {len(data)} records, {len(to_do)} need geocoding", flush=True)

    ok_street = ok_commune = fail = cached = 0
    for i, rec in enumerate(to_do):
        wilaya_id = int(rec["addresses"][0]["wilaya_code"])
        street = (rec["addresses"][0].get("street") or "").strip()
        city = (rec["addresses"][0].get("city") or "").strip()
        key = f"{street}|{city}|{wilaya_id}"

        hit = cache.get(key)
        if hit:
            cached += 1
        else:
            try:
                hit = geocode_one(session, rec, wilaya_id)
                cache.save({"query": key, **hit})
                time.sleep(1.0)
            except Exception as exc:  # noqa: BLE001
                print(f"  [err] {key!r}: {exc}", flush=True)
                fail += 1
                time.sleep(3.0)
                continue

        if hit.get("lat") is not None:
            rec["latitude"] = hit["lat"]
            rec["longitude"] = hit["lon"]
            rec["geocode_display"] = hit.get("display")
            rec["geocode_stage"] = hit.get("stage")
            if hit.get("stage") == "street":
                ok_street += 1
            else:
                ok_commune += 1
        else:
            rec["geocode_stage"] = "none"
            fail += 1

        if (i + 1) % 20 == 0:
            print(
                f"  progress {i + 1}/{len(to_do)} "
                f"(street={ok_street} commune={ok_commune} none={fail} cache={cached})",
                flush=True,
            )

    with open(PM_JSON, "w") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    no_geo = [r["name"] for r in data if not (r.get("latitude") and r.get("longitude"))]
    print(f"[=] street={ok_street} commune={ok_commune} none={fail} cache={cached}")
    print(f"    {len(no_geo)} records still without coordinates:")
    for n in no_geo[:12]:
        print(f"      - {n}")
    print(f"    -> {PM_JSON}")


if __name__ == "__main__":
    sys.exit(main())
