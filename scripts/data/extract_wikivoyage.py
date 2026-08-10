#!/usr/bin/env python3
"""Extract Wikivoyage FR Algerian destination pages into POI/stay/food records.

Parses the bz2 XML multistream dump and pulls entries from sections:
  Voir / A voir / Sites / Lieux → POIs
  À faire / Activités → experiences/POIs
  Où manger / Restaurants → food
  Où dormir / Hébergement → stays

Output unified stage records:
- scripts/data/raw/wikivoyage_fr_pois.json
- scripts/data/raw/wikivoyage_fr_food.json
- scripts/data/raw/wikivoyage_fr_stays.json

Wikivoyage is CC BY-SA, factual listings — a "gray but legal" public source.
"""

import bz2
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "scripts" / "data" / "raw"
DUMP = RAW / "frwikivoyage-20260801-pages-articles-multistream.xml.bz2"

WILAYA_PAGES = {
    "Adrar": "01", "Aflou": "03", "Ain Defla": "44", "Ain Oussera": "66",
    "Ain Temouchent": "46", "Alger": "16", "Annaba": "23", "Barika": "05",
    "Batna": "05", "Béchar": "08", "Béjaïa": "06", "Biskra": "07",
    "Blida": "09", "Bordj Badji Mokhtar": "50", "Bordj Bou Arreridj": "34",
    "Bouira": "10", "Boumerdès": "35", "Bou Saâda": "28", "Chlef": "02",
    "Constantine": "25", "Djanet": "56", "Djelfa": "17", "El Bayadh": "32",
    "El Meniaa": "58", "El Oued": "39", "El Tarf": "36", "Ghardaïa": "47",
    "Guelma": "24", "Hassi Messaoud": "30", "Illizi": "33", "In Guezzam": "54",
    "In Salah": "53", "Jijel": "18", "Khenchela": "40", "Laghouat": "03",
    "Mascara": "29", "Médéa": "26", "Mila": "43", "Mostaganem": "27",
    "M'Sila": "28", "Naâma": "45", "Oran": "31", "Ouargla": "30",
    "Oum el Bouaghi": "04", "Relizane": "48", "Saida": "20", "Sétif": "19",
    "Sidi Bel Abbes": "22", "Skikda": "21", "Souk Ahras": "41",
    "Tamanrasset": "11", "Tébessa": "12", "Tiaret": "14", "Tindouf": "37",
    "Tipaza": "42", "Tissemsilt": "38", "Tizi Ouzou": "15", "Tlemcen": "13",
    "Touggourt": "55", "Timimoun": "01",
    # regional / practical
    "Sahara algérien": "11", "Algérie": None, "Centre de l'Algérie": None,
    "Patrimoine mondial en Algérie": None,
}

SECTION_RE = re.compile(r"(?mi)^\s*(?:==+|\*\*)\s*(Voir|A voir|Sites|Lieux|Monuments|À faire|Activités|Où manger|Restaurants|Où dormir|Hébergement|Se loger)\s*(?:==+|\*\*)?\s*$")
LIST_RE = re.compile(r"^\*\s*(.+)$", re.MULTILINE)


def parse_page(title: str, text: str):
    """Yield records from a Wikivoyage page."""
    wilaya_code = WILAYA_PAGES.get(title)
    if wilaya_code is None and title.startswith("Alger ("):
        wilaya_code = "16"
    if wilaya_code is None:
        return
    # normalize text
    text = re.sub(r"\{\{[^}]+\}\}", "", text)
    # split by section headers
    parts = SECTION_RE.split(text)
    if not parts:
        return
    records = {"pois": [], "food": [], "stays": []}
    current = None
    for part in parts:
        low = part.strip().lower()
        if low in {"voir", "a voir", "sites", "lieux", "monuments"}:
            current = "pois"
        elif low in {"à faire", "activités"}:
            current = "pois"
        elif low in {"où manger", "restaurants"}:
            current = "food"
        elif low in {"où dormir", "hébergement", "se loger"}:
            current = "stays"
        elif current:
            for line in LIST_RE.findall(part):
                name = line.strip(" -*")
                # strip wikitext links [[...|...]]
                name = re.sub(r"\[\[[^\]|]+\|([^\]]+)\]\]", r"\1", name)
                name = re.sub(r"\[\[([^\]]+)\]\]", r"\1", name)
                name = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", name)
                name = name.split("—")[0].split(".")[0].strip()
                if len(name) < 3 or name.lower().startswith("voir"):
                    continue
                # crude coord extraction from text
                lat = lon = None
                m = re.search(r"(\d{1,2})°\s*(\d{1,2})'\s*([\d.]+)\"?\s*([NS])\s*[;,/]?\s*(\d{1,3})°\s*(\d{1,2})'\s*([\d.]+)\"?\s*([EO])", line)
                if m:
                    lat = int(m.group(1)) + int(m.group(2))/60 + float(m.group(3))/3600
                    if m.group(4) == 'S': lat = -lat
                    lon = int(m.group(5)) + int(m.group(6))/60 + float(m.group(7))/3600
                    if m.group(8) == 'O': lon = -lon
                rec = {
                    "source": "wikivoyage-fr",
                    "source_id": f"{title}/{name[:60]}",
                    "name_fr": name,
                    "name_ar": None,
                    "name_en": None,
                    "wilaya_code": wilaya_code,
                    "description": line.strip(),
                    "rating": None,
                    "num_reviews": None,
                    "photo_urls": [],
                    "verified_at": "2026-08-01",
                    "url": f"https://fr.wikivoyage.org/wiki/{title.replace(' ', '_')}",
                    "refs": {"wikivoyage": title},
                }
                if lat is not None:
                    rec["lat"] = lat
                    rec["lng"] = lon
                if current == "pois":
                    rec["category"] = "cultural"
                    rec["subtype"] = "wikivoyage"
                    rec["purpose"] = "user"
                    records["pois"].append(rec)
                elif current == "food":
                    rec["category"] = "restaurant"
                    rec["subtype"] = "restaurant"
                    rec["purpose"] = "user"
                    records["food"].append(rec)
                elif current == "stays":
                    rec["type"] = "hotel"
                    rec["subtype"] = "wikivoyage"
                    rec["purpose"] = "stays"
                    records["stays"].append(rec)
    return records


def main() -> int:
    if not DUMP.exists():
        print(f"missing {DUMP}")
        return 1
    pois, food, stays = [], [], []
    pages = 0
    with bz2.open(DUMP, "rt", encoding="utf-8", errors="replace") as f:
        title = text = ""
        in_text = False
        for line in f:
            if "<title>" in line:
                t = re.sub(r".*<title>(.*)</title>.*", r"\1", line.strip())
                if title and title in WILAYA_PAGES:
                    recs = parse_page(title, text)
                    if recs:
                        pois.extend(recs["pois"])
                        food.extend(recs["food"])
                        stays.extend(recs["stays"])
                        pages += 1
                title, text = t, ""
                in_text = False
            elif "<text" in line:
                in_text = True
                text += re.sub(r".*<text[^>]*>", "", line)
            elif "</text>" in line:
                in_text = False
                text += re.sub(r"</text>.*", "", line)
            elif in_text:
                text += line
        # last page
        if title and title in WILAYA_PAGES:
            recs = parse_page(title, text)
            if recs:
                pois.extend(recs["pois"])
                food.extend(recs["food"])
                stays.extend(recs["stays"])
                pages += 1
    (RAW / "wikivoyage_fr_pois.json").write_text(
        json.dumps(pois, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "wikivoyage_fr_food.json").write_text(
        json.dumps(food, ensure_ascii=False), encoding="utf-8"
    )
    (RAW / "wikivoyage_fr_stays.json").write_text(
        json.dumps(stays, ensure_ascii=False), encoding="utf-8"
    )
    print(f"parsed {pages} pages -> pois={len(pois)} food={len(food)} stays={len(stays)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())