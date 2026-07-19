"""Parse OSM opening_hours strings into structured weekday/time slots and store in
opening_hours_slots JSONB column.

Handles common patterns:
  - "Mo-Fr 09:00-18:00"
  - "Mo-Sa 08:00-12:00,14:00-18:00"
  - "Mo-Fr 09:00-18:00; Sa 09:00-12:00"
  - "24/7"
  - "PH off"
"""

import asyncio
import logging
import re
import sys
from collections import OrderedDict

from sqlalchemy import select

sys.path.insert(0, ".")

from app.db.session import async_session  # noqa: E402
from app.models.poi import POI  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

WEEKDAYS = OrderedDict([
    ("Mo", "monday"),
    ("Tu", "tuesday"),
    ("We", "wednesday"),
    ("Th", "thursday"),
    ("Fr", "friday"),
    ("Sa", "saturday"),
    ("Su", "sunday"),
])

WEEKDAY_ABBR = {v: k for k, v in WEEKDAYS.items()}
WEEKDAY_ORDER = {k: i for i, k in enumerate(WEEKDAYS)}

WEEKDAYS_LIST = list(WEEKDAYS.keys())


def _expand_day_range(start: str, end: str) -> list[str]:
    """Expand day range like Mo-Fr into [Mo, Tu, We, Th, Fr]."""
    if start not in WEEKDAY_ORDER or end not in WEEKDAY_ORDER:
        return [start]
    si, ei = WEEKDAY_ORDER[start], WEEKDAY_ORDER[end]
    if si <= ei:
        return WEEKDAYS_LIST[si : ei + 1]
    return WEEKDAYS_LIST[si:] + WEEKDAYS_LIST[: ei + 1]


def _parse_time_range(t: str) -> dict | None:
    """Parse a single time range like '09:00-18:00'."""
    m = re.match(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})", t.strip())
    if m:
        return {"opens": m.group(1), "closes": m.group(2)}
    return None


def _parse_day_spec(part: str) -> tuple[list[str], list[dict]]:
    """Parse a single day+times spec like 'Mo-Fr 09:00-18:00' or 'Mo 09:00-12:00,14:00-18:00'."""
    part = part.strip()
    # Match day spec at start
    m = re.match(r"([A-Za-z]{2}(?:[-–][A-Za-z]{2})?)\s+(.*)", part)
    if not m:
        return [], []
    day_raw = m.group(1).strip()
    time_raw = m.group(2).strip()

    # Handle "Mo-Fr" or "Mo"
    if "-" in day_raw or "–" in day_raw:
        sep = "-" if "-" in day_raw else "–"
        d1, d2 = day_raw.split(sep)
        days = _expand_day_range(d1.strip(), d2.strip())
    else:
        days = [day_raw] if day_raw in WEEKDAYS else []

    slots = []
    for tpart in time_raw.split(","):
        parsed = _parse_time_range(tpart.strip())
        if parsed:
            slots.append(parsed)
    return days, slots


def parse_opening_hours(raw: str) -> dict | None:
    """Parse an OSM opening_hours string into a structured dict.

    Returns dict like:
      {
        "monday": [{"opens": "09:00", "closes": "18:00"}],
        "tuesday": [...],
        ...
        "note": "PH off"  # optional
      }
    Returns None for unparseable strings.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()
    if raw == "24/7":
        slot = {"opens": "00:00", "closes": "23:59"}
        return {day: [slot] for day in WEEKDAYS.values()}

    result: dict[str, list[dict]] = {}
    notes = []

    # Split on ";"
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        if part.lower() in ("ph off", "off", "closed"):
            notes.append(part)
            continue
        if part.upper() in WEEKDAYS or any(d in part for d in WEEKDAYS):
            days, slots = _parse_day_spec(part)
            for d in days:
                full_name = WEEKDAYS.get(d)
                if full_name and slots:
                    result.setdefault(full_name, []).extend(slots)
        else:
            # Maybe just a time range without day spec
            slot = _parse_time_range(part)
            if slot:
                for day in WEEKDAYS.values():
                    result.setdefault(day, []).append(slot)
            else:
                notes.append(part)

    if notes:
        result["note"] = "; ".join(notes)

    return result if any(v for k, v in result.items() if k != "note") else None


async def main():
    async with async_session() as db:
        result = await db.execute(
            select(POI).where(POI.opening_hours.isnot(None), POI.opening_hours != "")
        )
        pois = result.scalars().all()

    parsed = 0
    for poi in pois:
        slots = parse_opening_hours(poi.opening_hours)
        if slots:
            poi.opening_hours_slots = slots
            parsed += 1

    async with async_session() as db:
        for poi in pois:
            if poi.opening_hours_slots:
                db.add(poi)
        await db.commit()

    logger.info("Parsed opening_hours for %d / %d POIs", parsed, len(pois))


if __name__ == "__main__":
    asyncio.run(main())
