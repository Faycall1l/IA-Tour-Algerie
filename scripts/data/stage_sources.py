#!/usr/bin/env python3
"""Stage all raw data sources into one unified POI corpus (pois_v2.json).

Sources:
- scripts/data/tripadvisor_v2.json        (159 POIs, Wayback + keyless API)
- scripts/data/raw/geoalgeria_culture.json (1,083 Ministry of Culture places)
- scripts/data/raw/geoalgeria_attractions.json (1,248 curated attractions)
- scripts/data/raw/geoalgeria_historic.json   (1,184 historic sites)
- scripts/data/raw/geoalgeria_parks.json      (32 national parks)
- scripts/data/raw/geoalgeria_thermal-springs.json (282 ASAL springs)
- scripts/data/raw/geoalgeria_lodging.json    (1,602 stays → stays_v2.json)

Unified record schema:
  source, source_id, name_fr, name_ar, name_en, category, subtype,
  lat, lng, wilaya_code, description, rating, num_reviews,
  photo_urls, verified_at, url, refs, purpose (user|stays|agent)

Outputs:
- scripts/data/pois_v2.json   (unified POI corpus, stays excluded)
- scripts/data/stays_v2.json  (unified stays corpus)
- scripts/data/staging_qa.json
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "scripts" / "data"
RAW = DATA / "raw"

ATTR_CATEGORY = {
    "artwork": "cultural",
    "museum": "museum",
    "theme_park": "park",
    "viewpoint": "natural",
    "waterfall": "natural",
    "zoo": "park",
    "cave": "natural",
    "attraction": "cultural",
}
HIST_CATEGORY = {
    "archaeological_site": "historical",
    "ruins": "historical",
    "castle": "historical",
    "fort": "historical",
    "fortress": "historical",
    "tomb": "historical",
    "monument": "historical",
    "memorial": "historical",
    "mosque": "religious",
    "church": "religious",
    "church_building": "religious",
    "temple": "religious",
    "battle_site": "historical",
    "battlefield": "historical",
    "palace": "historical",
    "city_gate": "historical",
    "citywalls": "historical",
    "heritage": "historical",
    "district": "cultural",
    "bridge": "historical",
    "castle": "historical",
    "manor": "historical",
    "building": "historical",
    "barracks": "historical",
    "bath": "historical",
    "house": "cultural",
    "library": "cultural",
    "wreck": "historical",
    "war_memorial": "historical",
    "mine": "historical",
    "military": "historical",
    "powder_magazine": "historical",
    "battle_site": "historical",
}
CULTURE_CATEGORY = {
    "protected-cultural-property": "historical",
    "museum": "museum",
    "museum-moudjahid": "museum",
    "theatre": "cultural",
    "cinema": "cultural",
    "cultural-house": "cultural",
    "cultural-palace": "cultural",
    "cultural-center": "cultural",
    "arts-school": "cultural",
    "cultural-directorate": "cultural",
    "library": "cultural",
}
SPRING_CATEGORY = "natural"


def clean_name(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def stage_tripadvisor(rows):
    out = []
    for p in rows:
        out.append(
            {
                "source": "tripadvisor",
                "source_id": str(p["d_id"]),
                "name_fr": None,
                "name_ar": None,
                "name_en": clean_name(p.get("name")),
                "category": p.get("category") or "cultural",
                "subtype": p.get("subtype") or "",
                "lat": p.get("latitude"),
                "lng": p.get("longitude"),
                "wilaya_code": None,  # assigned by wilaya mapper
                "description": p.get("description"),
                "rating": p.get("rating"),
                "num_reviews": p.get("num_reviews"),
                "photo_urls": p.get("photo_urls") or [],
                "verified_at": p.get("verified_at"),
                "url": f"https://www.tripadvisor.com/Attraction_Review-{p.get('geo_id')}-d{p.get('d_id')}",
                "refs": {"tripadvisor": p["d_id"]},
                "purpose": "user",
                "geo_names": p.get("geo_names") or [p.get("geo_name")],
            }
        )
    return out


def stage_culture(rows):
    out = []
    for x in rows:
        cat = CULTURE_CATEGORY.get(x.get("type"), "cultural")
        out.append(
            {
                "source": "geoalgeria-culture",
                "source_id": str(x.get("id")),
                "name_fr": clean_name(x.get("name_fr") or x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "category": cat,
                "subtype": x.get("type") or "",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-01-01",  # dataset published 2026
                "url": x.get("url"),
                "refs": x.get("refs") or {},
                "purpose": "user",
            }
        )
    return out


def stage_attractions(rows):
    out = []
    for x in rows:
        cat = ATTR_CATEGORY.get(x.get("type"), "cultural")
        out.append(
            {
                "source": "geoalgeria-tourisme",
                "source_id": str(x.get("id")),
                "name_fr": clean_name(x.get("name_fr") or x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "category": cat,
                "subtype": x.get("type") or "",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-01-01",
                "url": None,
                "refs": x.get("refs") or {},
                "purpose": "user",
            }
        )
    return out


def stage_historic(rows):
    out = []
    for x in rows:
        cat = HIST_CATEGORY.get(x.get("type"), "historical")
        out.append(
            {
                "source": "geoalgeria-tourisme",
                "source_id": str(x.get("id")),
                "name_fr": clean_name(x.get("name_fr") or x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "category": cat,
                "subtype": x.get("type") or "",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-01-01",
                "url": None,
                "refs": x.get("refs") or {},
                "purpose": "user",
            }
        )
    return out


def stage_parks(rows):
    out = []
    for x in rows:
        out.append(
            {
                "source": "geoalgeria-tourisme",
                "source_id": str(x.get("id") or f"park-{i}") if not x.get("id") else str(x.get("id")),
                "name_fr": clean_name(x.get("name_fr") or x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "category": "park",
                "subtype": "national_park",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-01-01",
                "url": None,
                "refs": x.get("refs") or {},
                "purpose": "user",
            }
        )
    return out


def stage_springs(rows):
    out = []
    for i, x in enumerate(rows):
        out.append(
            {
                "source": "geoalgeria-asal",
                "source_id": str(x.get("id") or f"spring-{i}"),
                "name_fr": clean_name(x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "category": "natural",
                "subtype": f"thermal_spring/{x.get('type') or 'source'}",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": (
                    f"Source thermale (température {x['temperature_c']}°C, "
                    f"débit {x['debit_l_s']} L/s, altitude {x['altitude_m']} m)"
                    if x.get("temperature_c")
                    else "Source thermale (ASAL Geoportail)"
                ),
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2025-01-01",
                "url": None,
                "refs": x.get("refs") or {},
                "purpose": "user",
            }
        )
    return out


def stage_lodging(rows):
    out = []
    map_type = {
        "hotel": "hotel",
        "hostel": "hostel",
        "guest_house": "guesthouse",
        "alpine_hut": "hotel",
        "motel": "hotel",
        "apartment": "apartment",
        "chalet": "guesthouse",
    }
    for i, x in enumerate(rows):
        t = map_type.get(x.get("type"), "hotel")
        out.append(
            {
                "source": "geoalgeria-tourisme",
                "source_id": str(x.get("id") or f"lodging-{i}"),
                "name_fr": clean_name(x.get("name_fr") or x.get("name")),
                "name_ar": clean_name(x.get("name_ar")),
                "name_en": None,
                "type": t,
                "subtype": x.get("type") or "",
                "lat": x.get("lat"),
                "lng": x.get("lng"),
                "wilaya_code": x.get("wilaya_code"),
                "description": None,
                "rating": None,
                "num_reviews": None,
                "photo_urls": [],
                "verified_at": "2026-01-01",
                "url": None,
                "refs": x.get("refs") or {},
                "purpose": "stays",
            }
        )
    return out


def main() -> int:
    pois: list[dict] = []
    stays: list[dict] = []
    qa: dict = {}

    ta = json.loads((DATA / "tripadvisor_v2.json").read_text(encoding="utf-8"))
    qa["tripadvisor"] = len(ta)
    pois += stage_tripadvisor(ta)

    culture = json.loads((RAW / "geoalgeria_culture.json").read_text(encoding="utf-8"))
    qa["geoalgeria_culture"] = len(culture)
    pois += stage_culture(culture)

    attractions = json.loads((RAW / "geoalgeria_attractions.json").read_text(encoding="utf-8"))
    qa["geoalgeria_attractions"] = len(attractions)
    pois += stage_attractions(attractions)

    historic = json.loads((RAW / "geoalgeria_historic.json").read_text(encoding="utf-8"))
    qa["geoalgeria_historic"] = len(historic)
    pois += stage_historic(historic)

    parks = json.loads((RAW / "geoalgeria_parks.json").read_text(encoding="utf-8"))
    qa["geoalgeria_parks"] = len(parks)
    pois += stage_parks(parks)

    springs = json.loads((RAW / "geoalgeria_thermal-springs.json").read_text(encoding="utf-8"))
    qa["geoalgeria_thermal_springs"] = len(springs)
    pois += stage_springs(springs)

    lodging = json.loads((RAW / "geoalgeria_lodging.json").read_text(encoding="utf-8"))
    qa["geoalgeria_lodging"] = len(lodging)
    stays += stage_lodging(lodging)

    qa["pois_total"] = len(pois)
    qa["stays_total"] = len(stays)
    qa["pois_by_source"] = dict(Counter(p["source"] for p in pois))
    qa["pois_by_category"] = dict(Counter(p["category"] for p in pois))
    qa["stays_by_type"] = dict(Counter(s["type"] for s in stays))
    qa["with_both_names"] = sum(1 for p in pois if p["name_fr"] and p["name_ar"])
    qa["wilaya_codes_covered"] = len({p["wilaya_code"] for p in pois if p["wilaya_code"]})

    (DATA / "pois_v2.json").write_text(
        json.dumps(pois, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "stays_v2.json").write_text(
        json.dumps(stays, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATA / "staging_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())