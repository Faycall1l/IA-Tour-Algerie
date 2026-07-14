import uuid

import pytest
from app.models.experience import Experience
from app.models.live_post import LivePost
from app.models.poi import POI
from app.models.price_report import PriceReport
from app.models.provider_profile import ProviderProfile
from app.models.review import Review
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


# ── Price Reports ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_price_reports(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    report = PriceReport(
        user_id=test_user.id,
        origin_wilaya_id=1,
        dest_wilaya_id=2,
        transport_mode="bus",
        price_dzd=500,
    )
    db.add(report)
    await db.commit()

    resp = await client.get("/api/v1/admin/price-reports", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert data["items"][0]["confidence"] == "user"


@pytest.mark.asyncio
async def test_verify_price_report(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    report = PriceReport(
        user_id=test_user.id,
        origin_wilaya_id=1,
        dest_wilaya_id=3,
        transport_mode="taxi",
        price_dzd=1000,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    resp = await client.put(
        f"/api/v1/admin/price-reports/{report.id}/verify",
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "Price report verified"

    await db.refresh(report)
    assert report.confidence == "verified"


@pytest.mark.asyncio
async def test_reject_price_report(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    report = PriceReport(
        user_id=test_user.id,
        origin_wilaya_id=1,
        dest_wilaya_id=4,
        transport_mode="train",
        price_dzd=800,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)

    resp = await client.delete(
        f"/api/v1/admin/price-reports/{report.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200

    # Verify deletion via API
    resp2 = await client.get(f"/api/v1/admin/price-reports", headers=admin_headers)
    assert resp2.status_code == 200
    assert not any(item["id"] == str(report.id) for item in resp2.json()["items"])


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
async def test_admin_delete_review(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    poi = POI(name="Test POI", category="cultural", wilaya_id=1, latitude=36, longitude=3)
    db.add(poi)
    await db.flush()
    review = Review(
        user_id=test_user.id,
        poi_id=poi.id,
        overall_score=4,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    resp = await client.delete(
        f"/api/v1/admin/reviews/{review.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_admin_delete_live_post(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    post = LivePost(
        user_id=test_user.id,
        photo_url="https://example.com/photo.jpg",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    resp = await client.delete(
        f"/api/v1/admin/live-posts/{post.id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_moderate_live_post(
    client: AsyncClient,
    admin_headers: dict[str, str],
    test_user: User,
    db: AsyncSession,
):
    post = LivePost(
        user_id=test_user.id,
        photo_url="https://example.com/photo2.jpg",
        is_moderated=False,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    resp = await client.put(
        f"/api/v1/admin/live-posts/{post.id}/moderate",
        headers=admin_headers,
    )
    assert resp.status_code == 200

    await db.refresh(post)
    assert post.is_moderated is True


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
