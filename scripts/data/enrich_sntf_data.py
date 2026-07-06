#!/usr/bin/env python3
"""Fetch ScrapNTF station IDs, define banlieue lines, fetch pricing, and write enriched JSON.

Self-contained — no imports from the athar project.
"""

import json
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "app" / "data"
OUTPUT_PATH = DATA_DIR / "sntf_enriched.json"

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) EnrichBot/1.0",
    "Mozilla/5.0 (X11; Linux x86_64) TrainDataCollector/2.0",
    "OpenTrainProject/3.0 (algeria-transit)",
]

SCRAPNTF_API = "https://scrapntf.onrender.com/getAllStations/"
SNTF_PRICING = "https://www.sntf.dz/index.php/component/sntf/"

# Multiple codes may map to the same station name; keep the first (canonical) code.
STATION_CODE_MAP: dict[int, str] = {
    37:  "ALGER (AGHA)",
    126: "BOUIRA",
    305: "ORAN",
    90:  "BEJAIA",
    168: "CHLEF",
    114: "AIN DEFLA",
    71:  "AIN DEFLA",
    376: "SETIF",
    182: "CHLEF",
    134: "BOUMERDES",
    415: "THENIA",
    525: "SIDI ABD ALLAH",
    560: "AEROPORT HOUARI BOUMEDIENE",
    69:  "BEJAIA",
    251: "LAKHDARIA",
    13:  "TLEMCEN",
    8:   "BECHAR",
}

# Canonical (preferred) code per station name for pricing lookups
CANONICAL_CODES: dict[str, int] = {
    "ALGER (AGHA)": 37,
    "ORAN": 305,
    "BEJAIA": 90,
    "BOUIRA": 126,
    "SETIF": 376,
    "CHLEF": 168,
    "AIN DEFLA": 114,
    "LAKHDARIA": 251,
    "TLEMCEN": 13,
    "BECHAR": 8,
    "BOUMERDES": 134,
    "THENIA": 415,
    "SIDI ABD ALLAH": 525,
    "AEROPORT HOUARI BOUMEDIENE": 560,
}

BANLIEUE_LINES: list[dict] = [
    {
        "name": "Axe Central",
        "operator": "SNTF",
        "mode": "train",
        "color": "#1E88E5",
        "stops": ["Agha", "Ateliers", "Hussein Dey", "Caroubier", "El Harrach"],
    },
    {
        "name": "Banlieue Est",
        "operator": "SNTF",
        "mode": "train",
        "color": "#1E88E5",
        "stops": [
            "Agha", "Ateliers", "Hussein Dey", "Caroubier", "El Harrach",
            "Oued Smar", "Bab Ezzouar", "Dar El Beïda", "Rouïba",
            "Rouïba Industrielle", "Réghaïa", "Réghaïa Industrielle",
            "Boudouaou", "Corso", "Boumerdès", "Tidjelabine", "Thénia",
        ],
    },
    {
        "name": "Banlieue Ouest",
        "operator": "SNTF",
        "mode": "train",
        "color": "#E53935",
        "stops": [
            "Agha", "Ateliers", "Hussein Dey", "Caroubier", "El Harrach",
            "Gué de Constantine", "Aïn Naâdja", "Baba Ali", "Birtouta",
            "Tessala El Merdja", "Boufarik", "Beni Mered", "Blida",
            "Chiffa", "Mouzaia", "El Affroun",
        ],
    },
    {
        "name": "Ligne Zéralda",
        "operator": "SNTF",
        "mode": "train",
        "color": "#43A047",
        "stops": [
            "Agha", "Ateliers", "Hussein Dey", "Caroubier", "El Harrach",
            "Gué de Constantine", "Aïn Naâdja", "Baba Ali", "Birtouta",
            "Tessala El Merdja", "Sidi Abd Allah", "Sidi Abd Allah Université",
            "Zéralda",
        ],
    },
    {
        "name": "Ligne Aéroport",
        "operator": "SNTF",
        "mode": "train",
        "color": "#FB8C00",
        "stops": [
            "Agha", "Ateliers", "Hussein Dey", "Caroubier", "El Harrach",
            "Oued Smar", "Bab Ezzouar", "Aéroport Houari Boumediene",
        ],
    },
    {
        "name": "Thenia - Zéralda Direct",
        "operator": "SNTF",
        "mode": "train",
        "color": "#8E24AA",
        "stops": [
            "Thénia", "Tidjelabine", "Boumerdès", "Corso", "Boudouaou",
            "Réghaïa Industrielle", "Réghaïa", "Rouïba Industrielle",
            "Rouïba", "Dar El Beïda", "Bab Ezzouar", "Oued Smar",
            "Gué de Constantine", "Aïn Naâdja", "Baba Ali", "Birtouta",
            "Tessala El Merdja", "Sidi Abd Allah", "Sidi Abd Allah Université",
            "Zéralda",
        ],
    },
    {
        "name": "Constantine Banlieue Est",
        "operator": "SNTF",
        "mode": "train",
        "color": "#00ACC1",
        "stops": [
            "Constantine", "Bekira", "Hamma Bouziane", "Kef Salah",
            "Didouche Mourad", "Zighoud Youcef",
        ],
    },
    {
        "name": "Constantine Banlieue Ouest",
        "operator": "SNTF",
        "mode": "train",
        "color": "#00ACC1",
        "stops": [
            "Constantine", "Chalet des Pins", "Sidi Mabrouk",
            "Oued Hamimine", "El Khroub", "Ouled Rahmoune",
        ],
    },
    {
        "name": "Annaba Banlieue",
        "operator": "SNTF",
        "mode": "train",
        "color": "#7CB342",
        "stops": [
            "Annaba", "Boukhadra", "Sidi Achour", "El Bouni",
            "Chaiba", "Sidi Amar",
        ],
    },
    {
        "name": "Oran Banlieue",
        "operator": "SNTF",
        "mode": "train",
        "color": "#FFB300",
        "stops": [
            "Oran", "Hai El Sabah", "Garita", "Hassi Bounif",
        ],
    },
]

KNOWN_FARES: dict[tuple[str, str], tuple[int, int]] = {
    ("Alger (Agha)", "Oran"):              (1750, 1250),
    ("Alger (Agha)", "Bejaia"):            (1550, 1100),
    ("Alger (Agha)", "Bouira"):            (850,  600),
    ("Alger (Agha)", "Lakhdaria"):         (650,  460),
    ("Alger (Agha)", "Boumerdes"):         (250,  180),
    ("Alger (Agha)", "Setif"):             (1650, 1180),
    ("Oran", "Tlemcen"):                   (800,  570),
    ("Oran", "Bechar"):                    (1800, 1300),
    ("Bouira", "Bejaia"):                  (700,  500),
    ("Alger (Agha)", "Thenia"):            (300,  210),
    ("Alger (Agha)", "Aeroport"):          (200,  150),
    ("Bejaia", "Bouira"):                  (700,  500),
    ("Alger (Agha)", "Chlef"):             (1050, 750),
    ("Alger (Agha)", "Ain Defla"):         (650,  460),
    ("Oran", "Chlef"):                     (1200, 860),
    ("Setif", "Bouira"):                   (550,  390),
    ("Alger (Agha)", "Sidi Abd Allah"):    (120,  80),
    ("Bouira", "Lakhdaria"):              (300,  210),
    ("Oran", "Bejaia"):                   (2350, 1680),
    ("Oran", "Bouira"):                   (1600, 1150),
}

PRICING_ROUTES: list[dict] = [
    {"from_code": 37,  "to_code": 305, "from_name": "Alger (Agha)", "to_name": "Oran"},
    {"from_code": 37,  "to_code": 90,  "from_name": "Alger (Agha)", "to_name": "Bejaia"},
    {"from_code": 37,  "to_code": 126, "from_name": "Alger (Agha)", "to_name": "Bouira"},
    {"from_code": 37,  "to_code": 251, "from_name": "Alger (Agha)", "to_name": "Lakhdaria"},
    {"from_code": 37,  "to_code": 134, "from_name": "Alger (Agha)", "to_name": "Boumerdes"},
    {"from_code": 37,  "to_code": 376, "from_name": "Alger (Agha)", "to_name": "Setif"},
    {"from_code": 305, "to_code": 13,  "from_name": "Oran",         "to_name": "Tlemcen"},
    {"from_code": 305, "to_code": 8,   "from_name": "Oran",         "to_name": "Bechar"},
    {"from_code": 126, "to_code": 90,  "from_name": "Bouira",       "to_name": "Bejaia"},
    {"from_code": 37,  "to_code": 415, "from_name": "Alger (Agha)", "to_name": "Thenia"},
    {"from_code": 37,  "to_code": 560, "from_name": "Alger (Agha)", "to_name": "Aeroport"},
    {"from_code": 90,  "to_code": 126, "from_name": "Bejaia",       "to_name": "Bouira"},
    {"from_code": 37,  "to_code": 168, "from_name": "Alger (Agha)", "to_name": "Chlef"},
    {"from_code": 37,  "to_code": 71,  "from_name": "Alger (Agha)", "to_name": "Ain Defla"},
    {"from_code": 37,  "to_code": 69,  "from_name": "Alger (Agha)", "to_name": "Bejaia"},
    {"from_code": 37,  "to_code": 114, "from_name": "Alger (Agha)", "to_name": "Ain Defla"},
    {"from_code": 305, "to_code": 168, "from_name": "Oran",         "to_name": "Chlef"},
    {"from_code": 376, "to_code": 126, "from_name": "Setif",        "to_name": "Bouira"},
    {"from_code": 126, "to_code": 251, "from_name": "Bouira",       "to_name": "Lakhdaria"},
    {"from_code": 37,  "to_code": 182, "from_name": "Alger (Agha)", "to_name": "Chlef"},
    {"from_code": 305, "to_code": 90,  "from_name": "Oran",         "to_name": "Bejaia"},
    {"from_code": 37,  "to_code": 525, "from_name": "Alger (Agha)", "to_name": "Sidi Abd Allah"},
    {"from_code": 305, "to_code": 126, "from_name": "Oran",         "to_name": "Bouira"},
]


def _ua() -> str:
    return random.choice(USER_AGENTS)


def _req(url: str, timeout: int = 4) -> dict | list | None:
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout), "-A", _ua(), url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        return None


def fetch_scrapntf_stations() -> dict[int, str]:
    log("=== Fetching ScrapNTF station IDs ===")
    log(f"  GET {SCRAPNTF_API}")
    data = _req(SCRAPNTF_API)
    station_codes: dict[int, str] = {}

    if data is None:
        log("  ERROR: Could not reach ScrapNTF API. Using known code map.")
        return dict(STATION_CODE_MAP)

    if isinstance(data, dict):
        items = list(data.items())
    elif isinstance(data, list):
        items = []
        for entry in data:
            if isinstance(entry, dict):
                items.extend(entry.items())
            elif isinstance(entry, list):
                items.append(("", entry))
            else:
                items.append(("", entry))
    else:
        log(f"  Unexpected data type: {type(data)}")
        return dict(STATION_CODE_MAP)

    log(f"  Got {len(items)} entries from API")
    seen: set[int] = set()
    for key, val in items:
        name_part = str(val if val else "").strip()
        code_part = str(key if key else "").strip()
        try:
            code = int(code_part)
        except ValueError:
            try:
                code = int(name_part)
                name_part = code_part
            except ValueError:
                continue
        if code in seen:
            continue
        seen.add(code)
        name = name_part.upper().strip()
        station_codes[code] = name

    for code, name in STATION_CODE_MAP.items():
        if code not in station_codes:
            station_codes[code] = name

    return station_codes


def fetch_pricing(
    from_code: int, to_code: int, from_name: str, to_name: str,
) -> dict:
    params = {
        "dd": "20251201",
        "ga": str(from_code),
        "gd": str(to_code),
        "h": "7189,7199",
        "h1": "0000",
        "h2": "2359",
        "o": "hd",
        "view": "tarification",
    }
    url = f"{SNTF_PRICING}?{urllib.parse.urlencode(params)}"
    route_label = f"{from_name} -> {to_name} (ga={from_code} -> gd={to_code})"
    log(f"  GET {route_label}")

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "4", "-A", _ua(),
             "-H", "Accept: application/json,text/html,*/*",
             "-H", "Accept-Language: fr,en;q=0.9",
             url],
            capture_output=True, text=True, timeout=8,
        )
        if result.returncode != 0 or not result.stdout.strip():
            log(f"    Failed (curl exit={result.returncode})")
            return {"from_code": from_code, "to_code": to_code, "from": from_name, "to": to_name}
        body = result.stdout
    except subprocess.TimeoutExpired:
        log("    Failed (timeout)")
        return {"from_code": from_code, "to_code": to_code, "from": from_name, "to": to_name}

    first_class = None
    second_class = None

    try:
        data = json.loads(body)
        if isinstance(data, list):
            for entry in data:
                if isinstance(entry, dict):
                    cls = entry.get("classe", "")
                    prix = entry.get("prix") or entry.get("price") or entry.get("Prix")
                    if prix is not None:
                        try:
                            val = float(prix)
                        except (ValueError, TypeError):
                            val = None
                        if "1" in str(cls):
                            if first_class is None:
                                first_class = val
                        elif "2" in str(cls):
                            if second_class is None:
                                second_class = val
        elif isinstance(data, dict):
            for cls_key in ("1", "2", "first", "second", "1ère", "2ème", "first_class", "second_class"):
                val = data.get(cls_key)
                if val is not None:
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        continue
                    if cls_key in ("1", "first", "1ère", "first_class"):
                        if first_class is None:
                            first_class = val
                    elif cls_key in ("2", "second", "2ème", "second_class"):
                        if second_class is None:
                            second_class = val
    except json.JSONDecodeError:
        html = body.lower()
        price_pattern = re.compile(
            r"(?:premi.?re|1[èe]re?|1re|first)[^\d]*?(\d[\d\s,.]*)\s*(?:da|dzd|dinars?)?",
            re.IGNORECASE,
        )
        m1 = price_pattern.search(html)
        if m1:
            raw = m1.group(1).replace(" ", "")
            try:
                first_class = float(raw.replace(",", "."))
            except ValueError:
                pass

        price_pattern2 = re.compile(
            r"(?:deuxi.?me|2[èe]me?|2me|second)[^\d]*?(\d[\d\s,.]*)\s*(?:da|dzd|dinars?)?",
            re.IGNORECASE,
        )
        m2 = price_pattern2.search(html)
        if m2:
            raw = m2.group(1).replace(" ", "")
            try:
                second_class = float(raw.replace(",", "."))
            except ValueError:
                pass

        if first_class is None:
            all_nums = re.findall(r"(\d[\d\s,.]*)\s*(?:da|dzd|dinars?)", html)
            if len(all_nums) >= 2:
                try:
                    first_class = float(all_nums[0].replace(" ", "").replace(",", "."))
                    second_class = float(all_nums[1].replace(" ", "").replace(",", "."))
                except ValueError:
                    pass

    result: dict = {
        "from": from_name,
        "to": to_name,
        "from_code": from_code,
        "to_code": to_code,
    }
    if first_class is not None:
        result["first_class"] = round(first_class)
    if second_class is not None:
        result["second_class"] = round(second_class)

    status = f"1ere={first_class} DZD" if first_class else "1ere=?"
    status += f", 2eme={second_class} DZD" if second_class else ", 2eme=?"
    log(f"    -> {status}")

    return result


def log(msg: str) -> None:
    print(msg, flush=True)


def main() -> None:
    station_codes = fetch_scrapntf_stations()
    log(f"  Total station codes mapped: {len(station_codes)}")

    log("\n=== Fetching pricing data ===")
    pricing_results: list[dict] = []
    for i, route in enumerate(PRICING_ROUTES, 1):
        sys.stdout.write(f"  [{i}/{len(PRICING_ROUTES)}] ")
        sys.stdout.flush()
        result = fetch_pricing(
            route["from_code"],
            route["to_code"],
            route["from_name"],
            route["to_name"],
        )
        pricing_results.append(result)
        time.sleep(0.5)

    for r in pricing_results:
        if "first_class" not in r and "second_class" not in r:
            key = (r["from"], r["to"])
            rev = (r["to"], r["from"])
            if key in KNOWN_FARES:
                r["first_class"], r["second_class"] = KNOWN_FARES[key]
                log(f"    [fallback] {r['from']} -> {r['to']}: 1ere={KNOWN_FARES[key][0]}, 2eme={KNOWN_FARES[key][1]}")
            elif rev in KNOWN_FARES:
                r["first_class"], r["second_class"] = KNOWN_FARES[rev]
                log(f"    [fallback] {r['from']} -> {r['to']}: 1ere={KNOWN_FARES[rev][0]}, 2eme={KNOWN_FARES[rev][1]}")

    # Deduplicate: keep the canonical code for each station name
    name_to_code: dict[str, int] = {}
    seen_names: set[str] = set()
    for code, name in sorted(station_codes.items()):
        if name in seen_names:
            continue
        seen_names.add(name)
        canonical = CANONICAL_CODES.get(name)
        name_to_code[name] = canonical if canonical is not None else code
    # Ensure all canonical codes are present
    for name, code in CANONICAL_CODES.items():
        if name not in name_to_code:
            name_to_code[name] = code

    output: dict = {
        "station_codes": name_to_code,
        "banlieue_lines": BANLIEUE_LINES,
        "pricing": pricing_results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    log(f"\nOutput written to {OUTPUT_PATH}")

    total_banlieue_stops = sum(len(line["stops"]) for line in BANLIEUE_LINES)
    routes_with_prices = sum(
        (1 for r in pricing_results if "first_class" in r or "second_class" in r),
    )

    log(f"\n{'=' * 60}")
    log("SUMMARY")
    log(f"{'=' * 60}")
    log(f"Station codes mapped:     {len(station_codes)}")
    log(f"Banlieue lines:           {len(BANLIEUE_LINES)}")
    log(f"Total stops across lines: {total_banlieue_stops}")
    log(f"Pricing routes fetched:   {len(pricing_results)} ({routes_with_prices} with prices)")
    log("")


if __name__ == "__main__":
    main()
