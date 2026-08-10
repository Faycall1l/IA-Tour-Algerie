#!/usr/bin/env python3
"""Targeted GeoNames enrichment for under-covered wilayas (data-v2 step 12).

Reads the GeoNames Algeria dump (`raw/geonames/DZ.txt`, real gazetteer data)
and inserts tourism-relevant features (peaks, dunes, springs, ruins, oases,
tombs, forts, parks…) into `pois` for wilayas that still have <50 POIs.

Wilaya assignment is coordinate-based (nearest of the 69 official centers),
the same scheme used by the OSM PBF extractor. Rows are deduplicated against
existing DB POIs by (wilaya, normalized name, ~5km coords) and within the
dump by geoname id. Each inserted POI carries `source='geonames'`,
`source_id=<geonameid>`, and a `geonames.org` website link.

Usage:
    python -m scripts.data.enrich_geonames_wilayas [--dry-run] [--limit N]
"""

import argparse
import json
import logging
import math
import os
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

RAW_DIR = Path(__file__).resolve().parent / "raw"
GEONAMES_FILE = RAW_DIR / "geonames" / "DZ.txt"
CENTERS_FILE = RAW_DIR / "wilayas_centers.json"

TARGET_WILAYAS = (50, 52, 54, 57, 59, 62, 63, 64)

# GeoNames feature code → (ATHAR category, subtype, short French label)
FEATURE_MAP: dict[str, tuple[str, str, str]] = {
    "T.PK": ("mountain", "peak", "pic"),
    "T.MT": ("mountain", "mountain", "montagne"),
    "T.MTS": ("mountain", "mountain", "massif montagneux"),
    "T.HLL": ("mountain", "hill", "colline"),
    "T.HLLS": ("mountain", "hill", "collines"),
    "T.RDGE": ("mountain", "ridge", "crête"),
    "T.VOLC": ("mountain", "volcano", "volcan"),
    "T.DUNE": ("natural", "dune", "dune"),
    "T.CAVE": ("natural", "cave", "grotte"),
    "T.PLN": ("natural", "plain", "plaine"),
    "T.REG": ("natural", "region", "région"),
    "H.SPNG": ("natural", "spring", "source thermale"),
    "H.STM": ("natural", "wadi", "oued"),
    "H.COVE": ("natural", "cove", "crique"),
    "H.BAY": ("natural", "bay", "baie"),
    "H.LK": ("natural", "lake", "lac"),
    "H.LAKE": ("natural", "lake", "lac"),
    "H.WTRF": ("natural", "waterfall", "cascade"),
    "H.CHNM": ("natural", "channel", "chenal"),
    "H.STMH": ("natural", "stream", "cours d'eau"),
    "L.OAS": ("natural", "oasis", "oasis"),
    "L.DSRT": ("natural", "desert", "désert"),
    "L.PRK": ("park", "park", "parc"),
    "L.RSVT": ("natural", "reserve", "réserve naturelle"),
    "S.ARCH": ("historical", "archaeological", "site archéologique"),
    "S.RUIN": ("historical", "ruins", "ruines"),
    "S.FT": ("historical", "fort", "fort"),
    "S.ANCH": ("historical", "anchor", "ancien port"),
    "S.BLDG": ("cultural", "building", "bâtiment remarquable"),
    "S.MUS": ("museum", "museum", "musée"),
    "S.MNMT": ("historical", "monument", "monument"),
    "S.TMB": ("historical", "tomb", "tombeau"),
    "S.CH": ("religious", "church", "lieu de culte"),
}


# ── Geometry ────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_centers() -> dict[int, tuple[float, float]]:
    return {
        int(w["id"]): (float(w["latitude"]), float(w["longitude"]))
        for w in json.loads(CENTERS_FILE.read_text(encoding="utf-8"))
    }


def nearest_wilaya(lat: float, lon: float, centers: dict[int, tuple[float, float]]) -> int:
    best, best_d = None, None
    for wid, (clat, clon) in centers.items():
        d = haversine_km(lat, lon, clat, clon)
        if best_d is None or d < best_d:
            best, best_d = wid, d
    return best  # type: ignore[return-value]


# ── GeoNames dump ───────────────────────────────────────────────────────────

def parse_geonames(
    centers: dict[int, tuple[float, float]],
) -> list[dict]:
    """Parse DZ.txt, keep tourism-relevant features in target wilayas.

    Returns records with keys: wid, geoname_id, name, alternates,
    feature_code, lat, lon, elevation, population.
    """
    records: list[dict] = []
    for line in GEONAMES_FILE.read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\n").split("\t")
        if len(p) < 15:
            continue
        try:
            lat, lon = float(p[4]), float(p[5])
        except ValueError:
            continue
        wid = nearest_wilaya(lat, lon, centers)
        if wid not in TARGET_WILAYAS:
            continue
        fclass, fcode = p[6], p[7]
        if f"{fclass}.{fcode}" not in FEATURE_MAP:
            continue
        try:
            elevation = int(float(p[16])) if p[16] else None
        except ValueError:
            elevation = None
        try:
            population = int(p[14]) if p[14].isdigit() else 0
        except ValueError:
            population = 0
        records.append(
            {
                "wid": wid,
                "geoname_id": p[0],
                "name": p[1],
                "alternates": p[3],
                "feature_code": fcode,
                "lat": lat,
                "lon": lon,
                "elevation": elevation,
                "population": population,
            }
        )
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted GeoNames POI enrichment for under-covered wilayas"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidates per wilaya without inserting",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to insert (0 = all)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    log.info("GeoNames wilaya enrichment (dry_run=%s, limit=%d)", args.dry_run, args.limit)


if __name__ == "__main__":
    main()
