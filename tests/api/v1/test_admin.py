import uuid

import pytest
from app.models.experience import Experience
from app.models.poi import POI
from app.models.provider_profile import ProviderProfile
from app.models.user import User
from app.models.wilaya import Wilaya
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_non_admin_cannot_access(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    resp = await client.get("/api/v1/admin/users", headers=auth_headers)
    assert resp.status_code == 403

    resp = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200


# ── Users ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_users(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
):
    resp = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(u["phone"] == test_user.phone for u in data["items"])


@pytest.mark.asyncio
async def test_set_user_role(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
):
    resp = await client.put(
        f"/api/v1/admin/users/{test_user.id}/role",
        headers=admin_headers,
        json={"role": "guide"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "guide"


@pytest.mark.asyncio
async def test_toggle_user_verification(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
):
    assert test_user.is_verified is False

    resp = await client.put(
        f"/api/v1/admin/users/{test_user.id}/verify",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_verified"] is True


# ── Provider Profiles ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_providers(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    profile = ProviderProfile(
        user_id=test_user.id,
        provider_type="guide",
    )
    db.add(profile)
    await db.commit()

    resp = await client.get("/api/v1/admin/providers", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_approve_provider(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    profile = ProviderProfile(
        user_id=test_user.id,
        provider_type="agency",
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    assert profile.is_verified is False

    resp = await client.put(
        f"/api/v1/admin/providers/{profile.id}/approve",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Provider profile approved"

    await db.refresh(profile)
    assert profile.is_verified is True


# ── Content Moderation ─────────────────────────────────────────────



@pytest.mark.asyncio
async def test_admin_delete_experience(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    experience = Experience(
        provider_id=test_user.id,
        title="Test Experience",
        category="tour",
        wilaya_id=1,
        status="active",
    )
    db.add(experience)
    await db.commit()
    await db.refresh(experience)

    resp = await client.delete(
        f"/api/v1/admin/experiences/{experience.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200
