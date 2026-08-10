"""Targeted stays/food enrichment for southern Algerian cities.

Data-v2 step 13. Real sources only:
  1. EN Wikivoyage destination pages — ``{{sleep}}``/``{{eat}}``/``{{drink}}``
     listing templates carry name/address/phone/coords/price.
  2. GeoNames DZ dump — ``HTL`` (hotel) → stays, ``RSTN`` (restaurant) → POIs
     for the target southern wilayas.

Known junk skipped: GeoNames record "Wyndham Lake Buena Vista Resort"
(geoname 9850629) sits at lon 0.0 — a copy/paste error, not a real Adrar hotel.

Usage:
    python scripts/data/enrich_southern_stays_food.py --dry-run
    python scripts/data/enrich_southern_stays_food.py --run
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import psycopg2

DATABASE_URL = (
    "postgresql://athar:athar_pass@localhost:5434/athar_db"
)
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
REPORTS_DIR = Path(__file__).resolve().parent / "reports"

# Wilayas targeted by data-v2 step 13.
TARGET_WILAYAS = (56, 11, 47, 49, 1, 30, 8)
TARGET_LABELS = {
    56: "Djanet",
    11: "Tamanrasset",
    47: "Ghardaïa (M'zab)",
    49: "Timimoun",
    1: "Adrar",
    30: "Ouargla",
    8: "Béchar",
}

USER_AGENT = (
    "ATHAR-Tourism/1.0 (data enrichment bot - bayrem.aymen@univ-usto.dz)"
)
API = "https://en.wikivoyage.org/w/api.php"

# EN Wikivoyage page title → target wilaya.
WIKIVOYAGE_PAGES: list[tuple[str, int]] = [
    ("M'zab", 47),
    ("Tamanrasset", 11),
    ("Djanet", 56),
    ("Timimoun", 49),
    ("Ouargla", 30),
    ("Bechar", 8),
]

# GeoNames feature code → (ATHAR category, subtype, property type, label)
GEONAMES_MAP: dict[str, tuple[str, str, str | None, str]] = {
    "HTL": ("stays", "", "hotel", "hôtel"),
    "RSTN": ("restaurant", "restaurant", None, "restaurant"),
}

STAY_TYPE_DEFAULT_PRICE: dict[str, float] = {
    "hotel": 6000.0,
    "hostel": 2500.0,
    "guesthouse": 4000.0,
    "apartment": 5000.0,
    "riad": 7000.0,
    "eco_lodge": 8000.0,
}

# known-bad GeoNames row (copy/paste error, lon 0.0)
SKIP_GEONAMES_IDS = {"9850629"}


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
    return min(centers, key=lambda w: haversine_km(lat, lon, *centers[w]))


def normalize_name(name: str) -> str:
    return "".join(c.lower() for c in name if c.isalnum())


def parse_float(v: object) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── EN Wikivoyage ───────────────────────────────────────────────────────────

def fetch_wikitext(page: str, retries: int = 4) -> str | None:
    url = API + "?" + urllib.parse.urlencode(
        {"action": "parse", "page": page, "prop": "wikitext", "format": "json"}
    )
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            data = json.loads(urllib.request.urlopen(req, timeout=40).read())
            return data["parse"]["wikitext"]["*"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(6 + 3 * attempt)
                continue
            return None
        except (KeyError, ValueError):
            return None
    return None


def split_template_params(body: str) -> list[str]:
    """Split a template body on top-level pipes (respecting nested braces)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


def parse_template(raw: str) -> dict[str, str]:
    """Parse a Wikivoyage listing template into a params dict."""
    raw = raw.strip()
    if raw.startswith("{{"):
        raw = raw[2:]
    if raw.endswith("}}"):
        raw = raw[:-2]
    parts = split_template_params(raw)
    params: dict[str, str] = {}
    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            key, _, value = part.partition("=")
            params[key.strip().lower()] = value.strip()
        else:
            params[f"_pos{len(params)}"] = part
    return params


def strip_curly(value: str) -> str:
    """Remove {{...}}/[[...]] markup from a value."""
    value = re.sub(r"\{\{[^{}]*\}\}", " ", value)
    value = re.sub(r"\[\[([^|\]]*\|)?([^\]]*)\]\]", r"\2", value)
    return re.sub(r"\s+", " ", value).strip()


def extract_price(price_raw: str) -> float | None:
    """Extract a nightly price in DZD from a Wikivoyage price field."""
    if not price_raw:
        return None
    m = re.search(r"DZD\|?\s*(\d[\d\s,]*)", price_raw)
    if m:
        try:
            return float(re.sub(r"[^\d]", "", m.group(1)))
        except ValueError:
            pass
    m = re.search(r"(\d{3,})", price_raw)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None


def page_geo(wikitext: str) -> tuple[float, float] | None:
    m = re.search(r"\{\{\s*geo\s*\|\s*([-\d.]+)\s*\|\s*([-\d.]+)", wikitext)
    if not m:
        return None
    lat, lon = parse_float(m.group(1)), parse_float(m.group(2))
    return (lat, lon) if lat is not None and lon is not None else None


STAY_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("auberge", "gite", "guesthouse", "maison d'hôte", "pension"), "guesthouse"),
    (("hostel", "auberge de jeunesse", "youth"), "hostel"),
    (("camp", "bivouac", "camping"), "eco_lodge"),
    (("riad", "dar "), "riad"),
    (("apart", "residence", "studio"), "apartment"),
]


def guess_property_type(name: str, content: str) -> str:
    text = f"{name} {content}".lower()
    for keywords, ptype in STAY_KEYWORDS:
        if any(k in text for k in keywords):
            return ptype
    return "hotel"


def find_templates(wt: str) -> list[tuple[str, str]]:
    """Scan wikitext for balanced {{...}} templates named listing/sleep/eat/drink."""
    results: list[tuple[str, str]] = []
    i, n = 0, len(wt)
    while True:
        j = wt.find("{{", i)
        if j == -1:
            break
        depth = 0
        k = j
        while k < n:
            if wt.startswith("{{", k):
                depth += 1
                k += 2
            elif wt.startswith("}}", k):
                depth -= 1
                k += 2
                if depth == 0:
                    break
            else:
                k += 1
        tpl = wt[j:k]
        m = re.match(r"\{\{\s*(listing|sleep|eat|drink)\b", tpl)
        if m:
            results.append((m.group(1).lower(), tpl))
        i = k
    return results


def extract_wikivoyage() -> list[dict]:
    """Extract sleep/eat/drink listings from the target EN Wikivoyage pages."""
    listings: list[dict] = []
    for page, wid in WIKIVOYAGE_PAGES:
        wt = fetch_wikitext(page)
        if wt is None:
            print(f"  [wv] {page}: fetch failed")
            continue
        fallback_geo = page_geo(wt)
        for kind, tpl in find_templates(wt):
            params = parse_template(tpl)
            if kind == "listing":
                kind = params.get("type", "").strip().lower()
                if kind not in ("sleep", "eat", "drink"):
                    continue
            name = strip_curly(params.get("name", ""))
            if not name:
                continue
            lat = parse_float(params.get("lat"))
            lon = parse_float(params.get("long", params.get("lon")))
            if lat is None or lon is None:
                if fallback_geo:
                    lat, lon = fallback_geo
                    coord_fallback = True
                else:
                    lat, lon, coord_fallback = None, None, False
            else:
                coord_fallback = False
            content = strip_curly(params.get("content", ""))
            price = extract_price(params.get("price", ""))
            listings.append(
                {
                    "source": "wikivoyage-en",
                    "source_id": f"{page}/{name}",
                    "page": page,
                    "kind": kind,
                    "name": name,
                    "wilaya_id": wid,
                    "address": strip_curly(params.get("address", "")),
                    "phone": strip_curly(params.get("phone", "")),
                    "url": strip_curly(params.get("url", "")),
                    "price_dzd": price,
                    "lat": lat,
                    "lon": lon,
                    "coord_fallback": coord_fallback,
                    "content": content,
                }
            )
        print(f"  [wv] {page}: {sum(1 for item in listings if item['page'] == page)} listings")
        time.sleep(0.5)
    return listings


# ── GeoNames ────────────────────────────────────────────────────────────────

def parse_geonames(centers: dict[int, tuple[float, float]]) -> list[dict]:
    records: list[dict] = []
    for line in GEONAMES_FILE.read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\n").split("\t")
        if len(p) < 15:
            continue
        try:
            lat, lon = float(p[4]), float(p[5])
        except ValueError:
            continue
        if p[7] not in GEONAMES_MAP or p[0] in SKIP_GEONAMES_IDS:
            continue
        wid = nearest_wilaya(lat, lon, centers)
        if wid not in TARGET_WILAYAS:
            continue
        records.append(
            {
                "source": "geonames",
                "source_id": p[0],
                "name": p[1],
                "feature": p[7],
                "wilaya_id": wid,
                "lat": lat,
                "lon": lon,
                "url": f"https://www.geonames.org/{p[0]}",
            }
        )
    return records


# ── Dedup ───────────────────────────────────────────────────────────────────

def fetch_db_stays(conn, wilayas: tuple[int, ...]) -> list[tuple[int, str, float, float]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT wilaya_id, name, latitude, longitude FROM stays
        WHERE wilaya_id = ANY(%s) AND name IS NOT NULL
        """,
        (list(wilayas),),
    )
    rows = cur.fetchall()
    cur.close()
    return [(r[0], normalize_name(r[1] or ""), r[2] or 0.0, r[3] or 0.0) for r in rows]


def fetch_db_pois(conn, wilayas: tuple[int, ...]) -> list[tuple[int, str, float, float]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT wilaya_id, name, latitude, longitude FROM pois
        WHERE wilaya_id = ANY(%s) AND name IS NOT NULL
        """,
        (list(wilayas),),
    )
    rows = cur.fetchall()
    cur.close()
    return [(r[0], normalize_name(r[1] or ""), r[2] or 0.0, r[3] or 0.0) for r in rows]


def is_duplicate(rec: dict, db_index: list[tuple[int, str, float, float]]) -> bool:
    name = normalize_name(rec["name"])
    for wid, db_name, lat, lon in db_index:
        if wid != rec["wilaya_id"]:
            continue
        if name and db_name and name == db_name:
            if rec["lat"] is not None and haversine_km(lat, lon, rec["lat"], rec["lon"]) < 5.0:
                return True
        elif (
            rec["lat"] is not None
            and abs(lat - rec["lat"]) < 0.02
            and abs(lon - rec["lon"]) < 0.02
        ):
            return True
    return False


# ── Insert ──────────────────────────────────────────────────────────────────

def build_stay(rec: dict, provider_id: str) -> dict:
    if rec["source"] == "geonames":
        ptype: str = GEONAMES_MAP[rec["feature"]][2] or "hotel"
        desc = f"{rec['name']}, hôtel (source GeoNames)."
        price = STAY_TYPE_DEFAULT_PRICE[ptype]
    else:
        ptype = guess_property_type(rec["name"], rec.get("content", ""))
        desc = rec.get("content") or ""
        if rec.get("url"):
            desc = (desc + "\n" if desc else "") + f"Site : {rec['url']}"
        price = rec.get("price_dzd") or STAY_TYPE_DEFAULT_PRICE[ptype]
        if rec.get("coord_fallback"):
            desc = (desc + "\n" if desc else "") + "Coordonnées : centre-ville (fallback)."
    return {
        "id": uuid.uuid4().hex,
        "provider_id": provider_id,
        "name": rec["name"][:200],
        "property_type": ptype,
        "description": (desc or None)[:2000] if desc else None,
        "wilaya_id": rec["wilaya_id"],
        "address": (rec.get("address") or None),
        "latitude": rec.get("lat"),
        "longitude": rec.get("lon"),
        "price_per_night_dzd": price,
        "is_active": True,
        "source": rec["source"],
        "source_id": rec["source_id"],
        "verified_at": "2026-08-10",
    }


def build_poi(rec: dict) -> dict:
    cat, sub = GEONAMES_MAP[rec["feature"]][:2]
    return {
        "id": uuid.uuid4().hex,
        "name": rec["name"][:200],
        "name_en": rec["name"][:200],
        "category": cat,
        "subtype": sub[:100],
        "wilaya_id": rec["wilaya_id"],
        "latitude": rec.get("lat"),
        "longitude": rec.get("lon"),
        "description": f"{rec['name']}, restaurant (source GeoNames).",
        "source": "geonames",
        "source_id": rec["source_id"],
        "website": rec["url"],
        "verified_at": "2026-08-10",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Southern stays/food enrichment from EN Wikivoyage + GeoNames"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report candidates without inserting"
    )
    parser.add_argument("--run", action="store_true", help="Insert candidates into DB")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run == args.run:
        print("Pass exactly one of --dry-run / --run")
        raise SystemExit(2)

    centers = load_centers()
    print("Fetching EN Wikivoyage listings...")
    wv = extract_wikivoyage()
    print("Parsing GeoNames hotels/restaurants...")
    gn = parse_geonames(centers)
    print(f"  [gn] {len(gn)} records in target wilayas")
    for r in gn:
        print(f"    {r['feature']} {r['wilaya_id']:02d} {r['name']}")

    conn = psycopg2.connect(**DB_CONFIG)
    stay_index = fetch_db_stays(conn, TARGET_WILAYAS)
    poi_index = fetch_db_pois(conn, TARGET_WILAYAS)
    print(f"Existing stays in target wilayas: {len(stay_index)}, POIs: {len(poi_index)}")

    stays: list[dict] = []
    food: list[dict] = []
    for rec in wv:
        if rec["kind"] == "sleep":
            if is_duplicate(rec, stay_index):
                print(f"  [dup stay] {rec['name']} ({rec['page']})")
                continue
            stays.append(rec)
        elif rec["kind"] in ("eat", "drink"):
            if is_duplicate(rec, poi_index):
                print(f"  [dup food] {rec['name']} ({rec['page']})")
                continue
            food.append(rec)

    for rec in gn:
        cat = GEONAMES_MAP[rec["feature"]][0]
        if cat == "stays":
            if is_duplicate(rec, stay_index):
                print(f"  [dup stay] {rec['name']} (geonames)")
                continue
            stays.append(rec)
        else:
            if is_duplicate(rec, poi_index):
                print(f"  [dup food] {rec['name']} (geonames)")
                continue
            food.append(rec)

    print(f"Candidates: {len(stays)} stays, {len(food)} food POIs")

    if args.dry_run:
        for s in stays:
            extra = s["lat"] if s["lat"] is not None else "NO-COORDS"
            print(f"  [stay] w{s['wilaya_id']:02d} {s['name'][:50]:50s} {extra}")
        for f in food:
            print(f"  [food] w{f['wilaya_id']:02d} {f['name'][:50]:50s} {f['feature']}")
        conn.close()
        return

    provider_id = conn.cursor()
    provider_id.execute("SELECT id FROM users WHERE phone = '+213500000001'")
    row = provider_id.fetchone()
    provider_id.close()
    if row:
        provider = row[0]
    else:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users LIMIT 1")
        provider = cur.fetchone()[0]
        cur.close()
    print(f"Provider: {provider}")

    cur = conn.cursor()
    inserted_stays = 0
    for rec in stays:
        s = build_stay(rec, provider)
        cur.execute(
            """
            INSERT INTO stays (
                id, provider_id, name, property_type, description, wilaya_id,
                address, latitude, longitude, price_per_night_dzd, is_active,
                source, source_id, verified_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                s["id"], s["provider_id"], s["name"], s["property_type"],
                s["description"], s["wilaya_id"], s["address"], s["latitude"],
                s["longitude"], s["price_per_night_dzd"], s["is_active"],
                s["source"], s["source_id"], s["verified_at"],
            ),
        )
        inserted_stays += 1
    conn.commit()

    inserted_food = 0
    for rec in food:
        if rec["source"] == "geonames":
            p = build_poi(rec)
            cur.execute(
                """
                INSERT INTO pois (
                    id, name, name_en, category, subtype, wilaya_id,
                    latitude, longitude, description, source, source_id,
                    website, verified_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    p["id"], p["name"], p["name_en"], p["category"], p["subtype"],
                    p["wilaya_id"], p["latitude"], p["longitude"], p["description"],
                    p["source"], p["source_id"], p["website"], p["verified_at"],
                ),
            )
        else:
            cat = "restaurant" if rec["kind"] == "eat" else "cafe"
            cur.execute(
                """
                INSERT INTO pois (
                    id, name, category, subtype, wilaya_id,
                    latitude, longitude, description, source, source_id,
                    phone, website, verified_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid.uuid4().hex, rec["name"][:200], cat, cat, rec["wilaya_id"],
                    rec["lat"], rec["lon"], rec.get("content") or None,
                    "wikivoyage-en", rec["source_id"], rec.get("phone") or None,
                    rec.get("url") or None, "2026-08-10",
                ),
            )
        inserted_food += 1
    conn.commit()
    cur.close()
    conn.close()
    print(f"DONE: inserted {inserted_stays} stays, {inserted_food} food POIs")


if __name__ == "__main__":
    main()
