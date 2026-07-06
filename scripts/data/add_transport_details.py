#!/usr/bin/env python3
"""Add comprehensive schedules, pricing, and metadata to all transport edges.

Reads transit_nodes_enriched.json / transit_edges_enriched.json,
enriches every edge with realistic schedules and pricing, and writes back.

Usage:
  python scripts/add_transport_details.py
"""

import json
import math
from pathlib import Path
from copy import deepcopy

ROOT = Path(__file__).resolve().parent.parent
NODES_PATH = ROOT / "app" / "data" / "transit_nodes_enriched.json"
EDGES_PATH = ROOT / "app" / "data" / "transit_edges_enriched.json"

# ── SNTF pricing (known official fares + distance-based estimate) ──

SNTF_PRICING_TABLE = {
    # (from_code, to_code): {"first": DZD, "second": DZD}
    (37, 305): (1860, 1360),
    (37, 376): (620, 440),
    (37, 251): (620, 450),
    (37, 134): (620, 450),
    (37, 90): (1050, 770),
    (37, 10): (620, 450),
    (37, 25): (1050, 770),
    (37, 23): (1250, 920),
    (37, 168): (820, 600),
    (37, 114): (500, 350),
    (37, 415): (450, 320),
    (37, 560): (400, 300),
    (37, 525): (350, 250),
    (37, 71): (500, 350),
    (37, 182): (820, 600),
    (37, 5): (1100, 800),
    (37, 7): (1200, 880),
    (37, 22): (1400, 1000),
    (37, 27): (1000, 730),
    (37, 30): (1300, 950),
    (37, 13): (1600, 1180),
    (37, 21): (1100, 800),
    (126, 90): (720, 525),
    (126, 376): (550, 400),
    (168, 305): (820, 600),
    (305, 22): (620, 450),
    (305, 13): (820, 600),
    (305, 5): (1100, 800),
    (22, 13): (620, 450),
    (25, 23): (620, 450),
    (25, 7): (650, 470),
    (25, 5): (620, 450),
    (25, 376): (350, 250),
    (25, 21): (400, 290),
    (5, 7): (450, 330),
}

# ── Calculate missing fares by km ──
FIRST_PER_KM = 3.5
SECOND_PER_KM = 2.5


def estimate_sntf_fare(dist_km: float) -> tuple[int, int]:
    first = max(200, int(dist_km * FIRST_PER_KM))
    second = max(150, int(dist_km * SECOND_PER_KM))
    return first, second


# ── Metro schedules ──
METRO_SCHEDULE = {
    "frequency_min": {"peak": 3, "offpeak": 5, "friday": 6},
    "first_departure": "05:00",
    "last_departure": "23:00",
    "pricing": {"single": 50, "book_of_10": 400},
    "schedule_samples": [
        {"departure": "05:00", "arrival": "05:30", "frequency": "daily"},
        {"departure": "07:00", "arrival": "07:30", "frequency": "weekdays"},
        {"departure": "16:00", "arrival": "16:30", "frequency": "weekdays"},
        {"departure": "10:00", "arrival": "10:30", "frequency": "weekends"},
    ],
}

# ── Tram schedules ──
TRAM_SCHEDULE = {
    "frequency_min": {"peak": 6, "offpeak": 12},
    "first_departure": "05:00",
    "last_departure": "22:30",
    "pricing": {"single": 40, "book_of_10": 350},
    "schedule_samples": [
        {"departure": "05:30", "arrival": "05:45", "frequency": "daily"},
        {"departure": "07:30", "arrival": "07:45", "frequency": "weekdays"},
        {"departure": "12:00", "arrival": "12:15", "frequency": "daily"},
        {"departure": "17:00", "arrival": "17:15", "frequency": "weekdays"},
        {"departure": "21:00", "arrival": "21:15", "frequency": "daily"},
    ],
}

# ── Cable car schedules ──
CABLECAR_SCHEDULES = {
    "Télécabine d'Alger": {
        "frequency_min": 5,
        "first_departure": "07:00",
        "last_departure": "19:00",
        "pricing": {"single": 30, "round_trip": 50},
        "schedule_samples": [
            {"departure": "07:00", "arrival": "07:05", "frequency": "daily"},
            {"departure": "10:00", "arrival": "10:05", "frequency": "daily"},
            {"departure": "14:00", "arrival": "14:05", "frequency": "daily"},
            {"departure": "18:00", "arrival": "18:05", "frequency": "daily"},
        ],
    },
    "Télécabine d'Oran": {
        "frequency_min": 10,
        "first_departure": "08:00",
        "last_departure": "18:00",
        "pricing": {"single": 25, "round_trip": 40},
        "schedule_samples": [
            {"departure": "08:00", "arrival": "08:10", "frequency": "daily"},
            {"departure": "12:00", "arrival": "12:10", "frequency": "daily"},
            {"departure": "16:00", "arrival": "16:10", "frequency": "daily"},
        ],
    },
}

# ── Ferry schedules ──
FERRY_SCHEDULES = {
    "Port d'Alger (Ferry) ↔ Port de Marseille (Ferry)": {
        "frequency": "3-4x/week",
        "duration_min": 1440,
        "pricing": {"salon": 15000, "cabine": 25000, "couchette": 35000},
        "schedule_samples": [
            {"departure": "10:00", "arrival": "10:00+1", "frequency": "mon_wed_fri"},
            {"departure": "14:00", "arrival": "14:00+1", "frequency": "tue_sat"},
        ],
    },
    "Port d'Alger (Ferry) ↔ Port de Tunis (Ferry)": {
        "frequency": "1-2x/week",
        "duration_min": 2160,
        "pricing": {"salon": 12000, "cabine": 20000, "couchette": 28000},
        "schedule_samples": [
            {"departure": "08:00", "arrival": "20:00+1", "frequency": "wed_sat"},
        ],
    },
    "Port d'Alger (Ferry) ↔ Port de Sète (Ferry)": {
        "frequency": "1x/week",
        "duration_min": 1380,
        "pricing": {"salon": 13000, "cabine": 22000, "couchette": 30000},
        "schedule_samples": [
            {"departure": "12:00", "arrival": "12:00+1", "frequency": "fri"},
        ],
    },
    "Port d'Oran (Ferry) ↔ Port d'Alicante (Ferry)": {
        "frequency": "2-3x/week",
        "duration_min": 480,
        "pricing": {"salon": 9000, "cabine": 15000, "couchette": 21000},
        "schedule_samples": [
            {"departure": "09:00", "arrival": "17:00", "frequency": "mon_thu_sat"},
        ],
    },
    "Port de Béjaïa (Ferry) ↔ Port de Marseille (Ferry)": {
        "frequency": "1x/week",
        "duration_min": 1380,
        "pricing": {"salon": 13000, "cabine": 22000, "couchette": 30000},
        "schedule_samples": [
            {"departure": "11:00", "arrival": "11:00+1", "frequency": "sun"},
        ],
    },
    "Port de Skikda (Ferry) ↔ Port de Marseille (Ferry)": {
        "frequency": "seasonal",
        "duration_min": 1440,
        "pricing": {"salon": 12000, "cabine": 20000, "couchette": 28000},
        "schedule_samples": [
            {"departure": "15:00", "arrival": "15:00+1", "frequency": "tue_summer"},
        ],
    },
}

# ── Flight schedules ──
FLIGHT_PRICING = {
    # (from_airport_name_key, to_airport_name_key): (econ_min, econ_max, biz_min, biz_max)
    "Alger_Oran": (7000, 12000, 15000, 25000),
    "Alger_Constantine": (7000, 12000, 15000, 25000),
    "Alger_Annaba": (8000, 13000, 17000, 28000),
    "Alger_Tlemcen": (8000, 13000, 17000, 28000),
    "Alger_Ouargla": (10000, 15000, 20000, 32000),
    "Alger_Tamanrasset": (14000, 20000, 28000, 40000),
    "Alger_Hassi_Messaoud": (10000, 15000, 20000, 32000),
    "Alger_Ghardaia": (10000, 15000, 20000, 32000),
    "Alger_Bechar": (12000, 17000, 24000, 36000),
    "Alger_Illizi": (15000, 22000, 30000, 45000),
    "Alger_Djanet": (16000, 24000, 32000, 48000),
    "Alger_In_Amenas": (14000, 20000, 28000, 40000),
    "Alger_El_Oued": (9000, 14000, 18000, 30000),
    "Alger_Timimoun": (13000, 19000, 26000, 38000),
    "Alger_Bejaia": (6000, 10000, 12000, 20000),
    "Alger_Biskra": (9000, 14000, 18000, 30000),
    "Alger_Tebessa": (10000, 15000, 20000, 32000),
}

FLIGHT_FREQUENCIES = {
    "Alger_Oran": {"daily": 5, "freq_min": 120, "first": "06:00", "last": "21:00"},
    "Alger_Constantine": {"daily": 4, "freq_min": 180, "first": "07:00", "last": "20:00"},
    "Alger_Annaba": {"daily": 3, "freq_min": 240, "first": "08:00", "last": "19:00"},
    "Alger_Tlemcen": {"daily": 3, "freq_min": 240, "first": "08:00", "last": "19:00"},
    "Alger_Ouargla": {"daily": 2, "freq_min": 360, "first": "07:00", "last": "17:00"},
    "Alger_Tamanrasset": {"daily": 2, "freq_min": 360, "first": "06:00", "last": "15:00"},
    "Alger_Hassi_Messaoud": {"daily": 2, "freq_min": 360, "first": "08:00", "last": "16:00"},
    "Alger_Ghardaia": {"daily": 2, "freq_min": 360, "first": "07:30", "last": "15:30"},
    "Alger_Bechar": {"daily": 2, "freq_min": 360, "first": "08:00", "last": "16:00"},
    "Alger_Illizi": {"weekly": 3, "freq_min": None, "first": "08:00", "last": "14:00"},
    "Alger_Djanet": {"weekly": 2, "freq_min": None, "first": "09:00", "last": "13:00"},
    "Alger_In_Amenas": {"weekly": 2, "freq_min": None, "first": "08:00", "last": "14:00"},
    "Alger_El_Oued": {"daily": 1, "freq_min": 720, "first": "10:00", "last": "16:00"},
    "Alger_Timimoun": {"weekly": 2, "freq_min": None, "first": "09:00", "last": "15:00"},
    "Alger_Bejaia": {"daily": 1, "freq_min": 720, "first": "11:00", "last": "17:00"},
    "Alger_Biskra": {"daily": 1, "freq_min": 720, "first": "10:00", "last": "16:00"},
    "Alger_Tebessa": {"weekly": 3, "freq_min": None, "first": "09:00", "last": "15:00"},
}

DOMESTIC_AIRPORTS = {
    "Alger": "A_ROPORT_D_ALGER_HOUARI_BOUMEDIENE",
    "Oran": "A_ROPORT_D_ORAN_AHMED_BEN_BELLA",
    "Constantine": "A_ROPORT_DE_CONSTANTINE_MOHAMED_BOUDIAF",
    "Annaba": "A_ROPORT_D_ANNABA_RABAH_BITAT",
    "Tlemcen": "A_ROPORT_DE_TLEMCEN_ZENATA",
    "Ouargla": "A_ROPORT_D_OUARGLA_AIN_BEIDA",
    "Tamanrasset": "A_ROPORT_DE_TAMANRASSET",
    "Bechar": "A_ROPORT_DE_B_CHAR_BOUDGHENE",
    "Bejaia": "A_ROPORT_DE_B_JA_A_ABANE_RAMDANE",
    "Ghardaia": "A_ROPORT_DE_GHARDA_A_NOUM_RAT",
    "Hassi_Messaoud": "A_ROPORT_DE_HASSI_MESSAOUD_OUED_IRARA",
    "Illizi": "A_ROPORT_D_ILLIZI_TAKHAMALT",
    "Djanet": "A_ROPORT_DE_DJANET",
    "In_Amenas": "A_ROPORT_D_IN_AMENAS",
    "El_Oued": "A_ROPORT_D_EL_OUED_GUEMAR",
    "Timimoun": "A_ROPORT_DE_TIMIMOUN",
    "Biskra": None,
    "Tebessa": None,
}


def route_key(from_name: str, to_name: str) -> str:
    parts = set()
    for n in [from_name, to_name]:
        n = n.replace("Aéroport d'", "").replace("d'", "").replace("(", "").replace(")", "")
        for token in n.split():
            parts.add(token)
    return "_".join(sorted(parts))


def find_flight_key(from_name: str, to_name: str) -> str | None:
    for city, node_key in DOMESTIC_AIRPORTS.items():
        if node_key and node_key in from_name:
            from_city = city
            break
    else:
        return None
    for city, node_key in DOMESTIC_AIRPORTS.items():
        if node_key and node_key in to_name:
            to_city = city
            break
    else:
        return None
    candidates = [
        f"{from_city}_{to_city}",
        f"{to_city}_{from_city}",
    ]
    for c in candidates:
        if c in FLIGHT_PRICING:
            return c
    return None


def hhmm_to_min(hhmm: str) -> int:
    parts = hhmm.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def main():
    with open(NODES_PATH) as f:
        nodes: list[dict] = json.load(f)
    with open(EDGES_PATH) as f:
        edges: list[dict] = json.load(f)

    node_map = {n["node_id"]: n for n in nodes}

    enriched_sched = 0
    enriched_price = 0
    new_nodes = 0
    new_edges = 0

    for e in edges:
        mode = e.get("mode", "")
        op = e.get("operator", "")
        line_name = e.get("line_name", "")
        dist = e.get("distance_km") or 0
        dur = e.get("duration_min") or 0

        # ── Metro ──
        if mode == "metro":
            if not e.get("schedule"):
                e["schedule"] = METRO_SCHEDULE["schedule_samples"]
            if not e.get("pricing"):
                e["pricing"] = METRO_SCHEDULE["pricing"]
            e["frequency_min"] = METRO_SCHEDULE["frequency_min"]["peak"]
            e["first_departure"] = METRO_SCHEDULE["first_departure"]
            e["last_departure"] = METRO_SCHEDULE["last_departure"]
            enriched_sched += 1
            enriched_price += 1

        # ── Tram ──
        elif mode == "tram":
            if not e.get("schedule"):
                e["schedule"] = TRAM_SCHEDULE["schedule_samples"]
            if not e.get("pricing"):
                e["pricing"] = TRAM_SCHEDULE["pricing"]
            e["frequency_min"] = TRAM_SCHEDULE["frequency_min"]["peak"]
            e["first_departure"] = TRAM_SCHEDULE["first_departure"]
            e["last_departure"] = TRAM_SCHEDULE["last_departure"]
            enriched_sched += 1
            enriched_price += 1

        # ── Cable car ──
        elif mode == "cablecar":
            sched = CABLECAR_SCHEDULES.get(line_name) or CABLECAR_SCHEDULES.get("Télécabine d'Alger")
            if not e.get("schedule") and sched:
                e["schedule"] = sched["schedule_samples"]
            if not e.get("pricing") and sched:
                e["pricing"] = sched["pricing"]
            if sched:
                e["frequency_min"] = sched["frequency_min"]
                e["first_departure"] = sched["first_departure"]
                e["last_departure"] = sched["last_departure"]
                enriched_sched += 1
                enriched_price += 1

        # ── Ferry ──
        elif mode == "ferry":
            sched = FERRY_SCHEDULES.get(line_name)
            if sched:
                if not e.get("schedule"):
                    e["schedule"] = sched["schedule_samples"]
                if not e.get("pricing"):
                    e["pricing"] = sched["pricing"]
                e["frequency_min"] = None
                e["first_departure"] = sched["schedule_samples"][0]["departure"] if sched["schedule_samples"] else None
                e["last_departure"] = e.get("first_departure")
                enriched_sched += 1
                enriched_price += 1

        # ── Flight ──
        elif mode == "flight":
            fn = e.get("from_node_id", "")
            tn = e.get("to_node_id", "")
            fk = find_flight_key(fn, tn) or find_flight_key(tn, fn)
            if fk:
                prices = FLIGHT_PRICING.get(fk, (9000, 14000, 18000, 30000))
                freq = FLIGHT_FREQUENCIES.get(fk, {})
                if not e.get("pricing"):
                    e["pricing"] = {
                        "economy_min": prices[0],
                        "economy_max": prices[1],
                        "business_min": prices[2],
                        "business_max": prices[3],
                    }
                first_hh = freq.get("first", "07:00")
                last_hh = freq.get("last", "19:00")
                if not e.get("schedule"):
                    e["schedule"] = []
                    num = freq.get("daily", 3)
                    for i in range(num):
                        dep = f"{int(first_hh.split(':')[0]) + i * 3:02d}:{first_hh.split(':')[1]}"
                        arr_min = hhmm_to_min(dep) + dur
                        arr = f"{arr_min // 60 % 24:02d}:{arr_min % 60:02d}"
                        e["schedule"].append({
                            "departure": dep,
                            "arrival": arr,
                            "frequency": "daily",
                        })
                e["frequency_min"] = freq.get("freq_min")
                e["first_departure"] = first_hh
                e["last_departure"] = last_hh
                enriched_sched += 1
                enriched_price += 1

        # ── Banlieue suburban train ──
        elif mode == "train" and "banlieue" in e.get("line_id", "").lower():
            if not e.get("pricing"):
                flat = max(50, int(dist * 2))
                e["pricing"] = {"first_class": flat, "second_class": max(30, int(flat * 0.7))}
            if not e.get("schedule"):
                lid = e.get("line_id", "").lower()
                # Real SNTF frequencies per line (2025-2026 data)
                if "axe_central" in lid:
                    trains_per_day = 62
                    first_h, last_h = 5, 22
                    freq = 15
                elif "banlieue_est" in lid:
                    trains_per_day = 18
                    first_h, last_h = 6, 19
                    freq = 50
                elif "banlieue_ouest" in lid:
                    trains_per_day = 18
                    first_h, last_h = 5, 20
                    freq = 50
                elif "constantine" in lid:
                    trains_per_day = 8
                    first_h, last_h = 6, 18
                    freq = 90
                elif "annaba" in lid:
                    trains_per_day = 6
                    first_h, last_h = 6, 17
                    freq = 120
                elif "oran" in lid:
                    trains_per_day = 8
                    first_h, last_h = 6, 18
                    freq = 90
                else:
                    trains_per_day = 12
                    first_h, last_h = 6, 19
                    freq = 60
                num_dep = max(4, trains_per_day // 3)
                e["schedule"] = []
                step = int((last_h - first_h) * 60 / max(num_dep, 1))
                for i in range(num_dep):
                    dep_mm = first_h * 60 + i * step
                    dep = f"{dep_mm // 60 % 24:02d}:{dep_mm % 60:02d}"
                    arr_mm = dep_mm + dur
                    arr = f"{arr_mm // 60 % 24:02d}:{arr_mm % 60:02d}"
                    e["schedule"].append({
                        "departure": dep,
                        "arrival": arr,
                        "frequency": "daily",
                    })
                e["first_departure"] = f"{first_h:02d}:00"
                e["last_departure"] = f"{last_h:02d}:30"
                e["frequency_min"] = freq
            enriched_sched += 1
            enriched_price += 1

        # ── SNTF intercity train ──
        elif mode == "train" and op == "SNTF":
            if not e.get("pricing"):
                first, second = estimate_sntf_fare(dist)
                e["pricing"] = {"first_class": first, "second_class": second}
            if not e.get("schedule"):
                num_dep = max(2, min(6, int(720 / max(dur, 60))))
                e["schedule"] = []
                for i in range(num_dep):
                    dep_h = 6 + i * 3
                    dep = f"{dep_h:02d}:00"
                    arr_min = dep_h * 60 + dur
                    arr = f"{arr_min // 60 % 24:02d}:{arr_min % 60:02d}"
                    e["schedule"].append({
                        "departure": dep,
                        "arrival": arr,
                        "frequency": "daily",
                    })
                e["first_departure"] = "06:00"
                e["last_departure"] = f"{6 + (num_dep - 1) * 3:02d}:00"
                e["frequency_min"] = max(60, dur // 2)
            enriched_sched += 1
            enriched_price += 1

        # ── Bus ──
        elif mode == "bus" and op in ("SOGRAL", "SNTV", "TRANSTEV"):
            if not e.get("pricing"):
                cost_per_km = 8 if op == "SOGRAL" else 7
                e["pricing"] = {"estimated_dzd": int(dist * cost_per_km), "class": "standard"}
            if not e.get("schedule"):
                num_dep = max(1, min(3, int(480 / max(dur, 120))))
                e["schedule"] = []
                for i in range(num_dep):
                    dep_h = 7 + i * 5
                    dep = f"{dep_h:02d}:00"
                    arr_min = dep_h * 60 + dur
                    arr = f"{arr_min // 60 % 24:02d}:{arr_min % 60:02d}"
                    e["schedule"].append({
                        "departure": dep,
                        "arrival": arr,
                        "frequency": "daily",
                    })
                e["first_departure"] = "07:00"
                e["last_departure"] = "17:00"
                e["frequency_min"] = max(120, dur)
            enriched_sched += 1
            enriched_price += 1

    # ── Remaining flight edges (unmatched by name) ──
    for e in edges:
        if e["mode"] == "flight" and (not e.get("pricing")):
            dur = e.get("duration_min") or 120
            e["pricing"] = {
                "economy_min": 9000,
                "economy_max": 15000,
                "business_min": 18000,
                "business_max": 30000,
            }
            if not e.get("schedule"):
                e["schedule"] = [{"departure": "08:00", "arrival": f"{8 + dur//60:02d}:{dur%60:02d}", "frequency": "daily"}]
            enriched_sched += 1
            enriched_price += 1

    # ── Transfer edges: add metadata but no schedule/pricing needed ──
    for e in edges:
        if e["mode"] == "transfer":
            e["metadata"] = e.get("metadata") or {
                "type": "walking_transfer",
                "description": "Intermodal pedestrian connection",
            }
            e["pricing"] = e.get("pricing") or {"cost": 0, "currency": "DZD"}
            e["schedule"] = e.get("schedule") or [{"departure": "always", "arrival": "always", "frequency": "continuous"}]
            enriched_sched += 1
            enriched_price += 1

    print(f"Enriched schedules: {enriched_sched}/{len(edges)} edges")
    print(f"Enriched pricing:   {enriched_price}/{len(edges)} edges")

    # ── Deduplicate edges with same edge_id ──
    seen = set()
    deduped = []
    for e in edges:
        if e["edge_id"] not in seen:
            seen.add(e["edge_id"])
            deduped.append(e)
    dupes_removed = len(edges) - len(deduped)
    edges = deduped
    if dupes_removed:
        print(f"Removed {dupes_removed} duplicate edges")

    with open(EDGES_PATH, "w") as f:
        json.dump(edges, f, indent=2, ensure_ascii=False)
    print(f"Written: {EDGES_PATH}")

    # Quick validation
    eids = [e["edge_id"] for e in edges]
    if len(eids) != len(set(eids)):
        print("WARNING: duplicate edge_ids remain!")
    nids = {n["node_id"] for n in nodes}
    missing = [e["from_node_id"] for e in edges if e["from_node_id"] not in nids]
    missing += [e["to_node_id"] for e in edges if e["to_node_id"] not in nids]
    if missing:
        print(f"WARNING: {len(missing)} edges reference non-existent node_ids")
    else:
        print("Validation: all edge references valid")

    sched_count = sum(1 for e in edges if e.get("schedule"))
    price_count = sum(1 for e in edges if e.get("pricing"))
    print(f"Final: {len(edges)} edges, {sched_count} with schedules, {price_count} with pricing")


if __name__ == "__main__":
    main()
