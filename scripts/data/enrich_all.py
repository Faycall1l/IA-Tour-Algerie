#!/usr/bin/env python3
"""Master enrichment pipeline: descriptions, photos, featured, pricing, events."""

import subprocess
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent

SCRIPTS = [
    ("Wikivoyage destination descriptions", "enrich_wikivoyage.py"),
    ("Featured attractions ranking", "enrich_featured_attractions.py"),
    ("Pricing & events seeding", "enrich_pricing_events.py"),
    ("Wikimedia Commons photos", "enrich_wikimedia_photos.py"),
]


def run_step(name, script):
    print(f"\n{'='*60}")
    print(f"  STEP: {name}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script)],
        capture_output=False,
        text=True,
    )
    if result.returncode != 0:
        print(f"\n  ❌ {name} FAILED (exit code {result.returncode})")
        return False
    print(f"\n  ✅ {name} complete")
    return True


def main():
    print("=" * 60)
    print("  ATHAR DATA ENRICHMENT PIPELINE")
    print("=" * 60)

    start = time.time()
    successes = 0

    for name, script in SCRIPTS:
        ok = run_step(name, script)
        if ok:
            successes += 1
        print()

    elapsed = time.time() - start
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print(f"\n{'='*60}")
    print(f"  Pipeline complete: {successes}/{len(SCRIPTS)} steps succeeded")
    print(f"  Duration: {minutes}m {seconds}s")
    print(f"{'='*60}")

    return 0 if successes == len(SCRIPTS) else 1


if __name__ == "__main__":
    sys.exit(main())
