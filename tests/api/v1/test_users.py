import pytest
from app.models.provider_profile import ProviderProfile
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_self_role_change_to_admin_blocked(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.put(
        "/api/v1/users/me/role",
        json={"role": "admin"},
        headers=auth_headers,
    )
    assert resp.status_code in (403, 422)

    me = await client.get("/api/v1/users/me", headers=auth_headers)
    assert me.status_code == 200
    assert me.json()["role"] != "admin"


@pytest.mark.asyncio
async def test_self_role_change_to_provider_allowed(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.put(
        "/api/v1/users/me/role",
        json={"role": "guide"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "guide"


@pytest.mark.asyncio
async def test_self_role_change_creates_provider_profile(
    client: AsyncClient,
    auth_headers: dict[str, str],
    db: AsyncSession,
    test_user: User,
):
    resp = await client.put(
        "/api/v1/users/me/role",
        json={"role": "hotel"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    result = await db.execute(
        select(ProviderProfile).where(ProviderProfile.user_id == test_user.id)
    )
    profile = result.scalar_one_or_none()
    assert profile is not None
    assert profile.provider_type == "hotel"


@pytest.mark.asyncio
async def test_update_me_cannot_change_role(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.put(
        "/api/v1/users/me",
        json={"display_name": "Traveller", "role": "admin"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Traveller"
    assert data["role"] == "traveler"


@pytest.mark.asyncio
async def test_inactive_user_rejected(
    client: AsyncClient,
    db: AsyncSession,
    test_user: User,
    user_token: str,
):
    test_user.is_active = False
    await db.commit()

    headers = {"Authorization": f"Bearer {user_token}"}
    resp = await client.get("/api/v1/users/me", headers=headers)
    assert resp.status_code == 401
