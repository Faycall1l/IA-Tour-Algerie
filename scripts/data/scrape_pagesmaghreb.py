#!/usr/bin/env python3
"""Scrape real artisan/craft businesses from PagesMaghreb (pagesmaghreb.com).

Source: PagesMaghreb is a long-running Algerian business directory
(contact@lespagesmaghreb.com, pages in sitemap_0..3). Detail pages AND
listing pages are server-rendered; listing pages embed each business as a
<firm-card :firm="JSON.parse('...')"> block with full contact data.

This scraper:
  1. Reads sitemap_0.xml (already downloaded to /tmp or re-fetched) to find
     artisan-relevant category listing URLs (pottery, jewelry, carpet,
     weaving, leather, copper/dinanderie, ferronnerie, vannerie, corail,
     verrerie d'art, eebenisterie, broderies, etc.).
  2. For each category, follows pagination (?page=N, links embedded in the
     page) and extracts every firm-card.
  3. Dedupes by PagesMaghreb firm id and writes a checkpoint JSONL + a final
     JSON corpus.

Usage:
  python scripts/data/scrape_pagesmaghreb.py [--output out.json]
  python scripts/data/scrape_pagesmaghreb.py --list-categories   # show curated set
  python scripts/data/scrape_pagesmaghreb.py --reset-cache

Every record carries source='pagesmaghreb' and source_url = detail URL, so it
satisfies the "every record from a real, verifiable source" rule.
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

from data.scrape_utils import Checkpointer, PoliteFetcher  # noqa: E402

BASE = "https://www.pagesmaghreb.com"
SITEMAP0 = "https://www.pagesmaghreb.com/sitemap_0.xml"
HOST = "www.pagesmaghreb.com"

# Curated set of artisan/traditional-craft categories. Each tuple is
# (category_name, listing_url). Only *traditional craft* categories — no
# industrial fabrication, import/export, sanitary ware, car parts, etc.
ARTISAN_CATEGORIES: list[tuple[str, str]] = [
    ("artisanat-dart", "/entreprises/artisanat/artisanat-dart/algerie"),
    ("artisanat-detail", "/entreprises/artisanat/artisanat-detail/algerie"),
    ("maroquinerie-artisanat", "/entreprises/artisanat/maroquinerie-artisanat/algerie"),
    ("maroquinerie-traditionnelle-detail", "/entreprises/artisanat/maroquinerie-traditionnelle-detail/algerie"),
    ("travail-du-cuir", "/entreprises/artisanat/travail-du-cuir/algerie"),
    ("sellerie-maroquinerie", "/entreprises/artisanat/sellerie-maroquinerie/algerie"),
    ("harnachement-et-sellerie-fabrication", "/entreprises/artisanat/harnachement-et-sellerie-fabrication/algerie"),
    ("corail-fabrication", "/entreprises/artisanat/corail-fabrication/algerie"),
    ("oeuvres-dart-fabrication", "/entreprises/artisanat/oeuvres-dart-fabrication/algerie"),
    ("oeuvres-dart-vente", "/entreprises/artisanat/oeuvres-dart-vente/algerie"),
    ("sparterie-et-vannerie", "/entreprises/artisanat/sparterie-et-vannerie/algerie"),
    ("vannerie-fabrication", "/entreprises/artisanat/vannerie-fabrication/algerie"),
    ("vannerie-et-sparterie-gros", "/entreprises/artisanat/vannerie-et-sparterie-gros/algerie"),
    ("vannerie-detail", "/entreprises/commerce/vannerie-detail/algerie"),
    ("poterie-faiencerie-artisanat", "/entreprises/verre-et-materiaux-de-construction/poterie-faiencerie-artisanat/algerie"),
    ("poterie", "/entreprises/verre-et-materiaux-de-construction/poterie/algerie"),
    ("ceramique-artisanat", "/entreprises/verre-et-materiaux-de-construction/ceramique-artisanat/algerie"),
    ("ceramiques-dart", "/entreprises/verre-et-materiaux-de-construction/ceramiques-dart/algerie"),
    ("verrerie-dart", "/entreprises/verre-et-materiaux-de-construction/verrerie-dart/algerie"),
    ("verrerie-dart-soufflee", "/entreprises/verre-et-materiaux-de-construction/verrerie-dart-verrerie-soufflee-fabrication-gros/algerie"),
    ("bijouterie-entreprise-artisanale", "/entreprises/produits-de-luxe-et-de-loisirs/bijouterie-entreprise-artisanale/algerie"),
    ("joaillerie-creation-fabrication", "/entreprises/produits-de-luxe-et-de-loisirs/joaillerie-creation-fabrication/algerie"),
    ("bijouterie-traditionnelle-detail", "/entreprises/commerce/bijouterie-traditionnelle-et-horlogerie-detail/algerie"),
    ("bijouterie-joaillerie-fabrication", "/entreprises/metallurgie-et-travail-des-metaux/bijouterie-joaillerie-fabrication-transformation/algerie"),
    ("cuivrerie-et-dinanderie", "/entreprises/produits-de-luxe-et-de-loisirs/cuivrerie-et-dinanderie/algerie"),
    ("dinanderie-detail", "/entreprises/metallurgie-et-travail-des-metaux/dinanderie-detail/algerie"),
    ("dinanderie-et-cuivrerie", "/entreprises/metallurgie-et-travail-des-metaux/dinanderie-et-cuivrerie/algerie"),
    ("ferronnerie-artisanat", "/entreprises/construction-mecanique-et-industrie-equipements/ferronnerie-artisanat/algerie"),
    ("ferronnerie-dart", "/entreprises/construction-mecanique-et-industrie-equipements/ferronnerie-dart/algerie"),
    ("ferronnerie-menuiserie-metallique-artisanat", "/entreprises/construction-mecanique-et-industrie-equipements/ferronnerie-et-menuiserie-metallique-artisanat/algerie"),
    ("tapis-fabrication", "/entreprises/textiles-et-habillement/tapis-fabrication/algerie"),
    ("tapis-detail", "/entreprises/textiles-et-habillement/tapis-detail/algerie"),
    ("tapis-dorient-et-dartisanat", "/entreprises/textiles-et-habillement/tapis-dorient-et-dartisanat/algerie"),
    ("tapis-et-tapisseries-reproduction", "/entreprises/textiles-et-habillement/tapis-et-tapisseries-reproduction-reparation-restauration/algerie"),
    ("reproductions-de-tapis", "/entreprises/textiles-et-habillement/reproductions-de-tapis-et-tapisseries/algerie"),
    ("tapisserie-dart", "/entreprises/textiles-et-habillement/tapisserie-dart/algerie"),
    ("broderies-artisanat", "/entreprises/textiles-et-habillement/broderies-artisanat/algerie"),
    ("broderies-detail", "/entreprises/textiles-et-habillement/broderies-detail/algerie"),
    ("bonneterie-artisanat", "/entreprises/textiles-et-habillement/bonneterie-artisanat/algerie"),
    ("ebenisterie-dart", "/entreprises/bois-et-ameublement/ebenisterie-dart-restauration-de-meubles/algerie"),
    ("ebenisterie", "/entreprises/bois-et-ameublement/ebenisterie/algerie"),
    ("bois-debenisterie", "/entreprises/bois-et-ameublement/bois-debenisterie/algerie"),
    ("commerce-de-tapis-en-etal", "/entreprises/commerce/commerce-de-detail-de-tapis-exerce-en-etal/algerie"),
    ("artisanat-travaux-manuels-fournitures", "/entreprises/commerce/artisanat-et-travaux-manuels-fournitures-detail/algerie"),
    ("promotion-produits-artisanat", "/entreprises/produits-de-luxe-et-de-loisirs/promotion-des-produits-de-lartisanat/algerie"),
]

FIRM_CARD_RE = re.compile(r'<firm-card :firm="JSON\.parse\(\'(.*?)\'\)"', re.S)


def extract_json_parse(html: str, attr: str) -> object:
    """Pull the JSON value of a `:attr=" JSON.parse('...')"` Vue prop."""
    m = re.search(r":" + attr + r'="\s*JSON\.parse\(', html)
    if not m:
        return None
    start = m.end()
    i, n = start, len(html)
    while i < n:
        if html[i] == "\\":
            i += 2
            continue
        if html[i] == "'" and i + 1 < n and html[i + 1] == ")":
            break
        i += 1
    js = html[start:i]
    inner = js[1:] if js.startswith("'") else js
    return json.loads(inner.encode().decode("unicode_escape"))


def max_page(html: str) -> int:
    """Largest page number linked in the pagination nav."""
    pages = [int(p) for p in re.findall(r'(?:[?&]|&amp;)page=(\d+)', html)]
    return max(pages) if pages else 1


def extract_firms(html: str) -> list[dict]:
    firms = []
    for m in FIRM_CARD_RE.finditer(html):
        raw = m.group(1)
        try:
            firm = json.loads(raw.replace("\\/", "/").encode().decode("unicode_escape"))
        except Exception:
            continue
        firms.append(firm)
    return firms


def normalize_firm(firm: dict, category: str, cat_name: str) -> dict:
    """Map a PagesMaghreb firm-card into our corpus schema."""
    name = (firm.get("corporate_name") or firm.get("usual_corporate_name")
            or firm.get("slug") or "").strip()
    if not name:
        name = (firm.get("slug") or "").split("-")[0].title()
    addresses = []
    region_slug = ""
    for a in firm.get("addresses", []):
        city = a.get("city") or {}
        region = city.get("region") or {}
        if not region_slug:
            region_slug = region.get("slug", "")
        addresses.append({
            "street": a.get("name"),
            "city": city.get("name"),
            "wilaya": region.get("name"),
            "wilaya_code": region.get("code"),
            "region_slug": region.get("slug"),
        })
    source_url = f"{BASE}/entreprise/{firm.get('slug')}"
    if region_slug:
        source_url += f"/{region_slug}/algerie"
    phones, emails, websites = [], [], []
    for c in firm.get("contacts", []):
        for cm in c.get("contactmethods", []):
            t = cm.get("method_type", "").lower()
            v = cm.get("value")
            if not v:
                continue
            v = v.replace("\\/", "/")
            if "telephone" in t or "mobile" in t or "fax" in t:
                phones.append(v)
            elif "email" in t:
                emails.append(v)
            elif "site" in t or "web" in t:
                websites.append(v)
    return {
        "name": name,
        "activity_description": (firm.get("description") or "").strip(),
        "categories": [c.get("name") for c in firm.get("categories", [])],
        "addresses": addresses,
        "phones": phones,
        "emails": emails,
        "websites": websites,
        "pm_id": firm.get("id"),
        "slug": firm.get("slug"),
        "listing_category": category,
        "listing_category_name": cat_name,
        "source": "pagesmaghreb",
        "source_url": source_url,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=REPO / "app" / "data" / "pagesmaghreb_artisans.json")
    ap.add_argument("--list-categories", action="store_true")
    ap.add_argument("--max-categories", type=int, default=0, help="limit for a test run (0 = all)")
    args = ap.parse_args()

    if args.list_categories:
        for cat, url in ARTISAN_CATEGORIES:
            print(f"{cat:45s} {BASE}{url}")
        return

    fetch = PoliteFetcher(HOST)
    ckpt = Checkpointer(REPO / "scripts" / "data" / "reports" / "pm_artisans.jsonl")

    cats = ARTISAN_CATEGORIES
    if args.max_categories:
        cats = cats[: args.max_categories]

    by_id: dict[int, dict] = {}
    for cat, url in cats:
        page = 1
        maxp = 1
        while True:
            page_url = f"{BASE}{url}{'?page=%d' % page if page > 1 else ''}"
            html = fetch.fetch(page_url)
            if html is None:
                print(f"  [!] {cat} page {page}: fetch failed", flush=True)
                break
            if page == 1:
                maxp = max_page(html)
                print(f"[*] {cat}: {maxp} page(s)", flush=True)
            for firm in extract_firms(html):
                rec = normalize_firm(firm, cat, cat)
                if rec["pm_id"] is not None and rec["pm_id"] not in by_id:
                    by_id[rec["pm_id"]] = rec
                    ckpt.save(rec["pm_id"], rec)
            if page >= maxp:
                break
            page += 1

    out = sorted(by_id.values(), key=lambda r: (r.get("name") or "").lower())
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n[=] {len(out)} unique firms -> {args.output}")
    print(f"    fetcher stats: {fetch.stats}")
    cats_used: dict[str, int] = {}
    for r in out:
        cats_used[r["listing_category"]] = cats_used.get(r["listing_category"], 0) + 1
    for k, v in sorted(cats_used.items(), key=lambda kv: -kv[1]):
        print(f"    {k:45s} {v}")


if __name__ == "__main__":
    main()
