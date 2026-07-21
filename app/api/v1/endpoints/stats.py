"""Dashboard stats — overview counts for the home screen."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.event import Event
from app.models.experience import Experience
from app.models.poi import POI
from app.models.review import Review
from app.models.stay import Stay
from app.models.trip import Trip
from app.models.user import User

router = APIRouter(prefix="/stats", tags=["Dashboard"])


@router.get("")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
):
    def count(stmt):
        return select(func.count()).select_from(stmt.subquery())

    total_pois = (await db.execute(count(select(POI)))).scalar() or 0
    total_stays = (await db.execute(count(select(Stay)))).scalar() or 0
    total_experiences = (await db.execute(count(select(Experience)))).scalar() or 0
    total_reviews = (await db.execute(count(select(Review)))).scalar() or 0
    total_events = (await db.execute(count(select(Event)))).scalar() or 0
    total_trips = (await db.execute(count(select(Trip)))).scalar() or 0
    total_users = (await db.execute(count(select(User)))).scalar() or 0

    return {
        "total_pois": total_pois,
        "total_stays": total_stays,
        "total_experiences": total_experiences,
        "total_reviews": total_reviews,
        "total_events": total_events,
        "total_trips": total_trips,
        "total_users": total_users,
    }
