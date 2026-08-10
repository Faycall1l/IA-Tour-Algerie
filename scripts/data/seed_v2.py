#!/usr/bin/env python3
"""Seed DB from unified v2 corpus."""
import asyncio, json, math, re, unicodedata, uuid
from datetime import date
from pathlib import Path
import asyncpg

DATA = Path(__file__).resolve().parent.parent.parent / "scripts" / "data"

def norm(s):
    return re.sub(r"[^a-z0-9]+", "", unicodedata.normalize("NFKD", (s or "").lower()))

def hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

def nearest(lat, lon, centers):
    best, best_d = None, None
    for wid, (clat, clon) in centers.items():
        d = hav(lat, lon, clat, clon)
        if best_d is None or d < best_d:
            best, best_d = wid, d
    return best

def dedupe(recs):
    seen = {}
    for r in recs:
        key = (r["wilaya_id"], norm(r.get("name") or r.get("name_en") or ""), round(r["lat"],4), round(r["lng"],4))
        prev = seen.get(key)
        if prev is None or (r.get("source") != "osm" and prev.get("source") == "osm"):
            seen[key] = r
    return list(seen.values())

async def main():
    conn = await asyncpg.connect("postgresql://athar:athar_pass@localhost:5434/athar_db")
    centers = {int(r["id"]): (float(r["latitude"]), float(r["longitude"])) for r in await conn.fetch("SELECT id, latitude, longitude FROM wilayas")}
    provider_id = await conn.fetchval("SELECT id FROM users WHERE role='hotel' LIMIT 1")
    if not provider_id:
        provider_id = await conn.fetchval("SELECT id FROM users LIMIT 1")

    pois = json.loads((DATA / "pois_v2.json").read_text(encoding="utf-8"))
    stays = json.loads((DATA / "stays_v2.json").read_text(encoding="utf-8"))

    poi_rows = []
    for p in pois:
        lat, lng = p.get("lat"), p.get("lng")
        if lat is None or lng is None:
            continue
        wid = nearest(lat, lng, centers)
        source = p.get("source", "unknown")
        tags = p.get("tags") or {}
        url = p.get("url")
        refs = p.get("refs") or {}
        if source == "tripadvisor" and refs.get("tripadvisor"):
            url = f"https://www.tripadvisor.com/Attraction_Review-g{p.get('geo_id')}-d{refs['tripadvisor']}"
        elif source == "geoalgeria-culture" and p.get("url"):
            url = p["url"]
        name = p.get("name_fr") or p.get("name_en") or ""
        name_en = p.get("name_en") or p.get("name_fr") or ""
        poi_rows.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "name_ar": p.get("name_ar"),
            "name_en": name_en,
            "category": p.get("category", "cultural"),
            "subtype": p.get("subtype", ""),
            "wilaya_id": wid,
            "latitude": lat,
            "longitude": lng,
            "description": p.get("description"),
            "photo_url": (p.get("photo_urls") or [None])[0],
            "photo_urls": p.get("photo_urls") or [],
            "website": url,
            "phone": tags.get("phone"),
            "opening_hours": tags.get("opening_hours"),
            "operator": tags.get("operator"),
            "cuisine": tags.get("cuisine"),
            "osm_node_id": refs.get("osm").split("/")[-1] if refs.get("osm") and refs.get("osm").startswith("node/") else None,
            "osm_type": refs.get("osm").split("/")[0] if refs.get("osm") else None,
            "osm_tags": tags if tags else None,
            "source": source,
            "source_id": str(p.get("source_id") or ""),
            "verified_at": date.fromisoformat(p.get("verified_at")) if p.get("verified_at") else None,
        })

    poi_rows = dedupe(poi_rows)

    stay_rows = []
    for s in stays:
        lat, lng = s.get("lat"), s.get("lng")
        if lat is None or lng is None:
            continue
        wid = nearest(lat, lng, centers)
        tags = s.get("tags") or {}
        stay_rows.append({
            "id": str(uuid.uuid4()),
            "provider_id": provider_id,
            "name": s.get("name_fr") or s.get("name_en") or "",
            "property_type": s.get("type", "hotel"),
            "description": s.get("description"),
            "wilaya_id": wid,
            "address": tags.get("address"),
            "latitude": lat,
            "longitude": lng,
            "price_per_night_dzd": None,
            "amenities": json.dumps({k: v for k, v in tags.items() if k in ("wifi","internet_access","stars","rooms","beds","smoking")}),
            "photos": s.get("photo_urls") or [],
            "check_in_time": None,
            "check_out_time": None,
            "max_guests": tags.get("capacity"),
            "total_rooms": tags.get("rooms"),
            "source": s.get("source", "unknown"),
            "source_id": str(s.get("source_id") or ""),
            "verified_at": date.fromisoformat(s.get("verified_at")) if s.get("verified_at") else None,
        })

    stay_rows = dedupe(stay_rows)

    print(f"Inserting {len(poi_rows)} POIs and {len(stay_rows)} stays...")

    if poi_rows:
        cols = list(poi_rows[0].keys())
        vals = [[r[c] for c in cols] for r in poi_rows]
        await conn.executemany(f"INSERT INTO pois ({','.join(cols)}) VALUES ({','.join(['$'+str(i+1) for i in range(len(cols))])})", vals)

    if stay_rows:
        cols = list(stay_rows[0].keys())
        vals = [[r[c] for c in cols] for r in stay_rows]
        await conn.executemany(f"INSERT INTO stays ({','.join(cols)}) VALUES ({','.join(['$'+str(i+1) for i in range(len(cols))])})", vals)

    print("done")
    await conn.close()

asyncio.run(main())
