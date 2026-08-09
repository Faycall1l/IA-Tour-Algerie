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
    url = (
        f"{WAYBACK_CDX}?url=tripadvisor.com/{slug}-g{geo_id}*"
        "&output=json&filter=statuscode:200&limit=100&collapse=urlkey"
    )
    for attempt in range(3):
        try:
            resp = cffi_requests.get(url, impersonate="chrome", timeout=120)
            rows = json.loads(resp.text)
            break
        except Exception as exc:
            if attempt == 2:
                print(f"  cdx {kind} g{geo_id}: {exc}")
                return []
            time.sleep(5 + attempt * 5)
    if len(rows) < 2:
        return []
    primary: dict[str, str] = {}  # urlkey → snapshot ts: bare + -oaN pages
    category: dict[str, str] = {}  # -cN pages (same cards, URI-filtered)
    for row in rows[1:]:
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
    if not urls:
        # No captures within the freshness window — fall back to the widest
        # window so cities with only older captures (e.g. Constantine, 2019)
        # still yield real listings. verified_at marks their age downstream.
        return cdx_snapshots(geo_id, kind, max_age_years=12)
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
    if not items:
        for m in re.finditer(r'<div[^>]*id="ATTR_ENTRY_(\d+)"', html):
            d_id = m.group(1)
            start = m.end()
            end = html.find("</div>", start)
            if end == -1:
                end = start + 4000
            block = html[start : end + 6]
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
                r'alt="([\d.]+) of 5 stars"|class="ui_bubble_rating[^"]*bubble_(\d+)[^"]*"',
                block,
            )
            rating = None
            if rating_m:
                if rating_m.group(1):
                    rating = float(rating_m.group(1))
                elif rating_m.group(2):
                    rating = int(rating_m.group(2)) / 10
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
        seen_ids = set()
        for snap in snaps[:page_limit]:
            try:
                m = re.search(r"/web/(\d{14})id_/", snap)
                verified_at = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}" if m else None
                resp = cffi_requests.get(snap, impersonate="chrome", timeout=90)
                if resp.status_code != 200:
                    print(f"  {kind}: snapshot HTTP {resp.status_code}")
                    continue
                items = parse_listing_html(resp.text, geo_id, kind)
                print(f"  {kind}: {len(items)} listings from {snap[-60:]}")
                for item in items:
                    if item["d_id"] in seen_ids:
                        continue
                    seen_ids.add(item["d_id"])
                    data = enrich_location(item["d_id"])
                    if not data or not data.get("latitude"):
                        continue
                    found.append(
                        {
                            "d_id": item["d_id"],
                            "geo_id": geo_id,
                            "geo_name": name,
                            "name": data.get("name") or item["name"],
                            "kind": kind,
                            "purpose": KIND_CONFIG[kind][2],
                            "category": normalize_category(data, kind),
                            "subtype": ",".join(
                                c.get("name", "")
                                for c in (data.get("subcategory") or [])
                            ),
                            "latitude": float(data["latitude"]),
                            "longitude": float(data["longitude"]),
                            "rating": data.get("rating"),
                            "num_reviews": data.get("num_reviews"),
                            "price_level": (data.get("price_level") or {}).get("level", 0) if isinstance(data.get("price_level"), dict) else data.get("price_level"),
                            "address": data.get("address_obj"),
                            "description": data.get("description"),
                            "photo_url": pick_photo(data)[0],
                            "photo_urls": pick_photo(data)[1],
                            "ranking": data.get("ranking_data"),
                            "verified_at": verified_at,
                        }
                    )
                    await asyncio.sleep(random.uniform(0.1, 0.35))
            except Exception as exc:
                print(f"  {kind}: error {exc}")
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
