#!/usr/bin/env python3
"""ATHAR OS — Algerian tourism API CLI explorer.

Usage:
  export ATHAR_API=http://localhost:8000/api/v1
  python scripts/cli/athar_cli.py pois list --wilaya 31
  python scripts/cli/athar_cli.py pois search "plage oran"
  python scripts/cli/athar_cli.py wilayas guide 31
"""

import json
import os
from datetime import datetime
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="ATHAR OS — Algerian tourism API explorer", no_args_is_help=True)
console = Console()

API = os.environ.get("ATHAR_API", "http://localhost:8000/api/v1")


# ── Helpers ──────────────────────────────────────────────────────────────

def api_url(path: str) -> str:
    return f"{API}/{path.lstrip('/')}"


def get(path: str, params: dict | None = None):
    r = httpx.get(api_url(path), params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def extract_items(data, default_key: str = "items"):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in (default_key, "items", "results", "data"):
            if key in data:
                return data[key]
    return []


def extract_total(data, default_key: str = "total"):
    if isinstance(data, dict):
        for key in (default_key, "total", "count", "total_count"):
            if key in data:
                return data[key]
    return len(extract_items(data))


def print_table(title: str, columns: list[tuple[str, str]], rows: list[dict]):
    if not rows:
        console.print("[yellow]No results[/]")
        return
    t = Table(title=title)
    for col_name, _ in columns:
        t.add_column(col_name)
    for row in rows:
        t.add_row(*[str(row.get(k, "")) or "—" for _, k in columns])
    console.print(t)


def print_json(data):
    console.print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ── POIs ─────────────────────────────────────────────────────────────────

@app.command()
def pois(
    ctx: typer.Context,
    wilaya: Optional[int] = typer.Option(None, help="Wilaya ID (1-58)"),
    category: Optional[str] = typer.Option(None, help="Category filter"),
    neighborhood: Optional[str] = typer.Option(None, help="Neighborhood filter"),
    limit: int = typer.Option(10, help="Max results"),
    json_output: bool = typer.Option(False, "--json", help="Raw JSON output"),
):
    """List POIs with optional filters."""
    params = {"page_size": limit}
    if wilaya:
        params["wilaya_id"] = wilaya
    if category:
        params["category"] = category
    if neighborhood:
        params["neighborhood"] = neighborhood
    data = get("pois", params)
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"POIs ({extract_total(data)} total)",
        [("Name", "name"), ("Category", "category"), ("Wilaya", "wilaya_id"), ("Subtype", "subtype"), ("Score", "average_score")],
        items,
    )


@app.command()
def poi_search(
    q: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Vector search POIs."""
    data = get("pois/search", {"q": q, "limit": limit})
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"POI search: '{q}' ({extract_total(data)} results)",
        [("Name", "name"), ("Category", "category"), ("Wilaya", "wilaya_id"), ("Subtype", "subtype")],
        items,
    )


@app.command()
def poi_get(
    poi_id: str = typer.Argument(..., help="POI UUID"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Get POI by ID."""
    data = get(f"pois/{poi_id}")
    if json_output:
        print_json(data)
        return
    for k, v in data.items():
        console.print(f"[bold]{k}:[/]  {v}")


@app.command()
def poi_neighborhoods(
    wilaya_id: int = typer.Argument(..., help="Wilaya ID"),
    json_output: bool = typer.Option(False, "--json"),
):
    """List distinct neighborhoods in a wilaya."""
    data = get("pois/neighborhoods", {"wilaya_id": wilaya_id})
    if json_output:
        print_json(data)
        return
    nbs = data.get("neighborhoods", [])
    console.print(f"[bold]{len(nbs)} neighborhoods[/] in wilaya {wilaya_id}:")
    for nb in nbs:
        console.print(f"  • {nb}")


# ── Stays ────────────────────────────────────────────────────────────────

@app.command()
def stays(
    wilaya: Optional[int] = typer.Option(None, help="Wilaya ID"),
    stay_type: Optional[str] = typer.Option(None, "--type", help="hotel/hostel/guesthouse"),
    limit: int = typer.Option(10, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """List stays with optional filters."""
    params = {"page_size": limit}
    if wilaya:
        params["wilaya_id"] = wilaya
    if stay_type:
        params["type"] = stay_type
    data = get("stays", params)
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Stays ({extract_total(data)} total)",
        [("Name", "name"), ("Type", "type"), ("Wilaya", "wilaya_id"), ("Price", "price_level"), ("Rating", "average_score")],
        items,
    )


@app.command()
def stay_get(
    stay_id: str = typer.Argument(..., help="Stay UUID"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Get stay by ID."""
    data = get(f"stays/{stay_id}")
    if json_output:
        print_json(data)
        return
    for k, v in data.items():
        console.print(f"[bold]{k}:[/]  {v}")


# ── Experiences ──────────────────────────────────────────────────────────

@app.command()
def experiences(
    wilaya: Optional[int] = typer.Option(None, help="Wilaya ID"),
    category: Optional[str] = typer.Option(None, help="Category filter"),
    season: Optional[str] = typer.Option(None, help="spring/summer/autumn/winter"),
    limit: int = typer.Option(10, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """List experiences with optional filters."""
    params = {"page_size": limit}
    if wilaya:
        params["wilaya_id"] = wilaya
    if category:
        params["category"] = category
    if season:
        params["season"] = season
    data = get("experiences", params)
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Experiences ({extract_total(data)} total)",
        [("Title", "title"), ("Category", "category"), ("Wilaya", "wilaya_id"), ("Season", "season"), ("Price", "price_dzd")],
        items,
    )


@app.command()
def experience_search(
    q: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Vector search experiences."""
    data = get("experiences/search", {"q": q, "limit": limit})
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Experience search: '{q}' ({extract_total(data)} results)",
        [("Title", "title"), ("Category", "category"), ("Wilaya", "wilaya_id"), ("Season", "season")],
        items,
    )


@app.command()
def experience_get(
    exp_id: str = typer.Argument(..., help="Experience UUID"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Get experience by ID."""
    data = get(f"experiences/{exp_id}")
    if json_output:
        print_json(data)
        return
    for k, v in data.items():
        console.print(f"[bold]{k}:[/]  {v}")


# ── Wilayas ──────────────────────────────────────────────────────────────

@app.command()
def wilayas(
    json_output: bool = typer.Option(False, "--json"),
):
    """List all wilayas."""
    data = get("discover/wilayas")
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Wilayas ({len(items)})",
        [("ID", "id"), ("Name", "name"), ("Featured", "total_featured"), ("POIs", "total_pois"), ("Stays", "total_stays"), ("Exp", "total_experiences")],
        items,
    )


@app.command()
def wilaya_guide(
    wilaya_id: int = typer.Argument(..., help="Wilaya ID"),
    json_output: bool = typer.Option(False, "--json"),
):
    """Get a curated travel guide for a wilaya."""
    data = get(f"discover/wilayas/{wilaya_id}/guide")
    if json_output:
        print_json(data)
        return
    w = data.get("wilaya", {})
    console.print(f"\n[bold cyan]Wilaya {w.get('id')}: {w.get('name')}[/]")
    console.print(f"  {w.get('description', '')[:200]}")
    console.print(f"  Featured POIs: {w.get('featured_count', 0)}  |  Experiences: {w.get('experience_count', 0)}  |  Stays: {w.get('stay_count', 0)}")
    for section_key, section_label in [
        ("top_pois", "Top POIs"),
        ("experiences", "Experiences"),
        ("stays", "Recommended Stays"),
    ]:
        items = data.get(section_key, [])
        if items:
            console.print(f"\n[bold]{section_label}:[/]")
            for i, item in enumerate(items[:5], 1):
                name = item.get("name") or item.get("title", "")
                cat = item.get("category", "")
                console.print(f"  {i}. {name}  [dim]({cat})[/]")


# ── Events ───────────────────────────────────────────────────────────────

@app.command()
def events(
    wilaya: Optional[int] = typer.Option(None, help="Wilaya ID"),
    month: Optional[int] = typer.Option(None, help="Month (1-12)"),
    category: Optional[str] = typer.Option(None, help="Category filter"),
    limit: int = typer.Option(20, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """List festivals and events."""
    params = {"page_size": limit}
    if wilaya:
        params["wilaya_id"] = wilaya
    if month:
        params["month"] = month
    if category:
        params["category"] = category
    data = get("events", params)
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Events ({extract_total(data)} total)",
        [("Title", "title"), ("Category", "category"), ("Wilaya", "wilaya_id"), ("Month", "month"), ("Duration", "duration_days")],
        items,
    )


# ── Transport ────────────────────────────────────────────────────────────

@app.command()
def stations(
    wilaya: Optional[int] = typer.Option(None, help="Wilaya ID"),
    station_type: Optional[str] = typer.Option(None, "--type", help="bus/train/tram/airport/ferry/taxi/cablecar"),
    limit: int = typer.Option(20, help="Max results"),
    json_output: bool = typer.Option(False, "--json"),
):
    """List transport stations."""
    params = {"page_size": limit}
    if wilaya:
        params["wilaya_id"] = wilaya
    if station_type:
        params["type"] = station_type
    data = get("transport/stations", params)
    items = extract_items(data)
    if json_output:
        print_json(items)
        return
    print_table(
        f"Stations ({len(items)} total)",
        [("Name", "name"), ("Type", "type"), ("Wilaya", "wilaya_id"), ("Lines", "line_count")],
        items,
    )


# ── Status / Health ──────────────────────────────────────────────────────

@app.command()
def status():
    """Check API health and connectivity."""
    try:
        r = httpx.get(f"{API}/pois", params={"page_size": 1}, timeout=5)
        r.raise_for_status()
        total = r.json().get("total", "?")
    except Exception as e:
        console.print(f"[red]✗ API unreachable:[/] {e}")
        raise typer.Exit(1)

    console.print(f"[green]✓[/] API reachable at [bold]{API}[/]")
    console.print(f"  POIs in DB: {total}")
    try:
        r2 = httpx.get(f"{API}/wilayas", timeout=5)
        wd = r2.json()
        wc = len(extract_items(wd))
        console.print(f"  Wilayas: {wc}")
    except Exception:
        pass
    try:
        r3 = httpx.get("http://localhost:6333/collections", timeout=3)
        cols = r3.json().get("result", {}).get("collections", [])
        for col in cols:
            info = httpx.get(f"http://localhost:6333/collections/{col['name']}", timeout=3).json()
            pc = info.get("result", {}).get("points_count", 0)
            console.print(f"  Qdrant '{col['name']}': {pc} points")
    except Exception:
        console.print(f"  [yellow]Qdrant: not checked[/]")


# ── Entry ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
