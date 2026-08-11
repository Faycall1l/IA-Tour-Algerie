"""Diversified photo enrichment for the data-v2 POI corpus.

Sources (all keyless, real, CC-safe, hosted on Wikimedia/MinIO):
  Pass 1 — Wikidata P18 via name match:
      One big SPARQL call (all Algerian items with a P18 image + labels +
      sitelinks), then in-memory exact/containment name matching against every
      named POI that still has no photo. High precision, ~1 network round trip.
  Pass 2 — Commons API text search:
      For southern + featured named POIs, text-search Wikimedia Commons
      ("<name> <wilaya> Algeria"), take the top relevant image ≥800px.
  Pass 3 — Openverse API (CC aggregator):
      Fallback for southern POIs still missing after Pass 1+2; filters to
      CC0/CC-BY/CC-BY-SA and image size ≥800px.

Every accepted image is downloaded and uploaded to MinIO via the shared
`migrate_photos_minio.download_and_upload` helper (URL-hash dedup), and the
POI row is updated with photo_url/photo_urls/photo_source/photo_attribution.

Usage:
    python scripts/data/enrich_photos_diverse_v2.py --dry-run --passes 1
    python scripts/data/enrich_photos_diverse_v2.py --run --passes 1
    python scripts/data/enrich_photos_diverse_v2.py --run --passes 2 --limit 200
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
from pathlib import Path

import httpx
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

SPARQL_URL = "https://query.wikidata.org/sparql"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
USER_AGENT = "ATHAR-Tourism/1.0 (photo enrichment; faycal@athar.dz)"
MIN_WIDTH = 800
MIN_HEIGHT = 600
LANG_PREFIXES = ("/fr/", "/en/", "/ar/")
CC_LICENSES = {"cc0", "by", "by-sa"}

INDEX_CACHE = Path(__file__).resolve().parent / "raw" / "wikidata_photo_index.json"

SOUTHERN_WILAYAS = {1, 8, 11, 30, 33, 37, 47, 49, 50, 52, 53, 56, 58}

# ── text utils ───────────────────────────────────────────────────────────────

def normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_name(name: str) -> str:
    return name.split("(")[0].strip()


def lang_of_wiki_article(article: str) -> str:
    for prefix in LANG_PREFIXES:
        if prefix in article:
            return prefix.strip("/")
    return ""


def wiki_title(article: str) -> str:
    return urllib.parse.unquote(article.rstrip("/").rsplit("/", 1)[-1])


def parse_point(coords: str) -> tuple[float, float] | None:
    m = re.search(r"Point\(([-\d.]+)\s+([-\d.]+)\)", coords)
    if not m:
        return None
    lat, lon = float(m.group(2)), float(m.group(1))
    return (lat, lon)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def token_contained(short: str, long: str) -> bool:
    """True when `short` appears in `long` as a complete whitespace token run."""
    if len(short) < 5 or len(long) <= len(short):
        return False
    return bool(re.search(r"(?<![a-z0-9])" + re.escape(short) + r"(?![a-z0-9])", long))


# ── DB ───────────────────────────────────────────────────────────────────────

TARGET_SQL = """
    SELECT p.id, p.name, p.wilaya_id, w.name_fr, p.is_featured, p.latitude, p.longitude
    FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
    WHERE (p.photo_url IS NULL OR p.photo_url = '')
      AND (p.photo_urls IS NULL OR array_length(p.photo_urls, 1) IS NULL OR p.photo_urls[1] = '')
      AND p.name NOT LIKE %s
      AND p.name NOT ILIKE %s
      AND LENGTH(TRIM(p.name)) > 3
    ORDER BY p.wilaya_id = ANY(%s) DESC, p.is_featured DESC, p.name
"""


def fetch_targets(conn, limit: int = 0) -> list[dict]:
    cur = conn.cursor()
    params: list = ["%non nommé%", "unknown%", list(SOUTHERN_WILAYAS)]
    sql = TARGET_SQL
    if limit > 0:
        sql += " LIMIT %s"
        params.append(limit)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "id": str(r[0]),
            "name": r[1],
            "wilaya_id": r[2],
            "wilaya": r[3],
            "featured": r[4],
            "lat": r[5],
            "lon": r[6],
        }
        for r in rows
    ]


def update_poi_photo(conn, poi_id: str, minio_url: str, source: str, attribution: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE pois SET photo_url = %s, photo_urls = ARRAY[%s]::text[],
            photo_source = %s, photo_attribution = %s
        WHERE id = %s AND (photo_url IS NULL OR photo_url = '')
        """,
        (minio_url, minio_url, source, attribution, poi_id),
    )
    cur.close()


# ── Pass 1: Wikidata SPARQL ─────────────────────────────────────────────────

SPARQL_QUERY = """
SELECT ?item ?itemLabel ?itemAltLabel ?image ?article ?coords WHERE {
  ?item wdt:P17 wd:Q262 .
  ?item wdt:P18 ?image .
  OPTIONAL { ?item rdfs:label ?itemLabel . FILTER(LANG(?itemLabel) = "fr") }
  OPTIONAL { ?item skos:altLabel ?itemAltLabel . FILTER(LANG(?itemAltLabel) = "fr") }
  OPTIONAL { ?item wdt:P625 ?coords }
  OPTIONAL {
    ?article schema:about ?item .
    ?article schema:isPartOf [wikibase:wikiGroup "wikipedia"] .
  }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "fr,en,ar" }
}
LIMIT 120000
"""


def fetch_wikidata_index(refresh: bool = False) -> tuple[dict[str, str], dict[str, dict]]:
    """Return (norm_label → image_url, qid → info{image,label}) for Algerian items.

    Cached to `raw/wikidata_photo_index.json` so re-runs skip the slow SPARQL.
    """
    if not refresh and INDEX_CACHE.exists():
        raw = json.loads(INDEX_CACHE.read_text(encoding="utf-8"))
        qid_info = {
            qid: {
                "image": info["image"],
                "labels": set(info["labels"]),
                "sitelinks": set(info["sitelinks"]),
                "coords": tuple(info["coords"]) if info["coords"] else None,
            }
            for qid, info in raw["qid_info"].items()
        }
        log.info("  loaded Wikidata index from cache (%d items)", len(qid_info))
        return raw["label_map"], qid_info

    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    last_err: Exception | None = None
    bindings: list[dict] = []
    for attempt in range(4):
        try:
            with httpx.Client(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
                resp = client.post(
                    SPARQL_URL,
                    data={"query": SPARQL_QUERY},
                    headers=headers,
                )
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = min(90, 10 * (attempt + 1))
                log.warning("SPARQL HTTP %d, retrying in %ds", resp.status_code, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            bindings = resp.json()["results"]["bindings"]
            break
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = min(90, 10 * (attempt + 1))
            log.warning("SPARQL error, retrying in %ds: %s", wait, exc)
            time.sleep(wait)
    if not bindings:
        raise RuntimeError(f"SPARQL failed after 4 attempts: {last_err}")

    qid_info: dict[str, dict] = {}
    for b in bindings:
        qid = b["item"]["value"].rsplit("/", 1)[-1]
        image = b["image"]["value"]
        info = qid_info.setdefault(
            qid, {"image": image, "labels": set(), "sitelinks": set(), "coords": None}
        )
        for key in ("itemLabel", "itemAltLabel"):
            if b.get(key):
                for lbl in b[key]["value"].split(","):
                    lbl = lbl.strip()
                    if len(lbl) > 2:
                        info["labels"].add(lbl)
        if b.get("article"):
            lang = lang_of_wiki_article(b["article"]["value"])
            if lang:
                info["sitelinks"].add(wiki_title(b["article"]["value"]))
        if b.get("coords"):
            pt = parse_point(b["coords"]["value"])
            if pt:
                info["coords"] = pt

    label_map: dict[str, str] = {}
    for qid, info in qid_info.items():
        for lbl in list(info["labels"]) + list(info["sitelinks"]):
            n = normalize(lbl)
            if len(n) > 2 and n not in label_map:
                label_map[n] = qid

    INDEX_CACHE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_CACHE.write_text(
        json.dumps(
            {
                "label_map": label_map,
                "qid_info": {
                    qid: {
                        "image": info["image"],
                        "labels": sorted(info["labels"]),
                        "sitelinks": sorted(info["sitelinks"]),
                        "coords": list(info["coords"]) if info["coords"] else None,
                    }
                    for qid, info in qid_info.items()
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("  cached Wikidata index (%d items)", len(qid_info))
    return label_map, qid_info


def build_token_index(label_map: dict[str, str]) -> dict[str, set[str]]:
    """Inverted index: token (≥5 chars) → label keys containing it."""
    idx: dict[str, set[str]] = {}
    for key in label_map:
        for tok in set(key.split()):
            if len(tok) >= 5:
                idx.setdefault(tok, set()).add(key)
    return idx


def pass1_match(
    targets: list[dict],
    label_map: dict[str, str],
    qid_info: dict[str, dict],
    token_idx: dict[str, set[str]],
) -> list[dict]:
    """Exact + conservative containment name match → list of photo candidates."""
    candidates: list[dict] = []
    for t in targets:
        key = normalize(t["name"])
        if not key:
            continue
        qid = label_map.get(key)
        hit_label = key
        exact = qid is not None
        if qid is None:
            # containment: candidate labels must share a ≥5-char token, item
            # must be geolocated ≤100km from the POI, and the POI name must
            # carry ≥2 tokens (single-word generic names are too risky).
            poi_coords = None
            if t.get("lat") is not None and t.get("lon") is not None:
                poi_coords = (t["lat"], t["lon"])
            if not poi_coords or len(key.split()) < 2:
                continue
            cand_keys: set[str] = set()
            for tok in key.split():
                if len(tok) >= 5:
                    cand_keys |= token_idx.get(tok, set())
            for wd_key in cand_keys:
                if not (token_contained(key, wd_key) or token_contained(wd_key, key)):
                    continue
                item_coords = qid_info[label_map[wd_key]].get("coords")
                if not item_coords:
                    continue
                if haversine_km(*poi_coords, *item_coords) <= 100.0:
                    qid = label_map[wd_key]
                    hit_label = wd_key
                    break
        if not qid:
            continue
        info = qid_info[qid]
        candidates.append(
            {
                "poi": t,
                "image_url": info["image"],
                "source": "wikidata-p18",
                "attribution": (
                    f"Wikidata {qid} ({hit_label})"
                    + (" exact" if exact else " containment")
                    + f", image {info['image'].rsplit('/', 1)[-1]}"
                ),
            }
        )
    return candidates


# ── Pass 2: Commons API text search ─────────────────────────────────────────

def commons_search(http: httpx.Client, name: str, wilaya: str) -> str | None:
    queries = [
        f'"{name}" {wilaya} Algeria',
        f"{name} {wilaya} Algeria",
        f"{name} Algeria",
        name,
    ]
    for q in queries:
        resp = http.get(
            COMMONS_API,
            params={
                "action": "query",
                "list": "search",
                "srsearch": q,
                "srnamespace": 6,
                "srlimit": 3,
                "format": "json",
            },
        )
        if resp.status_code == 429:
            time.sleep(5)
            continue
        if resp.status_code != 200:
            continue
        hits = resp.json().get("query", {}).get("search", [])
        if not hits:
            continue
        title = hits[0]["title"]
        info = http.get(
            COMMONS_API,
            params={
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url|size",
                "format": "json",
            },
        ).json()
        pages = info.get("query", {}).get("pages", {})
        for page in pages.values():
            img = (page.get("imageinfo") or [{}])[0]
            w, h, url = img.get("width", 0), img.get("height", 0), img.get("url", "")
            if url and (w >= MIN_WIDTH or h >= MIN_HEIGHT):
                return url
    return None


def pass2_candidates(
    targets: list[dict], limit: int, http: httpx.Client
) -> list[dict]:
    candidates: list[dict] = []
    for i, t in enumerate(targets[:limit]):
        if t["wilaya_id"] not in SOUTHERN_WILAYAS and not t["featured"]:
            continue
        name = clean_name(t["name"])
        if len(name) < 5:
            continue
        url = commons_search(http, name, t["wilaya"])
        time.sleep(0.6)
        if url:
            candidates.append(
                {
                    "poi": t,
                    "image_url": url,
                    "source": "commons-search",
                    "attribution": f"Wikimedia Commons search for '{name}' ({t['wilaya']})",
                }
            )
        if (i + 1) % 50 == 0:
            log.info("  commons search: %d/%d processed, %d found", i + 1, limit, len(candidates))
    return candidates


# ── Pass 3: Openverse supplement ─────────────────────────────────────────────

def openverse_search(http: httpx.Client, name: str, wilaya: str) -> tuple[str | None, str]:
    resp = http.get(
        OPENVERSE_API,
        params={
            "q": f"{name} {wilaya} Algeria",
            "page_size": 5,
            "license": ",".join(CC_LICENSES),
            "aspect_ratio": "wide,standard,tall",
        },
    )
    if resp.status_code == 429:
        time.sleep(10)
        return None, ""
    if resp.status_code != 200:
        return None, ""
    for r in resp.json().get("results", []):
        w, h = r.get("width") or 0, r.get("height") or 0
        if w >= MIN_WIDTH or h >= MIN_HEIGHT:
            license_ = r.get("license") or ""
            return r.get("url"), license_
    return None, ""


def pass3_candidates(
    targets: list[dict], limit: int, http: httpx.Client
) -> list[dict]:
    candidates: list[dict] = []
    for i, t in enumerate(targets[:limit]):
        if t["wilaya_id"] not in SOUTHERN_WILAYAS:
            continue
        name = clean_name(t["name"])
        if len(name) < 5:
            continue
        url, license_ = openverse_search(http, name, t["wilaya"])
        time.sleep(0.4)
        if url:
            candidates.append(
                {
                    "poi": t,
                    "image_url": url,
                    "source": "openverse",
                    "attribution": f"Openverse CC ({license_}) search for '{name}' ({t['wilaya']})",
                }
            )
        if (i + 1) % 50 == 0:
            log.info("  openverse: %d/%d processed, %d found", i + 1, limit, len(candidates))
    return candidates


# ── ingestion ────────────────────────────────────────────────────────────────

def normalize_wikimedia_url(url: str) -> str | None:
    from scripts.data.enrich_photos_wikidata_p18 import to_direct_upload_url

    return to_direct_upload_url(url)


def ingest(
    conn,
    candidates: list[dict],
    dry_run: bool,
    commit_every: int = 25,
) -> tuple[int, int]:
    if not candidates:
        return 0, 0
    if dry_run:
        for c in candidates[:10]:
            log.info("[DRY] %s -> %s", c["poi"]["name"], c["image_url"][:70])
        return len(candidates), 0

    from scripts.data.migrate_photos_minio import download_and_upload, get_minio_client

    minio_client = get_minio_client()
    timeout = httpx.Timeout(60.0, connect=20.0, read=60.0)
    updated = 0
    failed = 0
    with httpx.Client(follow_redirects=True, timeout=timeout) as http:
        for c in candidates:
            url = c["image_url"]
            if c["source"] == "wikidata-p18" and "/wiki/Special:FilePath/" in url:
                # Request a 640px thumbnail via the canonical redirect endpoint;
                # the /thumb/ path 400s and full-size originals are slow to pull.
                direct = url + ("&" if "?" in url else "?") + "width=640"
            else:
                direct = normalize_wikimedia_url(url) or url
            try:
                minio_url, _ext = download_and_upload(minio_client, http, direct)
            except Exception as exc:  # noqa: BLE001
                log.warning("download/upload error %s: %s", c["poi"]["name"], exc)
                minio_url = None
            if not minio_url:
                failed += 1
                log.warning("No image for %s [%s]", c["poi"]["name"], direct[:70])
                continue
            update_poi_photo(
                conn, c["poi"]["id"], minio_url, c["source"], c["attribution"]
            )
            updated += 1
            if updated % commit_every == 0:
                conn.commit()
                log.info("  progress: %d enriched, %d failed", updated, failed)
    conn.commit()
    return updated, failed


# ── main ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diversified photo enrichment (Wikidata P18 + Commons + Openverse)"
    )
    parser.add_argument(
        "--passes", default="1", help="Comma-separated passes to run: 1,2,3 (default 1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report matches without downloading"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Max POIs to consider (0 = all named no-photo)"
    )
    parser.add_argument(
        "--pass-limit", type=int, default=0, help="Per-pass cap for API-search passes (0 = all)"
    )
    parser.add_argument(
        "--commit-every", type=int, default=25, help="DB commit batch size"
    )
    parser.add_argument(
        "--refresh-index",
        action="store_true",
        help="Re-fetch the Wikidata index from SPARQL instead of using the cache",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    passes = {int(p) for p in args.passes.split(",") if p.strip() in ("1", "2", "3")}
    log.info("diverse photos (passes=%s, dry_run=%s, limit=%d)",
             sorted(passes), args.dry_run, args.limit)

    conn = psycopg2.connect(**DB_CONFIG)
    targets = fetch_targets(conn, args.limit)
    log.info("Named no-photo POIs: %d", len(targets))
    if not targets:
        conn.close()
        return

    all_candidates: list[dict] = []
    if 1 in passes:
        log.info("Pass 1: Wikidata SPARQL name match")
        label_map, qid_info = fetch_wikidata_index(refresh=args.refresh_index)
        token_idx = build_token_index(label_map)
        log.info("  Wikidata label map: %d entries, %d items", len(label_map), len(qid_info))
        cand = pass1_match(targets, label_map, qid_info, token_idx)
        log.info("  Pass 1 matched %d POIs", len(cand))
        all_candidates.extend(cand)

    if 2 in passes or 3 in passes:
        still_missing = {t["id"] for t in targets}
        for c in all_candidates:
            still_missing.discard(c["poi"]["id"])
        remaining = [t for t in targets if t["id"] in still_missing]

    with httpx.Client(follow_redirects=True, timeout=httpx.Timeout(45.0, connect=20.0)) as http:
        if 2 in passes:
            log.info("Pass 2: Commons API text search (south + featured)")
            cap = args.pass_limit or len(remaining)
            cand = pass2_candidates(remaining, cap, http)
            log.info("  Pass 2 matched %d POIs", len(cand))
            all_candidates.extend(cand)

        if 3 in passes:
            still_missing = {t["id"] for t in targets}
            for c in all_candidates:
                still_missing.discard(c["poi"]["id"])
            remaining = [t for t in targets if t["id"] in still_missing]
            log.info("Pass 3: Openverse supplement (south)")
            cap = args.pass_limit or len(remaining)
            cand = pass3_candidates(remaining, cap, http)
            log.info("  Pass 3 matched %d POIs", len(cand))
            all_candidates.extend(cand)

    log.info("Total photo candidates: %d", len(all_candidates))
    updated, failed = ingest(conn, all_candidates, args.dry_run, args.commit_every)
    conn.close()
    log.info("DONE: %s %d photos (%d failures)", "would enrich" if args.dry_run else "enriched", updated, failed)


if __name__ == "__main__":
    main()
