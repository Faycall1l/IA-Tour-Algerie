#!/usr/bin/env python3
"""Local OSM PBF extraction for all of Algeria (offline, no network flakiness).

Parses scripts/data/raw/osm/algeria-latest.osm.pbf (Geofabrik official
mirror) with osmium. Real named places only. Wilaya assigned lazily:
per-record nearest-center from raw/wilayas_centers.json.

OUTPUT (unified stage format consumed by the seeding step):
- raw/osm_pois_named.json   tourism / historic / natural / religious POIs
- raw/osm_food_named.json   restaurants / cafes / fast food
- raw/osm_stays_named.json  hotels / hostels / guest houses / camps

PBF is one file → single pass, no queries, no retries, no timeouts.
"""

import json
import math
import sys
from pathlib import Path

import osmium

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "scripts" / "data" / "raw"

POI_TOURISM = {
    "attraction", "museum", "artwork", "viewpoint", "theme_park", "zoo",
    "picnic_site", "gallery", "information" if False else "information",
}
STAY_TOURISM = {
    "hotel", "guest_house", "hostel", "motel", "alpine_hut", "chalet",
    "camp_site", "apartment", "caravan_site", "resort",
}
HIST_VALUES = {
    "archaeological_site", "ruins", "castle", "fort", "fortress", "tomb",
    "monument", "memorial", "palace", "city_gate", "citywalls", "heritage",
    "battle_site", "battlefield", "wayside_shrine", "house", "bridge",
    "manor", "church", "temple", "mosque", "building", "memorial",
}
NATURAL_VALUES = {
    "beach", "peak", "hill", "volcano", "cliff", "dune", "ridge",
    "waterfall", "spring", "hot_spring", "geyser", "cave", "sinkhole",
    "bay", "cape", "oasis", "desert", "lake", "wood", "forest", "wetland",
    "heath", "scrub", "rock", "stone",
}


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class CentroidStore:
    __slots__ = ("centers",)

    def __init__(self):
        self.centers: dict[int, tuple[float, float]] = {}

    def add(self, wid, lat, lon):
        self.centers[wid] = (lat, lon)


class AlgerianHandler(osmium.SimpleHandler):
    def __init__(self, centers):
        super().__init__()
        self.centers = {  # id -> (lat, lon)
            int(w["id"]): (w["latitude"], w["longitude"])
            for w in centers
        }
        self.pois = []
        self.food = []
        self.stays = []
        self.named = 0
        self.skipped = 0

    def nearest_wilaya(self, lat, lon):
        best, best_d = None, None
        for wid, (clat, clon) in self.centers.items():
            d = haversine(lat, lon, clat, clon)
            if best_d is None or d < best_d:
                best, best_d = wid, d
        return best

    def _tags(self, el):
        tags = {}
        for k, v in el.tags:
            tags[k] = v
        return tags

    def _coord(self, el):
        if self.location:
            pass
        try:
            if isinstance(el, (osmium.osm.Node, osmium.osm.WayNode)):
                pass
        except Exception:
            pass
        if el.location.valid() if hasattr(getattr(el, "location", None), "valid") else False:
            try:
                return el.location.lat, el.location.lon
            except Exception:
                pass
        return None

    def _category(self, tags):
        a = tags.get("amenity")
        if a in ("restaurant", "fast_food"):
            return "restaurant", "restaurant"
        if a == "cafe":
            return "cafe", "cafe"
        h = tags.get("historic")
        if h:
            if tags.get("religion") or h in ("wayside_shrine", "wayside_cross"):
                return "religious", f"historic/{h}"
            if h == "memorial":
                return "historical", "memorial"
            if h == "archaeological_site":
                return "historical", "archaeological"
            return "historical", f"historic/{h}"
        n = tags.get("natural")
        if n:
            if n == "beach":
                return "beach", n
            if n in ("peak", "hill", "volcano", "cliff", "dune", "ridge"):
                return "mountain", n
            if n in ("waterfall", "spring", "hot_spring", "geyser", "cave",
                     "sinkhole", "bay", "cape", "oasis", "desert", "lake",
                     "wood", "forest", "wetland", "heath", "scrub", "rock"):
                return "natural", n
            return "natural", n
        t = tags.get("tourism")
        if t == "museum":
            return "museum", "museum"
        if t == "attraction":
            return "cultural", "attraction"
        if t == "viewpoint":
            return "natural", "viewpoint"
        if t == "artwork":
            return "cultural", "artwork"
        if t == "theme_park":
            return "park", "theme_park"
        if t == "zoo":
            return "park", "zoo"
        if t == "picnic_site":
            return "park", "picnic_site"
        if a == "place_of_worship":
            return "religious", a
        return None, None

    PICK_TAGS = (
        "wikidata", "wikipedia", "phone", "website", "opening_hours", "fee",
        "wheelchair", "description", "stars", "capacity", "internet_access",
        "internet_access:fee", "smoking", "wifi", "rooms", "beds",
        "price_range", "address", "cuisine", "vegan", "vegetarian",
        "takeaway", "outdoor_seating",
    )

    def _record(self, el, tags, kind):
        lat, lon = None, None
        loc = getattr(el, "location", None)
        if loc:
            try:
                lat, lon = loc.lat, loc.lon
            except Exception:
                pass
        if lat is None:
            # way/relation: use first available member-node location (fast)
            nodes = getattr(el, "nodes", None)
            if nodes is not None:
                for nd in nodes:
                    nl = getattr(nd, "location", None)
                    if nl is not None:
                        try:
                            lat, lon = nl.lat, nl.lon
                            break
                        except Exception:
                            pass
        if lat is None and "center_lat" in tags:
            lat, lon = float(tags["center_lat"]), float(tags["center_lon"])
        if lat is None:
            center = getattr(el, "center", None)
            if center:
                lat, lon = center.lat, center.lon
        if lat is None or lon is None:
            self.skipped += 1
            return
        wid = self.nearest_wilaya(lat, lon)
        name = tags.get("name")
        if not name:
            self.skipped += 1
            return
        self.named += 1
        ref = f"{kind}/{el.id}"
        url = f"https://www.openstreetmap.org/{ref}"
        rec = {
            "source": "osm",
            "source_id": ref,
            "name_fr": None,
            "name_ar": tags.get("name:ar"),
            "name_en": name,
            "lat": lat,
            "lng": lon,
            "wilaya_code": f"{wid:02d}",
            "description": None,
            "rating": None,
            "num_reviews": None,
            "photo_urls": [],
            "verified_at": "2026-08-01",
            "url": url,
            "refs": {"osm": ref},
            "tags": {k: v for k, v in tags.items() if k in self.PICK_TAGS},
        }
        return rec

    def node(self, n):
        tags = self._tags(n)
        if not tags.get("name"):
            self.skipped += 1
            return
        self._handle(tags, n)

    def way(self, w):
        tags = self._tags(w)
        if not tags.get("name"):
            return
        self._handle(tags, w, is_way=True)

    def relation(self, r):
        tags = self._tags(r)
        if not tags.get("name"):
            return
        self._handle(tags, r, is_way=True, is_rel=True)

    def _handle(self, tags, el, is_way=False, is_rel=False):
        t = tags.get("tourism")
        if t in STAY_TOURISM:
            rec = self._record(el, tags, "way" if is_way else "node")
            if rec:
                stype = {
                    "hotel": "hotel", "motel": "hotel", "hostel": "hostel",
                    "guest_house": "guesthouse", "chalet": "guesthouse",
                    "bed_and_breakfast": "guesthouse",
                }.get(t, "hotel")
                rec["type"] = stype
                rec["subtype"] = t
                rec["purpose"] = "stays"
                self.stays.append(rec)
            return
        if tags.get("amenity") in ("restaurant", "fast_food", "cafe"):
            rec = self._record(el, tags, "way" if is_way else "node")
            if rec:
                cat, sub = "restaurant" if tags["amenity"] != "cafe" else "cafe", tags["amenity"]
                rec["category"] = cat
                rec["subtype"] = sub
                rec["purpose"] = "user"
                self.food.append(rec)
            return
        cat, sub = self._category(tags)
        if cat is None:
            return
        rec = self._record(el, tags, "way" if is_way else "node")
        if rec:
            rec["category"] = cat
            rec["subtype"] = sub
            rec["purpose"] = "user"
            self.pois.append(rec)


def main() -> int:
    pbf = RAW / "osm" / "algeria-latest.osm.pbf"
    if not pbf.exists():
        print(f"missing {pbf} — download from https://download.geofabrik.de/africa/")
        return 1
    centers = json.loads((RAW / "wilayas_centers.json").read_text(encoding="utf-8"))
    h = AlgerianHandler(centers)
    print(f"parsing {pbf.stat().st_size / 1e6:.0f} MB ...", flush=True)
    h.apply_file(str(pbf), locations=True)
    (RAW / "osm_pois_named.json").write_text(
        json.dumps(h.pois, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_food_named.json").write_text(
        json.dumps(h.food, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "osm_stays_named.json").write_text(
        json.dumps(h.stays, ensure_ascii=False), encoding="utf-8"
    )
    qa = {
        "pois": len(h.pois),
        "food": len(h.food),
        "stays": len(h.stays),
        "total": len(h.pois) + len(h.food) + len(h.stays),
        "skipped_no_geom_or_name": h.skipped,
    }
    (RAW / "osm_named_qa.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(json.dumps(qa, ensure_ascii=False, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())