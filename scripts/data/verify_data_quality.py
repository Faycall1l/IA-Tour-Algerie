"""Data quality verification script for POIs.

Runs rule-based checks on all POIs and reports:
- Missing phone/website/opening_hours
- Short/auto-generated descriptions
- Category mismatches (OSM tags vs assigned category)
- Coordinate issues (lat/lng outside expected range for Algeria)

Usage: PYTHONPATH=. python scripts/data/verify_data_quality.py [--fix] [--limit N]
"""

import argparse
import asyncio
import logging

from sqlalchemy import func, select, update

from app.db.session import async_session
from app.models.poi import POI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ALGERIA_BBOX = {"lat_min": 18.0, "lat_max": 37.5, "lng_min": -9.0, "lng_max": 12.0}

TAG_CATEGORY_MAP = {
    "amenity": {
        "place_of_worship": "religious",
        "museum": "museum",
        "restaurant": "restaurant",
        "cafe": "cafe",
        "marketplace": "market",
        "theatre": "cultural",
        "cinema": "cultural",
        "library": "cultural",
        "townhall": "cultural",
    },
    "historic": None,
    "leisure": {
        "park": "park",
        "beach_resort": "beach",
        "garden": "park",
        "nature_reserve": "natural",
        "stadium": "cultural",
    },
    "natural": {"beach": "beach", "peak": "mountain", "volcano": "natural"},
    "tourism": {
        "museum": "museum",
        "artwork": "cultural",
        "gallery": "cultural",
        "viewpoint": "natural",
        "picnic_site": "park",
    },
    "building": {"museum": "museum", "cathedral": "religious", "mosque": "religious", "church": "religious"},
}

HISTORIC_CATEGORIES = ("historical",)


def _infer_category(osm_tags: dict | None) -> str | None:
    if not osm_tags:
        return None
    for tag_key, mapping in TAG_CATEGORY_MAP.items():
        val = osm_tags.get(tag_key)
        if val:
            if mapping is None:
                # Any value for this key means historical (historic=*)
                return HISTORIC_CATEGORIES[0]
            if val in mapping:
                return mapping[val]
    return None


async def verify_poi(poi: POI, fix: bool = False) -> dict:
    issues = []

    # 1. Description quality
    desc = poi.description or ""
    if len(desc) < 30:
        issues.append("missing_short_description")
    elif "—" in desc and len(desc) < 100:
        issues.append("auto_generated_description")

    desc_ok = not issues

    # 2. Category check
    inferred = _infer_category(poi.osm_tags)
    cat_ok = True
    if inferred and inferred != poi.category:
        cat_ok = False
        if fix:
            issues.append(f"fixed_category:{poi.category}->{inferred}")
        else:
            issues.append(f"wrong_category:{poi.category}->{inferred}")

    # 3. Missing contact
    missing = []
    if poi.phone is None:
        missing.append("phone")
    if poi.website is None:
        missing.append("website")
    if poi.opening_hours is None:
        missing.append("opening_hours")

    # 4. Coordinates
    coord_ok = True
    if poi.latitude is not None and poi.longitude is not None:
        if not (ALGERIA_BBOX["lat_min"] <= poi.latitude <= ALGERIA_BBOX["lat_max"]):
            coord_ok = False
            issues.append("lat_outside_algeria")
        if not (ALGERIA_BBOX["lng_min"] <= poi.longitude <= ALGERIA_BBOX["lng_max"]):
            coord_ok = False
            issues.append("lng_outside_algeria")

    # 5. Photo missing for featured POIs
    if poi.is_featured and not poi.photo_url and (not poi.photo_urls or len(poi.photo_urls) == 0):
        issues.append("featured_no_photo")

    return {
        "id": str(poi.id),
        "name": poi.name,
        "category": poi.category,
        "desc_ok": desc_ok,
        "cat_ok": cat_ok,
        "inferred_cat": inferred,
        "missing": missing,
        "coord_ok": coord_ok,
        "is_featured": poi.is_featured,
        "issues": issues,
        "score": 5 - len(issues) - len(missing),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Fix auto-fixable issues")
    parser.add_argument("--limit", type=int, default=0, help="Max POIs to check (0=all)")
    args = parser.parse_args()

    async with async_session() as db:
        query = select(POI).order_by(POI.is_featured.desc(), POI.name)
        if args.limit:
            query = query.limit(args.limit)
        result = await db.execute(query)
        pois = result.scalars().all()

    logger.info("Verifying %d POIs...", len(pois))
    total_issues = 0
    cat_fixes = []
    featured_no_photo = 0

    for poi in pois:
        report = await verify_poi(poi, fix=args.fix)
        n_issues = len(report["issues"])
        total_issues += n_issues

        if n_issues > 0 and report["is_featured"]:
            featured_no_photo += 1

        for issue in report["issues"]:
            if issue.startswith("fixed_category:") or issue.startswith("wrong_category:"):
                cat_fixes.append(report)
                if args.fix and issue.startswith("fixed_category:"):
                    new_cat = issue.split("->")[1]
                    async with async_session() as db:
                        await db.execute(update(POI).where(POI.id == poi.id).values(category=new_cat))
                        await db.commit()

    # Report
    logger.info("=" * 60)
    logger.info("VERIFICATION REPORT")
    logger.info("=" * 60)
    logger.info("Total POIs checked: %d", len(pois))
    logger.info("Total issues found: %d", total_issues)
    logger.info("Avg issues/POI: %.2f", total_issues / max(len(pois), 1))
    logger.info("Featured without photos: %d", featured_no_photo)
    logger.info("Category mismatches: %d", len(cat_fixes))

    missing_phone = sum(1 for p in pois if p.phone is None)
    missing_website = sum(1 for p in pois if p.website is None)
    missing_hours = sum(1 for p in pois if p.opening_hours is None)
    logger.info("Missing phone: %d (%.1f%%)", missing_phone, missing_phone / max(len(pois), 1) * 100)
    logger.info("Missing website: %d (%.1f%%)", missing_website, missing_website / max(len(pois), 1) * 100)
    logger.info("Missing opening_hours: %d (%.1f%%)", missing_hours, missing_hours / max(len(pois), 1) * 100)

    score = sum(max(1, 5 - len(r["issues"]) - len(r["missing"])) for r in (await asyncio.gather(*[verify_poi(p) for p in pois[:1000]])))
    logger.info("Avg quality score (first 1000): %.1f/5", score / min(1000, len(pois)))


if __name__ == "__main__":
    asyncio.run(main())
