"""Extract OSM transport infrastructure for the 4 zero-station wilayas.

Wilayas 59 (Aflou), 62 (Bir El Ater), 66 (Messaad) and 69 (El Abiodh Sidi
Cheikh) had 0 rows in `stations` — routing could not start/end there.

For each wilaya we query Overpass for real transport nodes around its
center: bus stations, bus stops, railway stations/halts, taxi stands and
tram stops. Results are deduped against existing DB stations by rounded
coordinates and inserted with the correct `station_type` and `wilaya_id`.

New stations have no `line_stops` yet — run
`scripts/data/connect_orphan_stations.py` afterwards so they become
reachable via walking transfers.

Usage:
  PYTHONPATH=. python scripts/data/extract_wilaya_transport.py [--dryrun]
"""

from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text

from app.core.config import settings

REPORT_DIR = Path("scripts/data/reports")
DATABASE_URL = settings.database.url.replace("+asyncpg", "")
OVERPASS = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "ATHAR-Research/1.0 (tourism-data-collection)"}
BBOX_DEG = 1.0
RETRIES = 4
# El Abiodh Sidi Cheikh (69) has very sparse OSM coverage; a wide box 504s.
BBOX_BY_WILAYA = {69: 0.6}

TARGET_WILAYAS = {
    59: "Aflou",
    62: "Bir El Ater",
    66: "Messaad",
    69: "El Abiodh Sidi Cheikh",
}

TYPE_BY_TAG = {
    "bus_station": "bus",
    "bus_stop": "bus",
    "train_station": "train",
    "train_halt": "train",
    "taxi_stand": "taxi",
    "taxi_station": "taxi",
    "tram_stop": "tram",
    "ferry_terminal": "ferry",
}


def _query(center: tuple[float, float], bbox_deg: float = BBOX_DEG) -> list[dict]:
    lat, lon = center
    q = f"""
    [out:json][timeout:60];
    (
      node["amenity"="bus_station"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
      node["highway"="bus_stop"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
      node["railway"="station"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
      node["railway"="halt"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
      node["amenity"="taxi"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
      node["highway"="platform"]["public_transport"="platform"]({lat - bbox_deg},{lon - bbox_deg},{lat + bbox_deg},{lon + bbox_deg});
    );
    out body;
    """
    for attempt in range(RETRIES):
        try:
            resp = httpx.post(
                OVERPASS, data={"data": q}, headers=HEADERS, timeout=120
            )
            resp.raise_for_status()
            return resp.json().get("elements", [])
        except Exception as exc:  # noqa: BLE001
            if attempt == RETRIES - 1:
                print(f"  Overpass failed after {RETRIES} attempts: {exc}")
                return []
            time.sleep(3 * (attempt + 1))
    return []


def _station_type(tags: dict) -> str | None:
    if tags.get("amenity") == "bus_station" or tags.get("public_transport") == "station":
        return "bus"
    if tags.get("highway") == "bus_stop":
        return "bus"
    if tags.get("railway") in ("station", "halt"):
        return "train"
    if tags.get("amenity") == "taxi":
        return "taxi"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract OSM transport for 4 empty wilayas")
    parser.add_argument("--dryrun", action="store_true")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)
    added: list[dict] = []
    skipped: dict[str, int] = {"no_type": 0, "dup": 0}

    with engine.begin() as conn:
        centers = {
            wid: (
                conn.execute(
                    text("SELECT latitude, longitude FROM wilayas WHERE id=:i"),
                    {"i": wid},
                ).fetchone()
            )
            for wid in TARGET_WILAYAS
        }
        existing = {
            (round(r[0], 4), round(r[1], 4))
            for r in conn.execute(text("SELECT latitude, longitude FROM stations"))
        }

        for wid, wname in TARGET_WILAYAS.items():
            center = (centers[wid].latitude, centers[wid].longitude)
            print(f"\n{wid} {wname} @ {center}")
            elements = _query(center, BBOX_BY_WILAYA.get(wid, BBOX_DEG))
            print(f"  OSM elements: {len(elements)}")
            for el in elements:
                tags = el.get("tags", {})
                stype = _station_type(tags)
                if stype is None:
                    skipped["no_type"] += 1
                    continue
                lat, lon = el["lat"], el["lon"]
                if (round(lat, 4), round(lon, 4)) in existing:
                    skipped["dup"] += 1
                    continue
                name = tags.get("name", "") or tags.get("name:fr", "") or tags.get("name:ar", "")
                operator = tags.get("operator", "")[:30] or "OSM"
                if not args.dryrun:
                    conn.execute(
                        text(
                            """
                            INSERT INTO stations (id, name, station_type, wilaya_id,
                                                  latitude, longitude, operator, is_active)
                            VALUES (:id, :name, :stype, :wid, :lat, :lon, :op, true)
                            """
                        ),
                        {
                            "id": uuid.uuid4(),
                            "name": (name or f"Arrêt {wname}")[:200],
                            "stype": stype,
                            "wid": wid,
                            "lat": lat,
                            "lon": lon,
                            "op": operator,
                        },
                    )
                existing.add((round(lat, 4), round(lon, 4)))
                added.append(
                    {"wilaya": wname, "name": name or "(unnamed)", "type": stype, "lat": lat, "lon": lon}
                )

    print(f"\nTotal added: {len(added)}  skipped: {skipped}")
    by_w = {}
    for a in added:
        by_w[a["wilaya"]] = by_w.get(a["wilaya"], 0) + 1
    print("per wilaya:", by_w)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = REPORT_DIR / f"wilaya_transport_{'dryrun' if args.dryrun else 'run'}.txt"
    report.write_text(
        json.dumps(
            {"added": added, "skipped": skipped, "per_wilaya": by_w}, indent=2, ensure_ascii=False
        ),
        encoding="utf-8",
    )
    print(f"Report: {report}")


if __name__ == "__main__":
    main()
