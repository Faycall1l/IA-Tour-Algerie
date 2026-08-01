#!/usr/bin/env python3
"""Fetch Wikivoyage destination descriptions for all Algerian wilayas (batch API with retry)."""

import json
import re
import time
import random
import urllib.request
import urllib.parse
import urllib.error
import psycopg2

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "dbname": "athar_db", "user": "athar", "password": "athar_pass",
}

WIKIVOYAGE_API = "https://fr.wikivoyage.org/w/api.php"
USER_AGENT = "ATHAR-Tourism/1.0 (data enrichment bot - bayrem.aymen@univ-usto.dz)"

FR_PAGE_MAP = {
    "Adrar": "Adrar",
    "Chlef": "Chlef",
    "Laghouat": "Laghouat",
    "Oum El Bouaghi": "Oum El Bouaghi",
    "Batna": "Batna",
    "Béjaïa": "Béjaïa",
    "Biskra": "Biskra",
    "Béchar": "Béchar",
    "Blida": "Blida",
    "Bouira": "Bouira",
    "Tamanrasset": "Tamanrasset",
    "Tébessa": "Tébessa",
    "Tlemcen": "Tlemcen",
    "Tiaret": "Tiaret",
    "Tizi Ouzou": "Tizi Ouzou",
    "Alger": "Alger",
    "Djelfa": "Djelfa",
    "Jijel": "Jijel",
    "Sétif": "Sétif",
    "Saïda": "Saïda",
    "Skikda": "Skikda",
    "Sidi Bel Abbès": "Sidi Bel Abbès",
    "Annaba": "Annaba",
    "Guelma": "Guelma",
    "Constantine": "Constantine",
    "Médéa": "Médéa",
    "Mostaganem": "Mostaganem",
    "M'Sila": "M'Sila",
    "Mascara": "Mascara",
    "Ouargla": "Ouargla",
    "Oran": "Oran",
    "El Bayadh": "El Bayadh",
    "Illizi": "Illizi",
    "Bordj Bou Arréridj": "Bordj Bou Arréridj",
    "Boumerdès": "Boumerdès",
    "El Tarf": "El Tarf",
    "Tindouf": "Tindouf",
    "Tissemsilt": "Tissemsilt",
    "El Oued": "El Oued",
    "Khenchela": "Khenchela",
    "Souk Ahras": "Souk Ahras",
    "Tipaza": "Tipaza",
    "Mila": "Mila",
    "Aïn Defla": "Aïn Defla",
    "Naâma": "Naâma",
    "Aïn Témouchent": "Aïn Témouchent",
    "Ghardaïa": "Ghardaïa",
    "Relizane": "Relizane",
    "Timimoun": "Timimoun",
    "Béni Abbès": "Béni Abbès",
    "Aïn Salah": "Aïn Salah",
    "Aïn Guezzam": "Aïn Guezzam",
    "Touggourt": "Touggourt",
    "Djanet": "Djanet",
    "El M'Ghair": "El M'Ghair",
    "El Meniaa": "El Meniaa",
    "Ouled Djellal": "Ouled Djellal",
    "Bordj Badji Mokhtar": "Bordj Badji Mokhtar",
}

EN_PAGE_MAP = {
    "Alger": "Algiers", "Oran": "Oran", "Constantine": "Constantine",
    "Annaba": "Annaba", "Tlemcen": "Tlemcen", "Béjaïa": "Béjaïa",
    "Tizi Ouzou": "Tizi Ouzou", "Sétif": "Sétif", "Batna": "Batna",
    "Biskra": "Biskra", "Tébessa": "Tébessa", "Djelfa": "Djelfa",
    "Blida": "Blida", "Ghardaïa": "Ghardaïa", "Ouargla": "Ouargla",
    "Tamanrasset": "Tamanrasset",
}


def api_call(api_url, params, retries=5):
    """Make API call with exponential backoff on 429."""
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        url = f"{api_url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = (2 ** attempt) + random.random() * 3
                print(f"    429 rate limit, waiting {wait:.0f}s...")
                time.sleep(wait)
                continue
            print(f"    HTTP {e.code}: {e.reason}")
            return None
        except Exception as e:
            print(f"    error: {e}")
            return None
    return None


def batch_extract(titles, lang="fr"):
    """Fetch extracts for multiple pages in one API call."""
    if lang == "fr":
        api = WIKIVOYAGE_API
    else:
        api = "https://en.wikivoyage.org/w/api.php"
    
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "titles": "|".join(titles),
        "format": "json",
        "redirects": 1,
    }
    data = api_call(api, params)
    if not data:
        return {}
    pages = data.get("query", {}).get("pages", {})
    results = {}
    for pid, page in pages.items():
        if pid != "-1":
            title = page.get("title", "")
            extract = page.get("extract", "")
            extract = re.sub(r'\n{3,}', '\n\n', extract).strip()
            if extract:
                results[title] = extract
    return results


def main():
    print("=== Wikivoyage Destination Enrichment ===\n")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Add columns if missing
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='wilayas' AND column_name='description'""")
    if not cur.fetchone():
        cur.execute("ALTER TABLE wilayas ADD COLUMN description TEXT")
        cur.execute("ALTER TABLE wilayas ADD COLUMN description_en TEXT")
        conn.commit()
        print("Added description columns to wilayas\n")

    # Fetch all wilayas
    cur.execute("SELECT id, name_fr FROM wilayas ORDER BY id")
    wilayas = cur.fetchall()
    print(f"Wilayas to enrich: {len(wilayas)}\n")

    # Batch into groups of 10 (API limit)
    batch_size = 10
    en_success = 0
    fr_success = 0

    for i in range(0, len(wilayas), batch_size):
        batch = wilayas[i:i + batch_size]
        titles = []
        for wid, name_fr in batch:
            t = FR_PAGE_MAP.get(name_fr, name_fr)
            titles.append(t)
        
        print(f"Batch {i//batch_size + 1}/{(len(wilayas)//batch_size)+1}: {', '.join(titles[:5])}...")
        
        # FR batch
        fr_results = batch_extract(titles)
        
        for wid, name_fr in batch:
            title = FR_PAGE_MAP.get(name_fr, name_fr)
            
            # Check FR result
            extract = fr_results.get(title) or fr_results.get(f"Algérie/{title}")
            if extract:
                cur.execute("UPDATE wilayas SET description = %s WHERE id = %s", (extract[:5000], wid))
                fr_success += 1
                print(f"  [{wid:2d}] {name_fr}: FR ✓ ({len(extract)} chars)")

            # EN fallback
            en_title = EN_PAGE_MAP.get(name_fr)
            if en_title and not extract:
                time.sleep(1)
                en_results = batch_extract([en_title], lang="en")
                en_extract = en_results.get(en_title) or en_results.get(f"Algeria/{en_title}")
                if en_extract:
                    cur.execute("UPDATE wilayas SET description_en = %s WHERE id = %s", (en_extract[:5000], wid))
                    en_success += 1
                    print(f"  [{wid:2d}] {name_fr}: EN ✓ ({len(en_extract)} chars)")
            
            if not extract:
                print(f"  [{wid:2d}] {name_fr}: ✗ no description found")

        conn.commit()
        # Long delay between batches to respect rate limits
        if i + batch_size < len(wilayas):
            wait = 8 + random.random() * 4
            print(f"  waiting {wait:.0f}s...\n")
            time.sleep(wait)

    conn.close()
    print(f"\nDone: FR={fr_success}, EN={en_success} / {len(wilayas)} wilayas")


if __name__ == "__main__":
    main()
