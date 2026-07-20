from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.exceptions import NotFoundException
from app.models.preference import UserPreference
from app.models.user import User
from app.schemas.preference import PreferenceRead, PreferenceUpdate

router = APIRouter(prefix="/preferences", tags=["Preferences"])


@router.get("", response_model=PreferenceRead | None)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    return result.scalar_one_or_none()


@router.put("", response_model=PreferenceRead)
async def upsert_preferences(
    body: PreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    pref = result.scalar_one_or_none()

    if pref:
        for field, value in body.model_dump(exclude_unset=True).items():
            setattr(pref, field, value)
    else:
        pref = UserPreference(
            user_id=current_user.id,
            **body.model_dump(exclude_unset=True),
        )
        db.add(pref)

    await db.commit()
    await db.refresh(pref)
    return PreferenceRead.model_validate(pref)


@router.delete("", status_code=204)
async def delete_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == current_user.id)
    )
    pref = result.scalar_one_or_none()
    if pref:
        await db.delete(pref)
        await db.commit()
