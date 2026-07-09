#!/usr/bin/env python3
"""Extract POIs from OSM for all 58 Algerian wilayas — checkpointed, resumable.

Saves intermediate results per wilaya so partial runs aren't lost.
"""

import json
import math
import os
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"
POI_NODES_PATH = ROOT / "app" / "data" / "poi_nodes_enriched.json"
POI_EDGES_PATH = ROOT / "app" / "data" / "poi_edges_enriched.json"
CHECKPOINT_DIR = ROOT / "app" / "data" / "poi_checkpoints"
CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

WILAYAS = {
    1: {"name": "Adrar", "lat": 27.87, "lon": -0.29, "radius_deg": 1.5},
    2: {"name": "Chlef", "lat": 36.16, "lon": 1.33, "radius_deg": 0.4},
    3: {"name": "Laghouat", "lat": 33.80, "lon": 2.88, "radius_deg": 0.6},
    4: {"name": "Oum El Bouaghi", "lat": 35.87, "lon": 7.12, "radius_deg": 0.4},
    5: {"name": "Batna", "lat": 35.55, "lon": 6.17, "radius_deg": 0.5},
    6: {"name": "Béjaïa", "lat": 36.75, "lon": 5.06, "radius_deg": 0.5},
    7: {"name": "Biskra", "lat": 34.85, "lon": 5.73, "radius_deg": 0.5},
    8: {"name": "Béchar", "lat": 31.62, "lon": -2.22, "radius_deg": 1.0},
    9: {"name": "Blida", "lat": 36.47, "lon": 2.83, "radius_deg": 0.4},
    10: {"name": "Bouira", "lat": 36.37, "lon": 3.90, "radius_deg": 0.4},
    11: {"name": "Tamanrasset", "lat": 22.79, "lon": 5.52, "radius_deg": 2.0},
    12: {"name": "Tébessa", "lat": 35.40, "lon": 8.12, "radius_deg": 0.5},
    13: {"name": "Tlemcen", "lat": 34.88, "lon": -1.32, "radius_deg": 0.5},
    14: {"name": "Tiaret", "lat": 35.37, "lon": 1.32, "radius_deg": 0.5},
    15: {"name": "Tizi Ouzou", "lat": 36.72, "lon": 4.05, "radius_deg": 0.4},
    16: {"name": "Alger", "lat": 36.75, "lon": 3.04, "radius_deg": 0.5},
    17: {"name": "Djelfa", "lat": 34.67, "lon": 3.25, "radius_deg": 0.5},
    18: {"name": "Jijel", "lat": 36.82, "lon": 5.77, "radius_deg": 0.4},
    19: {"name": "Sétif", "lat": 36.19, "lon": 5.41, "radius_deg": 0.5},
    20: {"name": "Saïda", "lat": 34.83, "lon": 0.15, "radius_deg": 0.5},
    21: {"name": "Skikda", "lat": 36.87, "lon": 6.91, "radius_deg": 0.4},
    22: {"name": "Sidi Bel Abbès", "lat": 35.19, "lon": -0.63, "radius_deg": 0.4},
    23: {"name": "Annaba", "lat": 36.90, "lon": 7.77, "radius_deg": 0.4},
    24: {"name": "Guelma", "lat": 36.46, "lon": 7.43, "radius_deg": 0.4},
    25: {"name": "Constantine", "lat": 36.37, "lon": 6.61, "radius_deg": 0.4},
    26: {"name": "Médéa", "lat": 36.27, "lon": 2.75, "radius_deg": 0.4},
    27: {"name": "Mostaganem", "lat": 35.93, "lon": 0.09, "radius_deg": 0.4},
    28: {"name": "M'Sila", "lat": 35.70, "lon": 4.55, "radius_deg": 0.5},
    29: {"name": "Mascara", "lat": 35.40, "lon": 0.14, "radius_deg": 0.4},
    30: {"name": "Ouargla", "lat": 31.96, "lon": 5.33, "radius_deg": 1.0},
    31: {"name": "Oran", "lat": 35.70, "lon": -0.65, "radius_deg": 0.4},
    32: {"name": "El Bayadh", "lat": 32.76, "lon": 1.02, "radius_deg": 0.8},
    33: {"name": "Illizi", "lat": 26.51, "lon": 8.48, "radius_deg": 2.0},
    34: {"name": "Bordj Bou Arréridj", "lat": 36.07, "lon": 4.76, "radius_deg": 0.4},
    35: {"name": "Boumerdès", "lat": 36.76, "lon": 3.48, "radius_deg": 0.3},
    36: {"name": "El Tarf", "lat": 36.77, "lon": 8.31, "radius_deg": 0.4},
    37: {"name": "Tindouf", "lat": 27.67, "lon": -8.13, "radius_deg": 1.5},
    38: {"name": "Tissemsilt", "lat": 35.61, "lon": 1.81, "radius_deg": 0.4},
    39: {"name": "El Oued", "lat": 33.37, "lon": 6.86, "radius_deg": 0.6},
    40: {"name": "Khenchela", "lat": 35.43, "lon": 7.14, "radius_deg": 0.4},
    41: {"name": "Souk Ahras", "lat": 36.29, "lon": 7.95, "radius_deg": 0.4},
    42: {"name": "Tipaza", "lat": 36.59, "lon": 2.45, "radius_deg": 0.3},
    43: {"name": "Mila", "lat": 36.45, "lon": 6.26, "radius_deg": 0.4},
    44: {"name": "Aïn Defla", "lat": 36.26, "lon": 1.97, "radius_deg": 0.4},
    45: {"name": "Naâma", "lat": 33.27, "lon": -0.31, "radius_deg": 0.8},
    46: {"name": "Aïn Témouchent", "lat": 35.30, "lon": -1.14, "radius_deg": 0.4},
    47: {"name": "Ghardaïa", "lat": 32.49, "lon": 3.67, "radius_deg": 0.6},
    48: {"name": "Relizane", "lat": 35.74, "lon": 0.56, "radius_deg": 0.4},
    49: {"name": "Timimoun", "lat": 29.26, "lon": 0.23, "radius_deg": 1.5},
    50: {"name": "Béni Abbès", "lat": 30.08, "lon": -2.16, "radius_deg": 1.5},
    51: {"name": "Aïn Salah", "lat": 27.19, "lon": 2.46, "radius_deg": 1.5},
    52: {"name": "Aïn Guezzam", "lat": 19.57, "lon": 5.77, "radius_deg": 2.0},
    53: {"name": "Touggourt", "lat": 33.11, "lon": 6.06, "radius_deg": 0.6},
    54: {"name": "Djanet", "lat": 24.55, "lon": 9.48, "radius_deg": 1.5},
    55: {"name": "El M'Ghair", "lat": 33.95, "lon": 5.92, "radius_deg": 0.6},
    56: {"name": "El Meniaa", "lat": 30.58, "lon": 2.88, "radius_deg": 1.0},
    57: {"name": "Ouled Djellal", "lat": 34.43, "lon": 5.07, "radius_deg": 0.5},
    58: {"name": "Bordj Badji Mokhtar", "lat": 21.33, "lon": 0.95, "radius_deg": 2.0},
}

OSM_CATEGORIES = {
    "tourism_hotel": {"poi_type": "hotel", "subtype": "accommodation"},
    "tourism_guest_house": {"poi_type": "guest_house", "subtype": "accommodation"},
    "tourism_hostel": {"poi_type": "hostel", "subtype": "accommodation"},
    "tourism_museum": {"poi_type": "museum", "subtype": "culture"},
    "tourism_attraction": {"poi_type": "attraction", "subtype": "tourism"},
    "tourism_artwork": {"poi_type": "artwork", "subtype": "culture"},
    "tourism_viewpoint": {"poi_type": "viewpoint", "subtype": "nature"},
    "tourism_camp_site": {"poi_type": "camp_site", "subtype": "accommodation"},
    "historic_monument": {"poi_type": "monument", "subtype": "culture"},
    "historic_memorial": {"poi_type": "memorial", "subtype": "culture"},
    "historic_ruins": {"poi_type": "ruins", "subtype": "culture"},
    "historic_archaeological_site": {"poi_type": "archaeological_site", "subtype": "culture"},
    "historic_castle": {"poi_type": "castle", "subtype": "culture"},
    "historic_fort": {"poi_type": "fort", "subtype": "culture"},
    "amenity_restaurant": {"poi_type": "restaurant", "subtype": "dining"},
    "amenity_cafe": {"poi_type": "cafe", "subtype": "dining"},
    "amenity_fast_food": {"poi_type": "fast_food", "subtype": "dining"},
    "amenity_pub": {"poi_type": "pub", "subtype": "dining"},
    "amenity_bar": {"poi_type": "bar", "subtype": "dining"},
    "amenity_theatre": {"poi_type": "theatre", "subtype": "entertainment"},
    "amenity_cinema": {"poi_type": "cinema", "subtype": "entertainment"},
    "amenity_library": {"poi_type": "library", "subtype": "culture"},
    "amenity_place_of_worship": {"poi_type": "place_of_worship", "subtype": "culture"},
    "leisure_park": {"poi_type": "park", "subtype": "nature"},
    "leisure_garden": {"poi_type": "garden", "subtype": "nature"},
    "leisure_stadium": {"poi_type": "stadium", "subtype": "sports"},
    "leisure_sports_centre": {"poi_type": "sports_centre", "subtype": "sports"},
    "leisure_marina": {"poi_type": "marina", "subtype": "entertainment"},
    "leisure_nature_reserve": {"poi_type": "nature_reserve", "subtype": "nature"},
    "natural_beach": {"poi_type": "beach", "subtype": "nature"},
    "natural_cave": {"poi_type": "cave", "subtype": "nature"},
    "natural_bay": {"poi_type": "bay", "subtype": "nature"},
    "natural_peak": {"poi_type": "peak", "subtype": "nature"},
    "shop_souvenir": {"poi_type": "souvenir_shop", "subtype": "shopping"},
    "shop_gift": {"poi_type": "gift_shop", "subtype": "shopping"},
    "shop_supermarket": {"poi_type": "supermarket", "subtype": "shopping"},
    "shop_mall": {"poi_type": "mall", "subtype": "shopping"},
    "man_made_lighthouse": {"poi_type": "lighthouse", "subtype": "tourism"},
    "man_made_tower": {"poi_type": "tower", "subtype": "tourism"},
    "man_made_observatory": {"poi_type": "observatory", "subtype": "culture"},
    "water_waterfall": {"poi_type": "waterfall", "subtype": "nature"},
}

OVERLAY_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "ATHAR-OS-POI-Extractor/1.0"


def build_query(lat, lon, radius_deg):
    bbox = f"{lat-radius_deg},{lon-radius_deg},{lat+radius_deg},{lon+radius_deg}"
    return f"""[out:json][timeout:60];
(
  node["tourism"]({bbox});
  node["historic"]({bbox});
  node["amenity"~"restaurant|cafe|fast_food|pub|bar|theatre|cinema|library"]({bbox});
  node["leisure"~"park|garden|stadium|sports_centre|marina|nature_reserve"]({bbox});
  node["natural"~"beach|cave|bay|peak"]({bbox});
  node["shop"~"souvenir|gift|supermarket|mall|bakery|confectionery"]({bbox});
  node["man_made"~"lighthouse|tower|observatory"]({bbox});
  node["water"~"waterfall"]({bbox});
  node["sport"~"diving|swimming|surfing|ski"]({bbox});
);
out body;
"""

def run_query(query, retries=5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                OVERLAY_URL, data=query.encode(),
                headers={"User-Agent": USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=90)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 15 * (attempt + 1)
            elif e.code == 504:
                wait = 30 * (attempt + 1)
            else:
                wait = 10 * (attempt + 1)
            print(f"  [attempt {attempt+1}/{retries}] HTTP {e.code}, waiting {wait}s...")
            time.sleep(wait)
        except urllib.error.URLError as e:
            wait = 20 * (attempt + 1)
            print(f"  [attempt {attempt+1}/{retries}] URL error: {e}, waiting {wait}s...")
            time.sleep(wait)
        except OSError as e:
            wait = 20 * (attempt + 1)
            print(f"  [attempt {attempt+1}/{retries}] OS error: {e}, waiting {wait}s...")
            time.sleep(wait)
    return None


def categorize_poi(tags):
    for tag_key, mapping in OSM_CATEGORIES.items():
        key, val = tag_key.split("_", 1)
        tag_val = tags.get(key)
        if tag_val and tag_val == val:
            return mapping["poi_type"], mapping["subtype"]
        if key == "water" and tags.get("water") == val:
            return mapping["poi_type"], mapping["subtype"]
        if key == "sport" and tags.get("sport") == val:
            return mapping["poi_type"], mapping["subtype"]
    if tags.get("tourism"):
        return f"tourism_{tags['tourism']}", "tourism"
    if tags.get("historic"):
        return f"historic_{tags['historic']}", "culture"
    if tags.get("amenity"):
        return f"amenity_{tags['amenity']}", "other"
    return "unknown", "other"


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def create_poi_nodes(data, wilaya_id, wilaya_name):
    nodes = []
    seen = set()

    for elem in data.get("elements", []):
        tags = elem.get("tags", {})
        lat = elem.get("lat")
        lon = elem.get("lon")
        if lat is None or lon is None:
            continue

        name = tags.get("name", "") or tags.get("name:fr", "") or tags.get("int_name", "")
        name_ar = tags.get("name:ar", "")
        name_en = tags.get("name:en", "") or tags.get("int_name", "")

        poi_type, subtype = categorize_poi(tags)

        safe_name = name.upper().replace(" ", "_") if name else f"UNNAMED_{poi_type}"
        node_id = f"POI_{poi_type.upper()}_{safe_name[:30]}_{elem['id']}"

        dedup_key = (round(lat, 3), round(lon, 3), name)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        node = {
            "node_id": node_id,
            "name": name or f"{poi_type.replace('_', ' ').title()} (non nommé)",
            "name_ar": name_ar,
            "name_en": name_en or name,
            "type": "poi",
            "subtype": poi_type,
            "category": subtype,
            "operator": tags.get("operator"),
            "wilaya_id": wilaya_id,
            "wilaya_name": wilaya_name,
            "latitude": lat,
            "longitude": lon,
            "osm_data": {
                "osm_id": elem["id"],
                "osm_type": elem.get("type", "node"),
            },
            "tags": tags,
            "lines_at_station": [],
            "has_parking": tags.get("parking") == "yes",
            "has_accessibility": tags.get("wheelchair") == "yes",
            "metadata": {
                "source": "osm_poi",
                "poi_type": poi_type,
                "subtype": subtype,
                "wilaya_id": wilaya_id,
            },
            "commune": tags.get("addr:city") or tags.get("addr:district"),
            "website": tags.get("website") or tags.get("contact:website"),
            "phone": tags.get("phone") or tags.get("contact:phone"),
            "opening_hours": tags.get("opening_hours"),
        }
        nodes.append(node)
    return nodes


def connect_to_transit(poi_nodes, transit_nodes, max_walk_km=1.0):
    edges = []
    transit_with_coords = [
        (n["node_id"], n.get("latitude"), n.get("longitude"))
        for n in transit_nodes if n.get("latitude") and n.get("longitude")
    ]

    for poi in poi_nodes:
        lat_p, lon_p = poi["latitude"], poi["longitude"]
        if lat_p is None or lon_p is None:
            continue
        best_dist = float("inf")
        best_node = None
        for tid, tlat, tlon in transit_with_coords:
            if tlat is None or tlon is None:
                continue
            d = haversine_km(lat_p, lon_p, tlat, tlon)
            if d < best_dist and d <= max_walk_km:
                best_dist = d
                best_node = tid
        if best_node:
            dur = max(1, int(best_dist / 5 * 60))
            for f, t, direction in [
                (poi["node_id"], best_node, "forward"),
                (best_node, poi["node_id"], "backward"),
            ]:
                eid = f"EDGE_POI_WALK_{f[-20:]}_{t[-20:]}".upper()
                edges.append({
                    "edge_id": eid,
                    "from_node_id": f,
                    "to_node_id": t,
                    "mode": "transfer",
                    "subtype": "walking",
                    "operator": None,
                    "line_id": "POI_TRANSFER",
                    "line_name": "Accès POI",
                    "direction": direction,
                    "distance_km": round(best_dist, 3),
                    "duration_min": dur,
                    "stops_between": 0,
                    "frequency_min": 5,
                    "pricing": {"single": 0},
                    "schedule": {
                        "first_departure": "00:00",
                        "last_departure": "23:59",
                        "frequency_min": 5,
                        "operating_days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
                    },
                    "first_departure": "00:00",
                    "last_departure": "23:59",
                    "metadata": {"source": "poi_connection"},
                })
    return edges


def load_checkpoints():
    """Load existing checkpoint results."""
    all_nodes = []
    completed = set()
    for f in sorted(CHECKPOINT_DIR.glob("wilaya_*.json")):
        wid = int(f.stem.split("_")[1])
        data = json.loads(f.read_text())
        all_nodes.extend(data)
        completed.add(wid)
    return all_nodes, completed


def save_checkpoint(wilaya_id, nodes):
    path = CHECKPOINT_DIR / f"wilaya_{wilaya_id:02d}.json"
    path.write_text(json.dumps(nodes, ensure_ascii=False))
    print(f"    Checkpoint saved: {path.name}")


def main():
    print("=== OSM POI Extraction for Algeria (checkpointed) ===\n")

    all_poi_nodes, completed = load_checkpoints()
    print(f"Loaded {len(all_poi_nodes)} POI nodes from {len(completed)} checkpointed wilayas")
    print(f"Completed: {sorted(completed)}")
    print(f"Remaining: {sorted(set(WILAYAS) - completed)}\n")

    for wid in sorted(WILAYAS):
        if wid in completed:
            continue

        info = WILAYAS[wid]
        print(f"[{wid:2d}] {info['name']:25s} lat={info['lat']:.2f} lon={info['lon']:.2f} radius={info['radius_deg']}°")
        sys.stdout.flush()

        query = build_query(info["lat"], info["lon"], info["radius_deg"])
        data = run_query(query)
        if not data:
            print(f"  SKIPPED (query failed after retries)")
            continue

        poi_nodes = create_poi_nodes(data, wid, info["name"])

        # Filter: keep only named or historic/tourism-tagged POIs
        filtered = []
        for pn in poi_nodes:
            tags = pn.get("tags", {})
            if not pn.get("name") and not tags.get("historic") and not tags.get("tourism"):
                continue
            filtered.append(pn)

        print(f"  → {len(data.get('elements', []))} OSM elements, {len(filtered)} new POI nodes")

        save_checkpoint(wid, filtered)
        all_poi_nodes.extend(filtered)

        # Polite delay between queries, increasing for southern (larger radius) queries
        delay = 5 if info["radius_deg"] <= 0.5 else 8
        if wid < max(WILAYAS.keys()):
            time.sleep(delay)

    # Deduplicate across all checkpoints
    seen_ids = set()
    seen_coords_name = set()
    unique_pois = []
    for pn in all_poi_nodes:
        key = (round(pn.get("latitude", 0), 3), round(pn.get("longitude", 0), 3), pn.get("name", ""))
        if pn["node_id"] not in seen_ids and key not in seen_coords_name:
            seen_ids.add(pn["node_id"])
            seen_coords_name.add(key)
            unique_pois.append(pn)

    print(f"\n{'='*50}")
    print(f"Total POI nodes collected: {len(all_poi_nodes)}")
    print(f"After dedup: {len(unique_pois)}")

    # Save standalone POI files
    POI_NODES_PATH.write_text(json.dumps(unique_pois, ensure_ascii=False, indent=2))
    print(f"\nSaved: {POI_NODES_PATH}")

    # Load transit graph
    with open(NODES_PATH) as f:
        transit_nodes = json.load(f)
    with open(EDGES_PATH) as f:
        transit_edges = json.load(f)

    existing_node_ids = {n["node_id"] for n in transit_nodes}
    existing_node_coords = {
        (round(n.get("latitude", 0), 3), round(n.get("longitude", 0), 3), n.get("name", ""))
        for n in transit_nodes
    }
    existing_edge_keys = {
        (e["from_node_id"], e["to_node_id"], e.get("line_id", ""), e.get("direction", ""))
        for e in transit_edges
    }

    # Filter out POIs colliding with existing transit nodes
    filtered_pois = []
    for pn in unique_pois:
        dk = (round(pn.get("latitude", 0), 3), round(pn.get("longitude", 0), 3), pn.get("name", ""))
        if dk in existing_node_coords or pn["node_id"] in existing_node_ids:
            continue
        filtered_pois.append(pn)

    print(f"After transit-collision filter: {len(filtered_pois)}")

    # Create walking edges
    print("\nConnecting POIs to transit graph...")
    poi_edges = connect_to_transit(filtered_pois, transit_nodes)
    print(f"Walking edges created: {len(poi_edges)}")

    POI_EDGES_PATH.write_text(json.dumps(poi_edges, ensure_ascii=False, indent=2))
    print(f"Saved: {POI_EDGES_PATH}")

    # Merge into transit graph
    merged_node_count = 0
    for pn in filtered_pois:
        if pn["node_id"] not in existing_node_ids:
            transit_nodes.append(pn)
            existing_node_ids.add(pn["node_id"])
            merged_node_count += 1

    merged_edge_count = 0
    for pe in poi_edges:
        key = (pe["from_node_id"], pe["to_node_id"], pe.get("line_id", ""), pe.get("direction", ""))
        if key not in existing_edge_keys:
            transit_edges.append(pe)
            existing_edge_keys.add(key)
            merged_edge_count += 1

    NODES_PATH.write_text(json.dumps(transit_nodes, ensure_ascii=False, indent=2))
    EDGES_PATH.write_text(json.dumps(transit_edges, ensure_ascii=False, indent=2))

    print(f"\n{'='*50}")
    print(f"Merged {merged_node_count} POI nodes into transit graph")
    print(f"Merged {merged_edge_count} walking edges into transit graph")
    print(f"Final transit nodes: {len(transit_nodes)}")
    print(f"Final transit edges: {len(transit_edges)}")

    cats = Counter(pn.get("subtype", "other") for pn in filtered_pois)
    print("\nPOI Categories:")
    for cat, count in cats.most_common(20):
        print(f"  {cat:20s} {count}")


if __name__ == "__main__":
    main()
