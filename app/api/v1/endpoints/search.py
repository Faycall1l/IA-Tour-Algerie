import logging
import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.search import SearchFeed, SearchResult, SuggestFeed, SuggestItem

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/search", tags=["Search"])

PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

SEARCH_UNION = """
SELECT * FROM (
  -- POIs
  SELECT
    'poi' AS entity_type,
    id AS entity_id,
    name,
    name_en,
    name_ar,
    description,
    category,
    subtype,
    wilaya_id,
    commune,
    latitude,
    longitude,
    photo_url,
    0 AS price,
    ts_rank(search_vector, plainto_tsquery('french', :q)) AS rank
  FROM pois
  WHERE search_vector @@ plainto_tsquery('french', :q)

  UNION ALL

  -- Stays
  SELECT
    'stay' AS entity_type,
    id AS entity_id,
    name,
    NULL AS name_en,
    NULL AS name_ar,
    description,
    property_type AS category,
    NULL AS subtype,
    wilaya_id,
    address AS commune,
    latitude,
    longitude,
    COALESCE(photos[1], NULL) AS photo_url,
    price_per_night_dzd AS price,
    ts_rank(search_vector, plainto_tsquery('french', :q)) AS rank
  FROM stays
  WHERE search_vector @@ plainto_tsquery('french', :q)

  UNION ALL

  -- Experiences
  SELECT
    'experience' AS entity_type,
    id AS entity_id,
    title AS name,
    NULL AS name_en,
    NULL AS name_ar,
    description,
    category,
    NULL AS subtype,
    wilaya_id,
    NULL AS commune,
    meeting_point_lat AS latitude,
    meeting_point_lng AS longitude,
    COALESCE(photos[1], NULL) AS photo_url,
    price_dzd AS price,
    ts_rank(search_vector, plainto_tsquery('french', :q)) AS rank
  FROM experiences
  WHERE search_vector @@ plainto_tsquery('french', :q)
) AS results
ORDER BY rank DESC
OFFSET :offset
LIMIT :limit
"""

SEARCH_COUNT_UNION = """
SELECT COUNT(*) FROM (
  SELECT id FROM pois WHERE search_vector @@ plainto_tsquery('french', :q)
  UNION ALL
  SELECT id FROM stays WHERE search_vector @@ plainto_tsquery('french', :q)
  UNION ALL
  SELECT id FROM experiences WHERE search_vector @@ plainto_tsquery('french', :q)
) AS cnt
"""


@router.get(
    "/suggest",
    response_model=SuggestFeed,
    summary="Search suggestions",
    description="Fast prefix autocomplete across POI names, experience titles, and stay names. Sorted by name length.",  # noqa: E501
    responses={422: {"description": "Query required (min 1 char)"}},
)
async def suggest(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    if not q.strip():
        return SuggestFeed(query=q, items=[])

    like = f"{q.strip()}%"

    poi_sql = text(
        "SELECT id, name, category, wilaya_id, photo_url FROM pois WHERE name ILIKE :q LIMIT :lim"
    )
    exp_sql = text(
        "SELECT id, title, category, wilaya_id, COALESCE(photos[1], NULL) FROM experiences WHERE title ILIKE :q LIMIT :lim"  # noqa: E501
    )
    stay_sql = text(
        "SELECT id, name, property_type, wilaya_id, COALESCE(photos[1], NULL) FROM stays WHERE name ILIKE :q LIMIT :lim"  # noqa: E501
    )

    items: list[SuggestItem] = []

    for sql, etype in [(poi_sql, "poi"), (exp_sql, "experience"), (stay_sql, "stay")]:
        rows = (await db.execute(sql, {"q": like, "lim": limit})).fetchall()
        for r in rows:
            items.append(
                SuggestItem(
                    entity_type=etype,
                    entity_id=r[0],
                    name=r[1],
                    category=r[2],
                    wilaya_id=r[3],
                    photo_url=r[4],
                )
            )

    items.sort(key=lambda x: len(x.name))
    return SuggestFeed(query=q, items=items[:limit])


@router.get(
    "",
    response_model=SearchFeed,
    summary="Unified search",
    description=(
        "Full-text search (French tsvector) across POIs, stays, and experiences in a single "
        "ranked result set. Each result carries entity_type, category, coordinates, price, "
        "and ts_rank score. Falls back gracefully if search vectors are absent."
    ),
    responses={422: {"description": "Query required (min 1 char)"}},
)
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    db: AsyncSession = Depends(get_db),
):
    if not q.strip():
        return SearchFeed(
            query=q, results=[], total=0, page=page, page_size=page_size, total_pages=0
        )

    # Count
    count_result = await db.execute(text(SEARCH_COUNT_UNION), {"q": q.strip()})
    total = count_result.scalar() or 0

    # Search
    offset = (page - 1) * page_size
    result = await db.execute(
        text(SEARCH_UNION),
        {"q": q.strip(), "offset": offset, "limit": page_size},
    )
    rows = result.fetchall()

    total_pages = max(1, math.ceil(total / page_size))

    return SearchFeed(
        query=q,
        results=[
            SearchResult(
                entity_type=r[0],
                entity_id=r[1],
                name=r[2],
                name_en=r[3],
                name_ar=r[4],
                description=r[5],
                category=r[6],
                subtype=r[7],
                wilaya_id=r[8],
                commune=r[9],
                latitude=float(r[10]) if r[10] else None,
                longitude=float(r[11]) if r[11] else None,
                photo_url=r[12],
                price=float(r[13]) if r[13] else None,
                rank=float(r[14]) if r[14] else None,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
