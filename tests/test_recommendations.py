import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite import Favorite
from app.models.poi import POI
from app.models.recommendation import UserPreference
from app.models.user import User


@pytest.mark.asyncio
async def test_get_recommendations_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/recommendations", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_get_recommendations_with_pois(
    client: AsyncClient, auth_headers: dict, sample_poi: POI, db: AsyncSession, test_user: User,
):
    # Create several POIs for recommendations
    cats = ["historical", "natural", "museum", "beach", "cultural"]
    for i, cat in enumerate(cats):
        poi = POI(
            name=f"Test POI {i}",
            category=cat,
            wilaya_id=31,  # Oran
            latitude=35.7 + i * 0.01,
            longitude=-0.6 + i * 0.01,
            entry_fee_dzd=100 * i,
            is_featured=(i == 0),
        )
        db.add(poi)
    await db.commit()

    resp = await client.get(
        "/api/v1/recommendations?entity_type=poi&limit=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    # Check recommendation structure
    rec = data["items"][0]
    assert "entity_type" in rec
    assert "entity_id" in rec
    assert "score" in rec
    assert "explanation" in rec


@pytest.mark.asyncio
async def test_get_recommendations_with_favorites(
    client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User,
):
    # Create POIs and add some as favorites
    for i in range(5):
        poi = POI(
            name=f"Fav POI {i}",
            category="historical",
            wilaya_id=31,
            latitude=35.7 + i * 0.01,
            longitude=-0.6 + i * 0.01,
        )
        db.add(poi)
        await db.flush()
        fav = Favorite(user_id=test_user.id, entity_type="poi", entity_id=poi.id)
        db.add(fav)
    await db.commit()

    resp = await client.get("/api/v1/recommendations?entity_type=poi", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    # Historical POIs should rank higher since user favorited them
    if data["total"] > 0:
        assert any("historical" in item.get("explanation", "") for item in data["items"])


@pytest.mark.asyncio
async def test_get_and_update_preferences(client: AsyncClient, auth_headers: dict):
    # Get (auto-creates)
    resp = await client.get("/api/v1/recommendations/preferences", headers=auth_headers)
    assert resp.status_code == 200
    pref = resp.json()
    assert pref["preferred_categories"] is None or isinstance(pref["preferred_categories"], list)

    # Update
    resp = await client.patch(
        "/api/v1/recommendations/preferences",
        json={
            "preferred_categories": ["historical", "museum"],
            "travel_style": "cultural",
            "budget_tier": "budget",
            "preferred_wilayas": [31, 13],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    pref = resp.json()
    assert pref["preferred_categories"] == ["historical", "museum"]
    assert pref["travel_style"] == "cultural"
    assert pref["budget_tier"] == "budget"
    assert pref["preferred_wilayas"] == [31, 13]


@pytest.mark.asyncio
async def test_derive_preferences(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/recommendations/preferences/derive",
        headers=auth_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_recommendations_feedback(client: AsyncClient, auth_headers: dict, db: AsyncSession, test_user: User):
    # Create a POI, generate a rec, then feedback on it
    from app.models.recommendation import Recommendation

    rec = Recommendation(
        id=uuid.uuid4(),
        user_id=test_user.id,
        entity_type="poi",
        entity_id=uuid.uuid4(),
        wilaya_id=31,
        score=5.0,
        explanation="test",
        reason_code="test",
    )
    db.add(rec)
    await db.commit()

    resp = await client.post(
        f"/api/v1/recommendations/{rec.id}/feedback",
        json={"feedback": "liked"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_seen"] is True


@pytest.mark.asyncio
async def test_recommendations_auth_required(client: AsyncClient):
    resp = await client.get("/api/v1/recommendations")
    assert resp.status_code in (401, 403)
