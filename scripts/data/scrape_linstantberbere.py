#!/usr/bin/env python3
"""Scrape artisan creator bios from linstantberbere.com (Maghreb marketplace).

Each /createur-artisan/<slug>/ page is a WooCommerce product archive with a
short bio (creator name, craft, and usually a location like "Basée à Fès
(Maroc)" or "artisan d'Alger"). We extract the bio text and record which
artisans are Algerian (wilaya/city mention) vs elsewhere (Morocco, Tunisia,
France...) — only the Algerian ones feed the ATHAR corpus.

Every record keeps source='linstantberbere' + source_url for verification.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "scripts" / "data"))

from data.scrape_utils import Checkpointer, PoliteFetcher, scrape_text  # noqa: E402

BASE = "https://linstantberbere.com"
SITEMAP = "https://linstantberbere.com/createur-artisan-sitemap.xml"
HOST = "linstantberbere.com"

ALGERIAN_CITIES = {
    "alger", "oran", "constantine", "tlemcen", "bejaia", "béjaïa", "boumerdes",
    "tizi ouzou", "tizi-ouzou", "ghardaia", "ghardaïa", "setif", "sétif",
    "annaba", "blida", "tipaza", "mascara", "mostaganem", "relizane", "msila",
    "m'sila", "batna", "biskra", "djelfa", "ouargla", "tamanrasset", "timimoun",
    "adrar", "illizi", "djanet", "el oued", "tebessa", "souk ahras", "jijel",
    "skikda", "chelghoum", "kabylie", "kabyli", "chenoua", "cherchell",
    "oranie", "constantine", "aures", "aures", "hoggar", "tassili", "miliana",
    "khenchela", "oum el bouaghi", "ain defla", "ain temouchent", "el bayadh",
    "el tarf", "guelma", "laghouat", "medea", "nâama", "naama", "sidi bel abbes",
    "saida", "souk ahras", "tiaret", "tissemsilt", "insalah", "in salah",
    "timimoun", "el meniaa", "el-meniaa", "touggourt", "touat", "gourara",
    "zaouia", "ksar", "beni abbes", "béni abbès",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=REPO / "app" / "data" / "linstantberbere_artisans.json")
    args = ap.parse_args()

    fetch = PoliteFetcher(HOST)
    ckpt = Checkpointer(REPO / "scripts" / "data" / "reports" / "ib_artisans.jsonl")

    html = fetch.fetch(SITEMAP)
    slugs = re.findall(r"<loc>https://linstantberbere\.com/createur-artisan/([^/]+)/</loc>", html or "")
    print(f"[*] {len(slugs)} creator pages in sitemap", flush=True)

    records = []
    for slug in slugs:
        url = f"{BASE}/createur-artisan/{slug}/"
        page = fetch.fetch(url)
        if page is None:
            continue
        # bio block = first meaningful paragraph after "Découvrez" / creator section
        m = re.search(r'<div[^>]*class="[^"]*(?:elementor-widget-text-editor|entry-content|product-cat-desc)[^"]*"[^>]*>(.*?)</div>', page, re.S)
        bio = ""
        if m:
            bio = scrape_text(m.group(1))
        if not bio:
            # fallback: search for the "Créateur/Créatrice" block
            i = page.find("Créatrice")
            if i < 0:
                i = page.find("Créateur")
            if i >= 0:
                seg = re.sub(r"<script.*?</script>|<style.*?</style>", "", page[i : i + 3000], flags=re.S)
                bio = scrape_text(seg)
        bio = bio[:2000].strip()
        title = ""
        tm = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
        if tm:
            title = scrape_text(tm.group(1))
        # location detection
        low = bio.lower()
        algerian = any(c in low for c in ALGERIAN_CITIES)
        elsewhere = "maroc" in low or "tunis" in low or "fès" in low or "fez" in low \
            or "paris" in low or "france" in low or "milan" in low or "italie" in low
        rec = {
            "name": title or slug.replace("-", " ").title(),
            "slug": slug,
            "bio": bio,
            "algerian": algerian,
            "elsewhere": elsewhere,
            "source": "linstantberbere",
            "source_url": url,
        }
        records.append(rec)
        ckpt.save(slug, rec)
        flag = "DZ" if algerian else ("XX" if elsewhere else "?")
        print(f"  [{flag}] {rec['name']}", flush=True)

    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=1))
    dz = [r for r in records if r["algerian"]]
    print(f"\n[=] {len(records)} creators, {len(dz)} Algerian -> {args.output}")
    print(f"    stats: {fetch.stats}")


if __name__ == "__main__":
    main()
