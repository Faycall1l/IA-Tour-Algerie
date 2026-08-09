#!/usr/bin/env python3
"""Scrape real TripAdvisor POI data for Algeria — zero-cost, no API key.

Pipeline:
1. Geo ID discovery: known Algerian city/province geo IDs + CDX prefix scans
2. Wayback listing pages: fetch archived Attractions/Restaurants pages per geo
3. Parse listing cards → location IDs (d-ids), names, photo URLs, ratings
4. Enrich each d-id via the keyless internal API `/data/1.0/location/{id}`
   (name, coords, rating, num_reviews, address, category, photo)
5. Write `tripadvisor_pois.json` for the seeding step.

TripAdvisor live pages are DataDome-walled, but:
- Wayback Machine snapshots of listing pages are fully parseable
- `data/1.0/location/{id}` is open (no key)
- `media-cdn.tripadvisor.com` photo CDN is open

Usage:
    python scripts/data/scrape_tripadvisor.py --city Algiers --page-limit 3
    python scripts/data/scrape_tripadvisor.py --all-cities --page-limit 3
"""

import argparse
import asyncio
import concurrent.futures
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx
from curl_cffi import requests as cffi_requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_FILE = ROOT / "scripts" / "data" / "tripadvisor_pois.json"
CDX_CACHE = ROOT / "scripts" / "data" / ".cdx_cache.json"

# City → (geo_id, type). geo_id is the TripAdvisor "narrow" city geo.
# Verified via data/1.0/location/{id}.
KNOWN_GEO_IDS = {
    "Algeria": (293717, "country"),
    "Algiers": (293718, "city"),
    "Algiers Province": (2600683, "province"),
    "Constantine": (734459, "city"),
    "Mostaganem": (734460, "city"),
    "Tebessa": (734461, "city"),
    "Tlemcen": (734462, "city"),
    "Annaba": (1071600, "city"),
    "Guelma": (2602144, "province"),
    "El Khroub": (19979066, "city"),
    "Casbah": (12931390, "city"),
    "Bordj El Bahri": (17484551, "city"),
    "Adrar Province": (2600506, "province"),
    "Ain Temouchent Province": (2600600, "province"),
    "Oran Province": (2600638, "province"),
    "Annaba Province": (2600703, "province"),
    "Bejaia Province": (2600752, "province"),
    "Blida Province": (2600822, "province"),
    "Bouira Province": (2600903, "province"),
    "Boumerdes Province": (2600925, "province"),
    "Chlef Province": (2601017, "province"),
    "Constantine Province": (2602028, "province"),
    "El Bayadh Province": (2602073, "province"),
    "El Tarf Province": (2602103, "province"),
    "Illizi Province": (2602163, "province"),
    "Khenchela Province": (2602211, "province"),
    "Mascara Province": (2602256, "province"),
    "Mila Province": (2602297, "province"),
    "Naama Province": (2602326, "province"),
    "Saida Province": (2602416, "province"),
    "Setif Province": (2602426, "province"),
    "Sidi Bel Abbas Province": (2602468, "province"),
    "Skikda Province": (2602492, "province"),
    "Tamanrasset Province": (2602542, "province"),
    "Tipasa Province": (2602584, "province"),
    "Tissemsilt Province": (2602605, "province"),
    "Tlemcen Province": (2602628, "province"),
    # Geo-discovery scan (2026-08-09, via country-page links + location API):
    "Cherchell": (4363354, "city"),
    "Setif": (424904, "city"),
    "Oran": (303167, "city"),
    "Jijel": (801303, "city"),
    "Es Senia": (18717700, "suburb"),
    "Blida": (2600838, "city"),
    "Mascara": (2602256, "city"),
    "Borj Bou Arreridj": (2600856, "city"),
    "Alger Centre": (12017949, "suburb"),
    "Djanet": (1984335, "city"),
    "Ghardaia": (317053, "city"),
    "Tamanrasset": (303168, "city"),
    "Tipasa": (424906, "city"),
    "Djemila": (946433, "site"),
    "Batna": (424900, "city"),
    "Skikda": (2602501, "city"),
    "Bou-Saada": (1074167, "city"),
    "Laghouat": (2602235, "city"),
    "Hassi Messaoud": (3326190, "city"),
    "M'sila": (424903, "city"),
    "Ghardaia Province": (1536382, "province"),
}

# TripAdvisor category key → ATHAR poi.category (pois CHECK constraint)
CATEGORY_MAP = {
    "attractions": "cultural",
    "landmarks": "historical",
    "museums": "museum",
    "nature_parks": "natural",
    "beaches": "beach",
    "parks": "park",
    "religions": "religious",
    "shopping": "market",
    "restaurants": "restaurant",
    "cafes": "cafe",
    "nightlife": "other",
    "activities": "other",
    "other": "other",
}

WAYBACK_CDX = "https://web.archive.org/cdx/search/cdx"
WAYBACK_ARCHIVE = "https://web.archive.org/web"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# kind → (listing slug, snapshot freshness window in years, purpose)
# purpose: "user" → pois table (user + agent face them), "stays" → stays
# table, "agent" → agent knowledge only (not user listings).
KIND_CONFIG = {
    "attractions": ("Attractions", 2, "user"),
    "restaurants": ("Restaurants", 8, "user"),
    "hotels": ("Hotels", 2, "stays"),
}
REVIEW_SLUG = r"(?:Attraction|Restaurant|Hotel)_Review"


def _cdx_cache() -> dict:
    try:
        return json.loads(CDX_CACHE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _cdx_cache_save(cache: dict) -> None:
    try:
        CDX_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def cdx_snapshots(geo_id: int, kind: str, max_age_years: int | None = None) -> list[str]:
    """Find newest Wayback snapshots of TripAdvisor listing pages.

    kind: 'attractions' | 'restaurants' | 'hotels'
    Returns web.archive.org URLs: newest bare page first, then pagination
    pages (-oaN), deduplicated. Freshness window per kind config — we are in
    August 2026, so attractions/hotels snapshots must be ≥2024; restaurants
    have no recent captures (old snapshots only) — kept with older window and
    flagged by their verified_at timestamp downstream.
    """
    slug, default_years, _ = KIND_CONFIG[kind]
    max_age_years = max_age_years or default_years
    cache_key = f"{geo_id}:{kind}:{max_age_years}"
    cache = _cdx_cache()
    if cache_key in cache:
        return cache[cache_key]
    url = (
        f"{WAYBACK_CDX}?url=tripadvisor.com/{slug}-g{geo_id}*"
        "&output=json&filter=statuscode:200&limit=100&collapse=urlkey"
    )
    rows = []
    for attempt in range(2):
        try:
            print(f"  cdx> {kind} g{geo_id} window={max_age_years}y ...", flush=True)
            resp = cffi_requests.get(url, impersonate="chrome", timeout=60)
            rows = json.loads(resp.text)
            print(f"  cdx< {kind} g{geo_id}: {max(len(rows) - 1, 0)} rows", flush=True)
            break
        except Exception as exc:
            if attempt == 1:
                print(f"  cdx! {kind} g{geo_id}: {exc}")
                cache[cache_key] = []
                _cdx_cache_save(cache)
                return []
            time.sleep(3)
    primary: dict[str, str] = {}  # urlkey → snapshot ts: bare + -oaN pages
    category: dict[str, str] = {}  # -cN pages (same cards, URI-filtered)
    for row in rows[1:]:
        if len(row) < 3:
            continue
        ts, u = row[1], row[2]
        key = u.split("?")[0]
        year = int(ts[:4])
        if year < 2026 - max_age_years:
            continue
        if re.search(r"z[a-z]{2}\d+", key):
            continue  # diet/meal/price/vibe filters — never useful
        if re.search(rf"g{geo_id}(?:-[^-/]*)?-?c\d+", key):
            bucket = category
        else:
            bucket = primary
        if key not in bucket or ts > bucket[key]:
            bucket[key] = ts
    # bare/oa pages first; fall back to category pages only when a geo has
    # no unfiltered listing page archived (e.g. Tlemcen — only -cN in 2025)
    buckets = primary or category
    urls = sorted(
        (f"{WAYBACK_ARCHIVE}/{ts}id_/{u}" for u, ts in buckets.items()),
        key=lambda x: 0 if "-oa" not in x else 1,
    )
    if not urls and max_age_years != 12:
        # No captures within the freshness window — fall back to the widest
        # window so cities with only older captures (e.g. Constantine, 2019)
        # still yield real listings. verified_at marks their age downstream.
        # Guarded against recursion: the 12y call itself never falls back.
        print(f"  cdx~ {kind} g{geo_id}: empty in {max_age_years}y, retry 12y", flush=True)
        urls = cdx_snapshots(geo_id, kind, max_age_years=12)
    cache[cache_key] = urls
    _cdx_cache_save(cache)
    return urls


def parse_listing_html(html: str, geo_id: int, kind: str) -> list[dict]:
    """Extract listing cards from archived TripAdvisor HTML.

    Two layouts:
    - modern SSR cards (article blocks) — parsed first
    - older pages (≤2019) with ItemList JSON-LD — fallback
    params:
        - kind: 'attractions' | 'restaurants' | 'hotels'
    Returns [{d_id, name, photo_url, rating, reviews, link}]
    """
    items = []
    seen = set()

    def add(d_id, name, photo_url=None, rating=None, reviews=None, link=""):
        if d_id in seen:
            return
        seen.add(d_id)
        items.append(
            {
                "d_id": d_id,
                "name": name,
                "photo_url": photo_url,
                "rating": rating,
                "reviews": reviews,
                "link": link,
                "kind": kind,
            }
        )

    # Modern layout: article cards. On geo-level listing pages the review
    # links carry the *city* geo id, not the page's own (e.g. country page
    # g293717 links `Attraction_Review-g424904-d10054787-...` for Setif).
    # Accept any Algerian geo id — enrichment is per d_id, geo is irrelevant.
    for m in re.finditer(
        r'<article class="[^"]*"[^>]*>(.*?)</article>', html, re.S
    ):
        block = m.group(1)
        link_m = re.search(
            rf'{REVIEW_SLUG}-g\d+-d(\d+)', block
        )
        if not link_m:
            continue
        d_id = link_m.group(1)
        name_m = re.search(r'title="([^"]+)"', block)
        name = name_m.group(1).strip() if name_m else ""
        if not name:
            name_m = re.search(
                r"<span[^>]*class=\"[^\"]*biGQs[^\"]*[^>]*>([^<]+)</span>", block
            )
            name = name_m.group(1).strip() if name_m else ""
        photo_m = re.search(
            r'src="(https://[^"]*media-cdn[^"]+\.jpg[^"]*)"', block
        )
        photo_url = photo_m.group(1).split("?")[0] if photo_m else None
        rating_m = re.search(r"(\d(?:\.\d)?) of 5 bubbles", block)
        rating = float(rating_m.group(1)) if rating_m else None
        reviews_m = re.search(r"(\d+) review", block)
        reviews = int(reviews_m.group(1)) if reviews_m else None
        add(d_id, name, photo_url, rating, reviews, link_m.group(0))

    # Older layout: ItemList JSON-LD (name + URL per position)
    if not items:
        for m in re.finditer(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S
        ):
            try:
                data = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict) or data.get("@type") != "ItemList":
                continue
            for entry in data.get("itemListElement") or []:
                url = (entry.get("url") or "").replace("\\u002F", "/")
                d_m = re.search(rf"{REVIEW_SLUG}-g\d+-d(\d+)", url)
                if not d_m:
                    continue
                add(
                    d_m.group(1),
                    entry.get("name", ""),
                    link=url,
                )
    # Pre-2020 legacy layout: divs with data-locationid + ATTR_ENTRY ids
    # e.g. <div id="ATTR_ENTRY_8489661" class="attraction_element" data-locationid="8489661">
    # (2011-2016 variant: <div class="listing ..." id="attraction_4172783">)
    if not items:
        for m in re.finditer(
            r'<div[^>]*id="(?:ATTR_ENTRY_|attraction_)(\d+)"', html
        ):
            d_id = m.group(1)
            start = m.end()
            # window: next listing container or 6000 chars (the attraction_
            # variant splits the listing into sibling divs)
            nxt = re.search(r'<div[^>]*id="(?:ATTR_ENTRY_|attraction_)\d+"', html[start + 1 :])
            end = (start + 1 + nxt.start()) if nxt else min(start + 6000, len(html))
            block = html[start:end]
            if not block or (
                "Attraction_Review" not in block
                and "location-name" not in block
                and "listing_title" not in block
            ):
                continue
            name_m = re.search(
                r'data-name="([^"]+)"|class="location-name[^"]*"[^>]*>\s*([^<]+)',
                block,
            )
            name = (
                (name_m.group(1) or name_m.group(2)).strip()
                if name_m
                else ""
            )
            if not name:
                name_m = re.search(
                    r'<a href="/Attraction_Review-g\d+-d\d+-Reviews-[^"]+">([^<]+)</a>',
                    block,
                )
                name = name_m.group(1).strip() if name_m else ""
            photo_m = re.search(
                r'<img[^>]+src="(https://[^"]+)"', block
            )
            photo_url = photo_m.group(1).split("?")[0] if photo_m else None
            rating_m = re.search(
                r'alt="([\d.]+) of 5 stars"|class="ui_bubble_rating[^"]*bubble_(\d+)[^"]*"|class="rate rate_no no(\d+)',
                block,
            )
            rating = None
            if rating_m:
                if rating_m.group(1):
                    rating = float(rating_m.group(1))
                elif rating_m.group(2):
                    rating = int(rating_m.group(2)) / 10
                elif rating_m.group(3):
                    rating = int(rating_m.group(3)) / 10
            reviews_m = re.search(r"(\d+)\s+reviews?", block)
            reviews = int(reviews_m.group(1)) if reviews_m else None
            add(
                d_id,
                name,
                photo_url,
                rating,
                reviews,
                f"Attraction_Review-g{geo_id}-d{d_id}",
            )
    return items


def enrich_location(d_id: str) -> dict | None:
    """Fetch full POI metadata from the keyless internal API."""
    for attempt in range(3):
        try:
            resp = cffi_requests.get(
                f"https://www.tripadvisor.com/data/1.0/location/{d_id}",
                impersonate="chrome",
                headers={"accept": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200 and resp.text.strip().startswith("{"):
                return json.loads(resp.text)
            return None
        except Exception:
            time.sleep(1 + attempt * 2)
    return None


def pick_photo(data: dict) -> tuple[str | None, list[str]]:
    """Extract best photo URLs from data/1.0 response."""
    images = (data.get("photo") or {}).get("images") or {}
    orig = (images.get("original") or {}).get("url")
    med = (images.get("medium") or {}).get("url")
    url = orig or med
    urls = []
    for img in images.values():
        u = (img or {}).get("url")
        if u and u not in urls:
            urls.append(u)
    return url, urls


def normalize_category(data: dict, kind: str) -> str:
    cats = data.get("subcategory") or []
    keys = [c.get("key", "") for c in cats]
    for k in keys:
        mapped = CATEGORY_MAP.get(k)
        if mapped:
            return mapped
    if kind == "restaurants":
        return "restaurant"
    if kind == "hotels":
        return "stay"
    return "cultural"


def snapshot_tail(snaps: list[str]) -> str:
    return snaps[0].split("id_/")[-1][-45:] if snaps else ""

def fetch_snapshot_items(
    snap: str, geo_id: int, kind: str
) -> tuple[str, list[dict]]:
    """Fetch one archive snapshot and parse its listing cards (thread pool)."""
    m = re.search(r"/web/(\d{14})id_/", snap)
    verified_at = (
        f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}" if m else None
    )
    for attempt in range(3):
        try:
            resp = cffi_requests.get(snap, impersonate="chrome", timeout=60)
            if resp.status_code != 200:
                return verified_at, []
            items = parse_listing_html(resp.text, geo_id, kind)
            return verified_at, items
        except Exception:
            if attempt == 2:
                return verified_at, []
            time.sleep(2)
    return verified_at, []


def enrich_batch(items: list[dict], verified_at: str, geo_id: int, name: str, kind: str):
    """Enrich parsed listing cards via the keyless location API (parallel)."""
    found = []

    def one(item: dict | None) -> dict | None:
        if item is None:
            return None
        data = enrich_location(item["d_id"])
        if not data or not data.get("latitude"):
            return None
        photo_url, photo_urls = pick_photo(data)
        return {
            "d_id": item["d_id"],
            "geo_id": geo_id,
            "geo_name": name,
            "name": data.get("name") or item["name"],
            "kind": kind,
            "purpose": KIND_CONFIG[kind][2],
            "category": normalize_category(data, kind),
            "subtype": ",".join(
                c.get("name", "") for c in (data.get("subcategory") or [])
            ),
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "rating": data.get("rating"),
            "num_reviews": data.get("num_reviews"),
            "price_level": (
                (data.get("price_level") or {}).get("level", 0)
                if isinstance(data.get("price_level"), dict)
                else data.get("price_level")
            ),
            "address": data.get("address_obj"),
            "description": data.get("description"),
            "photo_url": photo_url,
            "photo_urls": photo_urls,
            "ranking": data.get("ranking_data"),
            "verified_at": verified_at,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        for poi in ex.map(one, items):
            if poi:
                found.append(poi)
    return found


async def scrape_geo(
    geo_id: int, name: str, kinds: list[str], page_limit: int
) -> list[dict]:
    print(f"== {name} (g{geo_id})")
    found = []
    for kind in kinds:
        snaps = cdx_snapshots(geo_id, kind)
        if not snaps:
            print(f"  no {kind} snapshot")
            continue
        snapshot_items: list[tuple[str, list[dict]]] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = [
                ex.submit(fetch_snapshot_items, snap, geo_id, kind)
                for snap in snaps[:page_limit]
            ]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    snapshot_items.append(fut.result())
                except Exception as exc:
                    print(f"  {kind}: snapshot error {exc}")
        for verified_at, items in snapshot_items:
            if items:
                print(
                    f"  {kind}: {len(items)} listings from {snapshot_tail(snaps)} {verified_at}"
                )
        seen_ids = set()
        for verified_at, items in snapshot_items:
            fresh = [it for it in items if it["d_id"] not in seen_ids]
            for it in fresh:
                seen_ids.add(it["d_id"])
            if not fresh:
                continue
            enriched = enrich_batch(
                [it for it in fresh], verified_at, geo_id, name, kind
            )
            print(f"  {kind}: enriched {len(enriched)}/{len(fresh)}")
            found.extend(enriched)
    return found


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", help="Single city name from KNOWN_GEO_IDS")
    parser.add_argument("--all-cities", action="store_true")
    parser.add_argument("--page-limit", type=int, default=2, help="Listing pages per kind")
    parser.add_argument("--kinds", default="attractions,restaurants,hotels")
    parser.add_argument(
        "--purpose",
        default=None,
        help="Only keep this purpose: user | stays | agent (default: all)",
    )
    args = parser.parse_args()

    if args.city:
        if args.city not in KNOWN_GEO_IDS:
            print(f"Unknown city {args.city!r}; known: {list(KNOWN_GEO_IDS)}")
            sys.exit(1)
        geos = {args.city: KNOWN_GEO_IDS[args.city]}
    elif args.all_cities:
        geos = KNOWN_GEO_IDS
    else:
        geos = {"Algiers": KNOWN_GEO_IDS["Algiers"]}

    kinds = [k.strip() for k in args.kinds.split(",")]
    all_pois = []
    for city, (geo_id, _) in geos.items():
        found = await scrape_geo(geo_id, city, kinds, args.page_limit)
        if args.purpose:
            found = [p for p in found if p.get("purpose") == args.purpose]
        all_pois.extend(found)
        print(f"  -> {city}: {len(found)} POIs (total {len(all_pois)})")

    OUT_FILE.write_text(
        json.dumps(all_pois, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nWrote {len(all_pois)} POIs to {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
