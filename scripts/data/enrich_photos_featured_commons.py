"""Commons text-search photo pass for featured POIs without photos.

High-value targets only: the 344 featured/must-see POIs — 267 still lack a
real photo. The earlier Commons pass (diverse_v2 pass 2) was WAF-blocked (403)
and only ran on southern wilayas; the API is reachable again.

Match quality over quantity:
  * File title must share >=2 normalized tokens with the POI name (or be an
    exact normalized title match).
  * When the file carries coordinates (prop=coordinates), it must be within
    20 km of the POI — a strong wrong-photo guard.
  * Files without coordinates are only accepted on exact title matches.
  * Minimum image size 800x600.

Idempotent: UPDATE only touches rows with an empty photo_url, so re-runs skip
anything already covered.

Usage:
    python scripts/data/enrich_photos_featured_commons.py --dry-run
    python scripts/data/enrich_photos_featured_commons.py --run
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import re
import time
import unicodedata
from pathlib import Path

import httpx
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (photo enrichment; bayrem.aymen@univ-usto.dz)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}
MIN_WIDTH = 800
MIN_HEIGHT = 600
MAX_KM = 10.0
PLACEHOLDER_RE = re.compile(
    r"^(ruins \(non nomm[ée]\)|non nomm[ée]|unknown|unnamed|inconnu|ruines|"
    r"vestiges|d[ée]combres|reste|mausol[ée]e \(non|tombeau \(non)"
)
REQUEST_DELAY = 1.5
STOPWORDS = {
    "de", "des", "du", "d", "la", "le", "les", "un", "une", "et", "à", "au",
    "aux", "en", "sur", "sous", "dans", "pour", "par", "l", "the", "a", "of",
    "and", "in", "with", "el", "ou", "oued", "sidi",
}
ADMIN_JUNK_RE = re.compile(
    r"^(مديرية|مقر|مكتب|ديوان|مصلحة|جامعة|universit[ée]|direction|minist[eè]re|"
    r"mairie|apc|da[iï]ra|commune|préfecture|préfecture|wilaya)"
)
SKIP_SUBTYPES = {
    "library",
    "water",
    "wetland",
    "sand",
    "wood",
    "scrub",
    "desert",
    "bare_rock",
    "valley",
    "thermal_spring/forage",
}


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode()
    s = re.sub(r"[\u2019']", " ", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_name(name: str) -> str:
    return name.split("(")[0].strip()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_placeholder(name: str | None) -> bool:
    return not name or bool(PLACEHOLDER_RE.match(normalize(name))) or len(normalize(name)) < 4


def fetch_targets(conn) -> list[dict]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT p.id::text, p.name, p.name_ar, p.name_en, p.commune,
               w.name_fr, p.latitude, p.longitude, p.category, p.subtype
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE p.is_featured
          AND (p.photo_url IS NULL OR p.photo_url = '')
          AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
        """
    )
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "id": r[0],
            "name": r[1],
            "name_ar": r[2],
            "name_en": r[3],
            "commune": r[4],
            "wilaya": r[5],
            "lat": r[6],
            "lon": r[7],
            "category": r[8],
            "subtype": r[9],
        }
        for r in rows
    ]


def fetch_file_meta(http: httpx.Client, titles: list[str]) -> dict[str, dict]:
    """imageinfo (url/size) + coordinates for a batch of file titles."""
    if not titles:
        return {}
    resp = http.get(
        COMMONS_API,
        params={
            "action": "query",
            "titles": "|".join(titles[:50]),
            "prop": "imageinfo|coordinates",
            "iiprop": "url|size",
            "format": "json",
        },
        headers=HEADERS,
    )
    if resp.status_code != 200:
        return {}
    out: dict[str, dict] = {}
    for page in (resp.json().get("query", {}).get("pages", {}) or {}).values():
        title = page.get("title", "")
        img = (page.get("imageinfo") or [{}])[0]
        w, h = img.get("width", 0), img.get("height", 0)
        url = img.get("url", "")
        coords = (page.get("coordinates") or [{}])[0]
        clat, clon = coords.get("lat"), coords.get("lon")
        out[title] = {"url": url, "width": w, "height": h, "clat": clat, "clon": clon}
    return out


def commons_candidates(http: httpx.Client, t: dict) -> list[tuple[str, str | None]]:
    """Return (file_title, query_token) candidates via Commons text search.

    query_token is set when the query was a single distinctive name token;
    those candidates are coordinate-verified downstream instead of relying on
    lexical title matching (Commons files often spell names differently).
    """
    name = clean_name(t["name"])
    tokens = normalize(name).split()
    distinctive = sorted(
        {tok for tok in tokens if tok not in STOPWORDS and len(tok) >= 6},
        key=len,
        reverse=True,
    )
    stripped = [tok for tok in tokens if tok not in STOPWORDS]
    queries: list[tuple[str, str | None]] = []
    # Most specific first so the candidate pool is not flooded by generic
    # matches (e.g. shared token "ruines" in a different site's files).
    for tok in distinctive:
        queries.append((f"{tok} {t['wilaya']}", tok))
        queries.append((tok, tok))
    queries.append((f'"{name}" {t["wilaya"]}', None))
    if len(stripped) >= 2:
        queries.append((" ".join(stripped), None))
    seen: set[str] = set()
    for q, qtoken in queries:
        for attempt in range(3):
            try:
                resp = http.get(
                    COMMONS_API,
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": q,
                        "srnamespace": 6,
                        "srlimit": 15,
                        "format": "json",
                    },
                    headers=HEADERS,
                )
            except httpx.HTTPError:
                break
            if resp.status_code == 403:
                raise RuntimeError("WAF 403 on Commons search — aborting run")
            if resp.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            if resp.status_code != 200:
                break
            for hit in resp.json().get("query", {}).get("search", []):
                title = hit["title"]
                if title in seen:
                    continue
                seen.add(title)
                yield title, qtoken
            break
        time.sleep(REQUEST_DELAY)


def title_matches(name_norm: str, name_tokens: list[str], title: str) -> float:
    """Return a match score (0 = reject). 2.0 exact, 1.0 >=2 distinctive
    tokens, 0.5 one distinctive (>=6 char) token. Stopwords never count."""
    title_norm = normalize(title.replace("File:", ""))
    if not title_norm or len(title_norm) < 5:
        return 0.0
    if title_norm == name_norm:
        return 2.0
    distinctive = [tok for tok in name_tokens if tok not in STOPWORDS]
    shared = set(title_norm.split()) & set(distinctive)
    if len(shared) >= 2:
        return 1.0
    if len(shared) == 1 and len(shared.pop()) >= 6:
        return 0.5
    return 0.0


def pick_candidate(http: httpx.Client, t: dict, seen_titles: set[str]) -> dict | None:
    name = clean_name(t["name"])
    name_norm = normalize(name)
    name_tokens = name_norm.split()
    collected: list[dict] = []
    for title, qtoken in commons_candidates(http, t):
        if title in seen_titles:
            continue
        score = title_matches(name_norm, name_tokens, title)
        collected.append({"title": title, "score": score, "qtoken": qtoken})
        if len(collected) >= 40:
            break
    if not collected:
        return None
    meta = fetch_file_meta(http, [c["title"] for c in collected])
    best: dict | None = None
    for c in collected:
        info = meta.get(c["title"]) or {}
        url, w, h = info.get("url"), info.get("width", 0), info.get("height", 0)
        if not url or w < MIN_WIDTH or h < MIN_HEIGHT:
            continue
        clat, clon = info.get("clat"), info.get("clon")
        coord_ok = False
        if clat is not None and clon is not None:
            d = haversine_km(t["lat"], t["lon"], clat, clon)
            if d <= MAX_KM:
                coord_ok = True
        if coord_ok:
            # Coordinates are the strongest signal: accept a distinctive-token
            # candidate (handles title spelling variants) or a title match.
            if c["score"] < 0.5 and not (c["qtoken"] and len(c["qtoken"]) >= 7):
                continue
        elif c["score"] < 1.0:
            continue  # no coordinates: >=2 tokens or exact title only
        if best is None or c["score"] > best["score"]:
            best = {
                "title": c["title"],
                "url": url,
                "score": c["score"],
                "has_coords": clat is not None,
            }
    return best


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--commit-every", type=int, default=25)
    args = parser.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    targets = fetch_targets(conn)
    log.info("featured POIs without photo: %d", len(targets))
    targets = [
        t
        for t in targets
        if not is_placeholder(t["name"])
        and (t.get("subtype") or "") not in SKIP_SUBTYPES
        and t["category"] not in ("cafe", "restaurant")
        and not ADMIN_JUNK_RE.match(t["name"] or "")
    ]
    log.info("after placeholder/subtype filter: %d", len(targets))
    if args.limit:
        targets = targets[: args.limit]

    state_path = Path("scripts/data/reports/photos_commons_featured_state.json")
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    seen_titles: set[str] = set(state.get("titles", []))
    attempted: set[str] = set(state.get("attempted", []))

    candidates: list[dict] = []
    timeout = httpx.Timeout(45.0, connect=20.0, read=45.0)
    with httpx.Client(follow_redirects=True, timeout=timeout) as http:
        for i, t in enumerate(targets):
            if t["id"] in attempted:
                continue
            try:
                pick = pick_candidate(http, t, seen_titles)
            except RuntimeError as exc:
                log.warning("%s", exc)
                break
            attempted.add(t["id"])
            if pick:
                seen_titles.add(pick["title"])
                candidates.append(
                    {
                        "poi": t,
                        "image_url": pick["url"],
                        "source": "commons-featured",
                        "attribution": (
                            f"Wikimedia Commons: {pick['title']}"
                            + (" (coordinate-verified)" if pick["has_coords"] else " (exact title)")
                        ),
                    }
                )
            if (i + 1) % 25 == 0:
                log.info("  searched %d/%d, matched %d", i + 1, len(targets), len(candidates))
            state = {"titles": sorted(seen_titles), "attempted": sorted(attempted)}
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(state))
            time.sleep(REQUEST_DELAY)

    log.info("matched candidates: %d", len(candidates))
    if args.dry_run or not args.run:
        for c in candidates[:25]:
            log.info("[DRY] %s -> %s", c["poi"]["name"][:40], c["image_url"][:90])
        conn.close()
        return

    from scripts.data.migrate_photos_minio import download_and_upload, get_minio_client

    minio_client = get_minio_client()
    updated = failed = 0
    with httpx.Client(follow_redirects=True, timeout=timeout) as http:
        for c in candidates:
            try:
                minio_url, _ext = download_and_upload(minio_client, http, c["image_url"])
            except Exception as exc:  # noqa: BLE001
                log.warning("download/upload error %s: %s", c["poi"]["name"], exc)
                minio_url = None
            if not minio_url:
                failed += 1
                log.warning("no image for %s", c["poi"]["name"][:50])
                continue
            update_poi_photo(conn, c["poi"]["id"], minio_url, c["source"], c["attribution"])
            updated += 1
            if updated % args.commit_every == 0:
                conn.commit()
                log.info("  progress: %d enriched, %d failed", updated, failed)
    conn.commit()
    log.info("done: %d enriched, %d failed", updated, failed)
    conn.close()


if __name__ == "__main__":
    main()
