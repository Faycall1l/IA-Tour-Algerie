#!/usr/bin/env python3
"""Wikivoyage/Wikipedia description enrichment for featured POIs (data-v2 step 11).

Fetches real intro extracts from FR/EN Wikipedia and FR/EN Wikivoyage for the
featured POIs that currently lack a description (or whose description is an
auto-generated template, with `--upgrade`), and writes them to `pois.description`
tagged with a new `description_source` column.

Matching pipeline (deterministic, no LLM):
  1. `osm_tags.wikidata` QID -> sitelinks via the Wikidata API (fr first, en fallback).
  2. CURATED_RULES: verified name-substring rules for well-known Algerian sites.
  3. Search fallback (fr.wikivoyage -> fr.wikipedia -> en.wikivoyage -> en.wikipedia),
     accepted only when the hit title shares meaningful tokens with the POI name.

Usage:
    python -m scripts.data.enrich_wikivoyage_pois [--dry-run] [--limit N] [--upgrade]
"""

import argparse
import json
import logging
import os
import random
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DB_CONFIG = {
    "host": "localhost",
    "port": 5434,
    "dbname": "athar_db",
    "user": "athar",
    "password": "athar_pass",
}

USER_AGENT = "ATHAR-Tourism/1.0 (data enrichment bot - bayrem.aymen@univ-usto.dz)"
SOURCES = {
    "fr": ("https://fr.wikipedia.org/w/api.php", "wikipedia-fr"),
    "en": ("https://en.wikipedia.org/w/api.php", "wikipedia-en"),
    "frwv": ("https://fr.wikivoyage.org/w/api.php", "wikivoyage-fr"),
    "enwv": ("https://en.wikivoyage.org/w/api.php", "wikivoyage-en"),
}
MAX_LEN = 3000
MIN_LEN = 60

REPORT_DIR = Path(__file__).resolve().parent / "reports"
STATE_FILE = Path(__file__).resolve().parent / "raw" / "wikivoyage_poi_state.json"


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _strip_name(s: str) -> str:
    """POI name minus parentheticals / trailing Arabic / punctuation."""
    if not s:
        return ""
    s = re.sub(r"[（(].*?[)）]", " ", s)
    s = re.split(r"[;\u0641-\u064a\u0670-\u06d3\u06dd\u0660-\u0669]+", s)[0]
    return s.strip()


def _tokens(s: str) -> set[str]:
    return {w for w in norm(s).split() if len(w) >= 4}


# Name-substring rule -> (source, exact article title, museum_ok). Only rules whose
# article was verified to exist during probing are hard-coded; the rest go via search.
# museum_ok=False rules (e.g. town-level articles) are skipped for museum POIs, whose
# descriptions must come from a museum-specific article.
CURATED_RULES: list[tuple[str, str, str, bool]] = [
    ("musee national ahmed zabana", "fr", "Musée national Zabana d'Oran", True),
    ("musee public national cirta", "fr", "Musée national Cirta", True),
    ("musee national cirta", "fr", "Musée national Cirta", True),
    ("cherchell", "fr", "Musée public national de Cherchell", True),
    ("tombeau de tin hinan", "fr", "Tombeau de Tin Hinan", True),
    ("congres de la soummam", "fr", "Congrès de la Soummam", True),
    ("palais des rais", "fr", "Palais des Raïs", True),
    ("bastion", "fr", "Palais des Raïs", True),
    ("hippone", "fr", "Hippone", True),
    ("متحف هيبون", "fr", "Musée d'Hippone", True),
    ("parc national de gouraya", "fr", "Parc national de Gouraya", True),
    ("gouraya", "fr", "Parc national de Gouraya", True),
    ("erg chech", "fr", "Erg Chech", True),
    ("boussemghoun", "fr", "Boussemghoun", True),
    ("oued daoura", "fr", "Oued Daoura", True),
    # NOTE: Chott el-Gharsa excluded on purpose — the only FR article describes the
    # Tunisian side; attributing it to the Algerian POI (Bir El Ater) would mislead.
    ("el kantara", "fr", "El Kantara", False),
    ("kenadsa", "en", "Kénadsa", False),
]

# POIs whose only available article describes a feature in another country — the
# geography would mislead travelers. Kept as an explicit blocklist (deterministic).
BLOCKED_NAMES = {"chott el gharsa", "shatt al gharsah"}


def api_call(api_url: str, params: dict, retries: int = 5) -> dict | None:
    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        url = f"{api_url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 5 + (2**attempt) + random.random() * 3
                log.warning("  429 rate limit, waiting %.0fs...", wait)
                time.sleep(wait)
                continue
            log.warning("  HTTP %s: %s", e.code, e.reason)
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("  error: %s", e)
            return None
    return None


def batch_extracts(api_url: str, titles: list[str]) -> dict[str, str]:
    """Return {resolved_title: extract} for a batch of titles (with redirects)."""
    if not titles:
        return {}
    params = {
        "action": "query",
        "prop": "extracts",
        "exintro": True,
        "explaintext": True,
        "redirects": 1,
        "titles": "|".join(titles),
        "format": "json",
    }
    data = api_call(api_url, params)
    if not data:
        return {}
    out: dict[str, str] = {}
    for pid, page in data.get("query", {}).get("pages", {}).items():
        if pid != "-1":
            ex = re.sub(r"\n{3,}", "\n\n", (page.get("extract") or "")).strip()
            if len(ex) >= MIN_LEN:
                out[page.get("title", "")] = ex
    return out


def search_title(api_url: str, query: str) -> str | None:
    """Top-1 search result title, or None. Uses no score (dropped by MediaWiki)."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": 1,
        "srnamespace": 0,
        "format": "json",
    }
    data = api_call(api_url, params)
    if not data:
        return None
    hits = data.get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


# Known Algerian city names (normalized). A hit title that mentions one of these
# must correspond to the POI's own city, or the match is rejected.
KNOWN_CITIES = {
    "alger", "oran", "constantine", "annaba", "hippone", "setif", "tlemcen",
    "bejaia", "batna", "biskra", "tipaza", "tebessa", "cherchell", "djelfa",
    "tizi ouzou", "blida", "ghardaia", "ouargla", "tamanrasset", "djanet",
    "timimoun", "adrar", "bechar", "kenadsa", "laghouat", "jijel", "skikda",
    "bou saada", "boussemghoun", "el kantara", "gouraya", "mostaganem", "el oued",
    "sidi bel abbes", "tindouf", "naama", "illizi", "in salah", "m'sila",
    "relizane", "boumerdes", "tiaret", "el bayadh", "aflou", "ouled djellal",
    "ain temouchent", "el meniaa", "el m'ghair", "beni abbes", "messad",
}


def search_extract(api_url: str, query: str, poi_tokens: set[str]) -> str | None:
    """Search then fetch extract; accept only if the title is genuinely about the POI.

    Acceptance rules (conservative, no LLM):
      - the hit must share >= 2 distinctive name tokens with the POI name, and
      - if the hit title names a known Algerian city, that city must appear in the
        POI's own name or its wilaya (avoids attributing another city's article).
    """
    title = search_title(api_url, query)
    if not title:
        return None
    hit_tokens = _tokens(title)
    distinctive = {t for t in poi_tokens if len(t) >= 5}
    shared = distinctive & hit_tokens
    if len(shared) < 2:
        return None
    for city in KNOWN_CITIES:
        city_n = norm(city)
        if city_n in norm(title) and city_n not in poi_tokens:
            return None
    ex = batch_extracts(api_url, [title]).get(title)
    if ex and len(ex) >= MIN_LEN:
        return ex[:MAX_LEN]
    return None


def wikidata_sitelink(qid: str) -> dict[str, str]:
    """Resolve QID -> {lang: title} sitelinks (fr + en), one call."""
    params = {
        "action": "wbgetentities",
        "ids": qid,
        "props": "sitelinks",
        "sitefilter": "frwiki|enwiki",
        "format": "json",
    }
    data = api_call("https://www.wikidata.org/w/api.php", params)
    if not data:
        return {}
    ent = data.get("entities", {}).get(qid, {})
    out: dict[str, str] = {}
    for key, site in ent.get("sitelinks", {}).items():
        out[key.replace("wiki", "")] = site.get("title", "")
    return out


def candidates_for(poi: dict) -> list[tuple[str, str]]:
    """Ordered (source, title) candidates for a POI."""
    cands: list[tuple[str, str]] = []
    name = poi["name"] or ""
    nname = norm(name)
    is_museum = (poi.get("category") or "") == "museum"

    qid = poi.get("wikidata")
    if qid:
        links = wikidata_sitelink(qid)
        for lang in ("fr", "en"):
            if lang in links:
                cands.append((lang, links[lang]))
    for rule, lang, title, museum_ok in CURATED_RULES:
        if is_museum and not museum_ok:
            continue
        if rule in nname or rule in name:
            cands.append((lang, title))
    for title in (norm(_strip_name(name)), norm(_strip_name(poi.get("name_en") or ""))):
        if title and len(title.split()) >= 2 and (not is_museum or title):
            cands.append(("fr", title))
            cands.append(("en", title))
            cands.append(("frwv", title))
            cands.append(("enwv", title))
    # Drop candidates that resolve to a foreign-country feature.
    return [(lang, t) for lang, t in cands if norm(t) not in BLOCKED_NAMES]


def has_latin(s: str) -> bool:
    return bool(re.search(r"[A-Za-z]", s or ""))


def build_title_cache(pois: list[dict]) -> dict[tuple[str, str], str]:
    """Fetch all exact-title candidates in shared batches; return cache keyed by (lang, title)."""
    by_lang: dict[str, set[str]] = {}
    for poi in pois:
        for lang, title in candidates_for(poi):
            if lang not in ("fr", "en", "frwv", "enwv"):
                continue
            by_lang.setdefault(lang, set()).add(title)
    cache: dict[tuple[str, str], str] = {}
    for lang, titles in by_lang.items():
        api_url, _src = SOURCES[lang]
        ordered = sorted(titles)
        for i in range(0, len(ordered), 20):
            batch = ordered[i : i + 20]
            got = batch_extracts(api_url, batch)
            for t in batch:
                ex = got.get(t)
                if ex:
                    cache[(lang, t)] = ex[:MAX_LEN]
                else:
                    cache[(lang, t)] = ""
            time.sleep(1)
        log.info("title cache %s: %d titles probed", lang, len(ordered))
    return cache


def resolve(poi: dict, cache: dict[tuple[str, str], str]) -> tuple[str | None, str | None]:
    """Return (extract, description_source) for a POI."""
    raw_names = (_strip_name(poi["name"] or ""), _strip_name(poi.get("name_en") or ""))
    names = [x for x in raw_names if x]
    if any(norm(n) in BLOCKED_NAMES for n in names):
        return None, None
    poi_tokens = set()
    for n in names:
        poi_tokens |= _tokens(n)
    wilaya = norm(poi.get("wilaya") or "")

    for lang, title in candidates_for(poi):
        if (lang, title) not in cache:
            continue
        ex = cache.get((lang, title)) or ""
        if ex:
            _, src = SOURCES[lang]
            return ex[:MAX_LEN], src

    # Search fallback: only meaningful when the name is (partly) Latin-script.
    if not any(has_latin(n) for n in names):
        return None, None
    for lang in ("fr", "en"):
        api_url, src = SOURCES[lang]
        for n in names:
            q = norm(n)
            if len(q.split()) < 2:
                continue
            ex = search_extract(api_url, f"{q} {wilaya}".strip(), poi_tokens)
            if ex:
                return ex[:MAX_LEN], src
            time.sleep(0.3)
    return None, None


def fetch_pois(conn, upgrade: bool) -> list[dict]:
    cur = conn.cursor()
    where = "is_featured"
    if not upgrade:
        where += " AND p.description IS NULL"
    cur.execute(
        f"""
        SELECT p.id::text, p.name, p.name_en, p.category, p.subtype, w.name_fr,
               p.osm_tags->>'wikidata'
        FROM pois p JOIN wilayas w ON w.id = p.wilaya_id
        WHERE {where}
        ORDER BY p.id
        """
    )
    cols = ["id", "name", "name_en", "category", "subtype", "wilaya", "wikidata"]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--upgrade", action="store_true",
                    help="also enrich featured POIs that already have a description")
    ap.add_argument("--reset-state", action="store_true",
                    help="re-probe POIs already recorded in the checkpoint state")
    args = ap.parse_args()

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_name='pois' AND column_name='description_source'""")
    if not cur.fetchone():
        cur.execute("ALTER TABLE pois ADD COLUMN description_source TEXT")
        conn.commit()
        log.info("Added description_source column to pois")
    conn.close()

    conn = psycopg2.connect(**DB_CONFIG)
    pois = fetch_pois(conn, args.upgrade)
    conn.close()
    if args.limit:
        pois = pois[: args.limit]
    log.info("Targets: %d featured POIs", len(pois))

    state = load_state()
    if args.reset_state:
        state = {}
    done = set(state)

    log.info("Building exact-title candidate cache ...")
    cache = build_title_cache(pois)
    log.info("Cache ready: %d (lang,title) entries", len(cache))

    results: dict[str, dict] = {}
    hits = 0
    for i, poi in enumerate(pois, 1):
        pid = poi["id"]
        if pid in done:
            results[pid] = state[pid]
            if state[pid].get("source"):
                hits += 1
            continue
        log.info("[%d/%d] %s (%s)", i, len(pois), poi["name"], poi["wilaya"])
        extract, src = resolve(poi, cache)
        rec = {"source": src, "title": None, "extract": extract}
        results[pid] = rec
        state[pid] = rec
        if extract:
            hits += 1
            log.info("   + %s (%d chars)", src, len(extract))
        else:
            log.info("   - no article found")
        save_state(state)
        if i % 8 == 0:
            log.info("  checkpoint saved (%d done, %d hits)", len(results), hits)

    if args.dry_run:
        report_path = REPORT_DIR / "wikivoyage_pois_dryrun.txt"
    else:
        report_path = REPORT_DIR / "wikivoyage_pois_run.txt"

    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"Wikivoyage/Wikipedia POI description enrichment - "
        f"{'DRY RUN' if args.dry_run else 'RUN'}",
        f"targets: {len(pois)} | matched: {hits} | by source:",
    ]
    by_src: dict[str, int] = {}
    for r in results.values():
        s = r.get("source")
        if s:
            by_src[s] = by_src.get(s, 0) + 1
    for k, v in sorted(by_src.items()):
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("MISSES:")
    for pid, r in results.items():
        if not r.get("source"):
            p = next((x for x in pois if x["id"] == pid), None)
            lines.append(f"  {p['name']} ({p['wilaya']})" if p else f"  {pid}")
    report_path.write_text("\n".join(lines))
    log.info("Report written: %s", report_path)

    if args.dry_run:
        return

    conn = psycopg2.connect(**DB_CONFIG)
    n_written = 0
    for pid, r in results.items():
        if not r.get("source") or not r.get("extract"):
            continue
        cur = conn.cursor()
        cur.execute(
            "UPDATE pois SET description = %s, description_source = %s WHERE id = %s",
            (r["extract"], r["source"], pid),
        )
        n_written += 1
    conn.commit()
    conn.close()
    log.info("DB updated: %d POIs enriched", n_written)


if __name__ == "__main__":
    main()
