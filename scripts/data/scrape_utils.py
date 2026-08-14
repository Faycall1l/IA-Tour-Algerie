#!/usr/bin/env python3
"""Shared polite-scraping helpers for the artisan data campaign.

Design rules (per AGENTS.md / user directive):
- Never aggressive: random 2-5s delay between requests per host, one worker.
- Honest UA, retries with exponential backoff, honor robots.txt (caller checks).
- Disk-cached responses so failed runs resume without re-hitting sites.
- Checkpoint JSON writer so partial scrapes are never lost.
"""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36 ATHAR-data-collector/1.0"
)

DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


@dataclass
class PoliteFetcher:
    """One-host fetcher: disk cache + polite delay + retry/backoff.

    Cache key = sha1 of URL. Stored under cache_dir/<host>/<sha1>.html
    plus a sidecar .meta.json (status, content_type, fetched_at).
    """

    host: str
    cache_dir: Path = Path("/tmp/athar_scrape_cache")
    delay_range: tuple[float, float] = (2.0, 5.0)
    max_retries: int = 3
    backoff_base: float = 3.0
    session: requests.Session = field(default_factory=requests.Session)
    last_request_at: float = 0.0
    stats: dict[str, int] = field(default_factory=lambda: {"fetched": 0, "cached": 0, "errors": 0})

    def __post_init__(self) -> None:
        self.session.headers.update(DEFAULT_HEADERS)
        self._host_dir = self.cache_dir / self.host.replace("/", "_")
        self._host_dir.mkdir(parents=True, exist_ok=True)

    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        import hashlib

        h = hashlib.sha1(url.encode()).hexdigest()
        return self._host_dir / f"{h}.html", self._host_dir / f"{h}.meta.json"

    def _wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_request_at
        delay = random.uniform(*self.delay_range)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self.last_request_at = time.monotonic()

    def fetch(self, url: str, *, force: bool = False) -> Optional[str]:
        """Return page HTML (from cache if present), None on hard failure."""
        body_path, meta_path = self._cache_paths(url)
        if not force and body_path.exists() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                if meta.get("status") == 200:
                    self.stats["cached"] += 1
                    return body_path.read_text()
            except Exception:
                pass  # corrupt cache entry -> refetch

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            self._wait()
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    body_path.write_text(resp.text)
                    meta_path.write_text(
                        json.dumps(
                            {
                                "status": 200,
                                "content_type": resp.headers.get("content-type", ""),
                                "fetched_at": time.time(),
                            }
                        )
                    )
                    self.stats["fetched"] += 1
                    return resp.text
                elif resp.status_code in (429, 403, 503):
                    # Throttled — back off harder than default.
                    self.stats["errors"] += 1
                    backoff = self.backoff_base * (2 ** attempt) + random.uniform(1, 4)
                    time.sleep(backoff)
                    last_exc = RuntimeError(f"HTTP {resp.status_code} for {url}")
                    continue
                else:
                    self.stats["errors"] += 1
                    return None
            except requests.RequestException as exc:
                self.stats["errors"] += 1
                last_exc = exc
                time.sleep(self.backoff_base * (2 ** attempt))

        if last_exc:
            raise RuntimeError(f"scrape failed after {self.max_retries} attempts: {last_exc}")
        return None

    def fetch_json(self, url: str, **kw: Any) -> Optional[dict]:
        html = self.fetch(url, **kw)
        if html is None:
            return None
        # Some endpoints are JSON even though we fetched generically; helper for callers.
        return html


class Checkpointer:
    """Append-only JSONL checkpointing for long scrapes (resume-safe)."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[Any] = set()
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        self._seen.add(json.loads(line).get("_key"))
                    except Exception:
                        pass

    def already_done(self, key: Any) -> bool:
        return key in self._seen

    def save(self, key: Any, record: dict) -> None:
        record = dict(record)
        record["_key"] = key
        with self.path.open("a") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._seen.add(key)

    def read_all(self) -> list[dict]:
        out = []
        if not self.path.exists():
            return out
        with self.path.open() as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        rec.pop("_key", None)
                        out.append(rec)
                    except Exception:
                        pass
        return out


def scrape_text(html: str) -> str:
    """Crude HTML->text (strip scripts/styles/tags, collapse whitespace)."""
    import re

    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_phone(raw: Any) -> str:
    """Extract a 10-digit-ish DZ phone from free text (leading 0, or +213)."""
    if not raw:
        return ""
    s = str(raw).replace(" ", "").replace(".", "").replace("-", "")
    s = s.replace("\u202d", "").replace("\u202c", "")
    import re

    # match +213 6... or 0[5-7]...
    m = re.search(r"\+213[0-9]{9}", s)
    if m:
        return m.group(0)
    m = re.search(r"0[5-7][0-9]{8}", s)
    if m:
        return "+213 " + m.group(0)[1:]
    m = re.search(r"0[234][0-9]{6,8}", s)  # landline 02/03/04 (7-9 digits)
    if m:
        return "+213 " + m.group(0)[1:]
    return ""
