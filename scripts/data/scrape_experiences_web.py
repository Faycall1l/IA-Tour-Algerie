#!/usr/bin/env python3
"""
Scrape real Algerian tourism experiences from online sources (travel blogs,
event calendars, news articles). Adds them with source='scraped' + source_url.

Sources:
  1. Likizo Travel Blog — festivals calendar
  2. Algeria.com — national events & holidays
  3. ThingstoDoinAlgiers.com — Algiers events

Tracks scraped URLs to avoid re-importing duplicates.
"""

import json
import os
import re
import sys
import time
import uuid
from datetime import date, datetime
from html.parser import HTMLParser

import httpx
import psycopg2
from psycopg2.extras import execute_values

DB_DSN = os.getenv("DATABASE_URL", "postgresql://athar:athar_pass@localhost:5434/athar_db")
USER_AGENT = "ATHAR-Tourism/1.0 (faycal@athar.dz)"
CHECKPOINT_FILE = "scripts/data/.scraped_urls.json"

WILAYA_KEYWORDS = {
    "adrar": 1, "chlef": 2, "laghouat": 3, "oum el bouaghi": 4,
    "batna": 5, "béjaïa": 6, "bejaia": 6, "biskra": 7, "béchar": 8,
    "bechar": 8, "blida": 9, "bouira": 10, "tamanrasset": 11, "tébessa": 12,
    "tebessa": 12, "tlemcen": 13, "tiaret": 14, "tizi ouzou": 15, "alger": 16,
    "algiers": 16, "alger centre": 16, "djelfa": 17, "jijel": 18, "sétif": 19,
    "setif": 19, "saïda": 20, "saida": 20, "skikda": 21, "sidi bel abbès": 22,
    "annaba": 23, "guelma": 24, "constantine": 25, "médéa": 26, "medea": 26,
    "mostaganem": 27, "m'sila": 28, "msila": 28, "mascara": 29, "ouargla": 30,
    "oran": 31, "oranie": 31, "el bayadh": 32, "illizi": 33,
    "bordj bou arréridj": 34, "boumerdès": 35, "boumerdes": 35,
    "el tarf": 36, "tindouf": 37, "tissemsilt": 38, "el oued": 39,
    "khenchela": 40, "souk ahras": 41, "tipaza": 42, "mila": 43,
    "aïn defla": 44, "ain defla": 44, "naâma": 45, "naama": 45,
    "aïn témouchent": 46, "ain temouchent": 46, "ghardaïa": 47, "ghardaia": 47,
    "relizane": 48, "timimoun": 49, "béni abbès": 50, "beni abbes": 50,
    "aïn salah": 51, "ain salah": 51, "aïn guezzam": 52, "ain guezzam": 52,
    "touggourt": 53, "djanet": 54, "el m'ghair": 55, "el mghair": 55,
    "el meniaa": 56, "ouled djellal": 57, "bordj badji mokhtar": 58,
    "aflou": 59, "el abiodh sidi cheikh": 60, "el aricha": 61,
    "el kantara": 62, "barika": 63, "bou saâda": 64, "bou saada": 64,
    "bir el ater": 65, "ksar el boukhari": 66, "ksar chellala": 67,
    "aïn oussera": 68, "ain oussera": 68, "messaad": 69,
    "kabylie": 15, "kabylia": 15, "djurdjura": 15, "hoggar": 11,
    "tassili": 33, "sahara": 11, "mzab": 47, "aurès": 5, "aures": 5,
}

CATEGORY_KEYWORDS = {
    "tour": ["circuit", "tour", "visite", "excursion", "balade", "découverte", "city tour"],
    "hiking": ["randonnée", "trek", "sentier", "balade nature", "randonnee"],
    "cultural": ["festival", "musée", "musee", "patrimoine", "culturel", "spectacle",
                 "concert", "exposition", "tradition", "artisanat", "cérémonie"],
    "food": ["gastronomique", "cuisine", "dégustation", "déguster", "marché",
             "saveurs", "culinaire", "repas", "plat"],
    "adventure": ["aventure", "expédition", "4x4", "escalade", "sport",
                  "désert", "montagne", "ski", "parapente"],
    "wellness": ["bien-être", "spa", "hammam", "thermal", "détente", "yoga", "massage"],
}

MONTHS_FR = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
}
MONTHS_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def load_scraped():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return set(json.load(f))
    return set()


def save_scraped(urls):
    os.makedirs(os.path.dirname(CHECKPOINT_FILE), exist_ok=True)
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(sorted(urls), f, indent=2)


def guess_wilaya(text):
    text_lower = text.lower()
    for keyword, wid in WILAYA_KEYWORDS.items():
        if keyword in text_lower:
            return wid
    return None


def guess_category(text):
    text_lower = text.lower()
    scores = {}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        score = sum(2 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[cat] = score
    if scores:
        return max(scores, key=scores.get)
    return "cultural"


def guess_season(month):
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"


def parse_date_fr(text):
    """Try to extract a date from French text."""
    for month_name, month_num in MONTHS_FR.items():
        m = re.search(r"(\d+)[ers]{0,2}\s+" + month_name, text, re.IGNORECASE)
        if m:
            return date(2026, month_num, int(m.group(1)))
    for month_name, month_num in MONTHS_FR.items():
        if month_name in text.lower():
            m = re.search(month_name + r"\s+(\d{4})", text, re.IGNORECASE)
            return date(2026, month_num, 1)
    return None


def parse_date_en(text):
    for month_name, month_num in MONTHS_EN.items():
        m = re.search(month_name + r"\s+(\d{1,2})", text, re.IGNORECASE)
        if m:
            return date(2026, month_num, int(m.group(1)))
    return None


def fetch_url(url):
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"  [red]Error fetching {url}: {e}[/]")
        return None


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return " ".join(self.text)


def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_text()


def extract_likizo(html):
    """Extract festivals from Likizo Travel Blog page."""
    items = []
    text = strip_html(html)
    # Each festival is typically a heading followed by description
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    current_title = None
    current_desc = []
    for line in lines:
        if len(line) < 100 and line[0].isupper() and any(kw in line for kw in ["Festival", "Celebration", "Fest", "Camel", "Film", "Music", "Rai", "Jazz", "Date"]):
            if current_title and current_desc:
                items.append((current_title, " ".join(current_desc)[:300]))
            current_title = line
            current_desc = []
        elif current_title and len(line) > 10:
            current_desc.append(line)
    if current_title and current_desc:
        items.append((current_title, " ".join(current_desc)[:300]))
    return items


def extract_algeriacom(html):
    """Extract events from Algeria.com"""
    items = []
    text = strip_html(html)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines:
        if "Day" in line or "Festival" in line or "Celebration" in line:
            if len(line) > 3 and len(line) < 120:
                items.append((line, ""))
    return items


def extract_algiers_events(html):
    """Extract events from thingstodoinalgiers.com"""
    items = []
    text = strip_html(html)
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 3]
    for i, line in enumerate(lines):
        clean = re.sub(r'[^\w\sàâäéèêëîïôöùûüç\'\-\(\)]', '', line).strip()
        if len(clean) < 3:
            continue
        if any(kw in line for kw in ["Festival", "Fest", "Concert", "Marathon", "Souq",
                                       "Exhibition", "Market", "Fair", "Parade",
                                       "Biennale", "Nuit", "Salon", "Fête", "Foire",
                                       "Film", "Music", "Dance", "Theatre"]):
            if len(line) < 150:
                desc = lines[i + 1].strip() if i + 1 < len(lines) else ""
                items.append((clean, desc[:300]))
    return items


def extract_lexpress(html):
    """Extract events from L'Express Algérie article."""
    items = []
    text = strip_html(html)
    lines = [l.strip() for l in text.split("\n") if l.strip() and len(l.strip()) > 10]
    for i, line in enumerate(lines):
        if any(kw in line for kw in ["Festival", "concert", "spectacle", "Fest",
                                       "programmation", "rendez-vous"]):
            if len(line) < 200:
                desc = lines[i + 1].strip()[:300] if i + 1 < len(lines) else ""
                items.append((line, desc))
    return items


SOURCES = [
    {
        "name": "Likizo Travel Blog",
        "url": "https://www.likizotravelblog.com/blogs/festivals-in-algeria-best-events",
        "extract": extract_likizo,
    },
    {
        "name": "Algeria.com Events",
        "url": "https://www.algeria.com/events/",
        "extract": extract_algeriacom,
    },
    {
        "name": "ThingsToDoInAlgiers",
        "url": "https://thingstodoinalgiers.com/events/",
        "extract": extract_algiers_events,
    },
    {
        "name": "L'Express Algérie",
        "url": "https://www.lexpressquotidien.dz/2026/07/01/concerts-festivals-et-spectacles-un-ete-riche-en-rendez-vous-culturels-dans-la-capitale/",
        "extract": extract_lexpress,
    },
    {
        "name": "Algerian Radio News",
        "url": "https://news.radioalgerie.dz/en/node/90055",
        "extract": extract_lexpress,
    },
]


def main():
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor()

    # Fetch provider
    cur.execute("SELECT id FROM users WHERE phone = '+213500000001'")
    guide_row = cur.fetchone()
    cur.execute("SELECT id FROM users WHERE phone = '+213500000002'")
    agency_row = cur.fetchone()
    provider_id = (guide_row or agency_row)
    if not provider_id:
        print("ERROR: No provider users found. Run seed_providers.py first.")
        sys.exit(1)
    provider_id = provider_id[0]

    # Fetch existing wilayas
    cur.execute("SELECT id FROM wilayas")
    existing_wilayas = {row[0] for row in cur.fetchall()}

    # Fetch existing titles to avoid exact dupes
    cur.execute("SELECT title FROM experiences")
    existing_titles = {row[0].strip().lower() for row in cur.fetchall()}

    # Load scraped URLs checkpoint
    scraped_urls = load_scraped()
    print(f"Already scraped: {len(scraped_urls)} URLs")

    scraped_this_run = set(scraped_urls)
    experiences = []
    skipped = 0

    def add_experience(title, desc, wilaya, source_url, is_date_event=False):
        nonlocal skipped
        key = title.strip().lower()
        if key in existing_titles:
            skipped += 1
            return
        wid = guess_wilaya(f"{title} {desc}")
        if not wid and wilaya:
            wid = wilaya
        if not wid or wid not in existing_wilayas:
            wid = 16  # default to Algiers if can't determine
        if wid not in existing_wilayas:
            skipped += 1
            return
        cat = guess_category(f"{title} {desc}")
        existing_titles.add(key)

        season = None
        sd, ed = None, None
        if is_date_event:
            parsed = parse_date_fr(desc) or parse_date_en(desc) or parse_date_fr(title)
            if parsed:
                season = guess_season(parsed.month)
                sd = parsed.isoformat()
                ed = parsed.isoformat()

        experiences.append((
            uuid.uuid4(), provider_id, cat, title, desc[:500], wid,
            f"Alger centre" if wid == 16 else f"{wid} centre",
            1200, 3, 30,  # default price, dur, max_p
            "FR", None, None, "active",
            season, sd, ed,
            "scraped", source_url, False, 0,
        ))

    for source in SOURCES:
        name = source["name"]
        url = source["url"]
        if url in scraped_urls:
            print(f"[dim]Skipping {name} (already scraped)[/]")
            continue

        print(f"Fetching {name}...", end=" ")
        html = fetch_url(url)
        if not html:
            continue

        items = source["extract"](html)
        print(f"{len(items)} items found")

        for title, desc in items:
            add_experience(title, desc, None, url, is_date_event=True)

        scraped_this_run.add(url)

    # Insert
    if not experiences:
        print("\nNo new experiences to insert.")
        save_scraped(scraped_this_run)
        conn.close()
        return

    insert_sql = """
        INSERT INTO experiences
            (id, provider_id, category, title, description, wilaya_id,
             meeting_point, price_dzd, duration_hours, max_participants,
             language, included, what_to_bring, status,
             season, start_date, end_date,
             source, source_url, is_verified, completion_count)
        VALUES %s
    """
    rows = []
    for e in experiences:
        rows.append((
            str(e[0]), str(e[1]), e[2], e[3], e[4], e[5],
            e[6], e[7], e[8], e[9],
            e[10], e[11], e[12], e[13],
            e[14], e[15], e[16],
            e[17], e[18], e[19], e[20],
        ))

    try:
        execute_values(cur, insert_sql, rows, page_size=100)
        conn.commit()
        print(f"\nInserted {len(rows)} scraped experiences (+{skipped} skipped dupes)")

        cur.execute("SELECT source_url, COUNT(*) FROM experiences WHERE source='scraped' GROUP BY source_url")
        for url, cnt in cur.fetchall():
            print(f"  {url}: {cnt}")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        save_scraped(scraped_this_run)
        cur.close()
        conn.close()
        print(f"Checkpoint saved: {len(scraped_this_run)} URLs")


if __name__ == "__main__":
    main()
