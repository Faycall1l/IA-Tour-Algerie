import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def poi_id(client: AsyncClient, auth_headers: dict[str, str]) -> str:
    resp = await client.post(
        "/api/v1/pois",
        json={
            "name": "Test POI",
            "category": "historical",
            "wilaya_id": 16,
        },
        headers=auth_headers,
    )
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_review_requires_auth(client: AsyncClient, poi_id: str):
    resp = await client.post(
        "/api/v1/reviews",
        json={"poi_id": poi_id, "overall_score": 4, "text": "Great place"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_reviews(
    client: AsyncClient,
    auth_headers: dict[str, str],
    poi_id: str,
):
    resp = await client.post(
        "/api/v1/reviews",
        json={
            "poi_id": poi_id,
            "overall_score": 4.5,
            "text": "Amazing historical site",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["overall_score"] == 4.5
    assert data["text"] == "Amazing historical site"
    assert data["is_verified"] is False

    list_resp = await client.get("/api/v1/reviews", params={"poi_id": poi_id})
    assert list_resp.status_code == 200
    feed = list_resp.json()
    assert feed["total"] == 1
    assert feed["items"][0]["id"] == data["id"]


@pytest.mark.asyncio
async def test_duplicate_review_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
    poi_id: str,
):
    await client.post(
        "/api/v1/reviews",
        json={"poi_id": poi_id, "overall_score": 3, "text": "OK"},
        headers=auth_headers,
    )
    resp = await client.post(
        "/api/v1/reviews",
        json={"poi_id": poi_id, "overall_score": 4, "text": "Better"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_review_invalid_score(
    client: AsyncClient,
    auth_headers: dict[str, str],
    poi_id: str,
):
    resp = await client.post(
        "/api/v1/reviews",
        json={"poi_id": poi_id, "overall_score": 6, "text": "Invalid"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_missing_poi(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/reviews",
        json={
            "poi_id": "00000000-0000-0000-0000-000000000000",
            "overall_score": 4,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest_asyncio.fixture
async def alt_auth_headers(db) -> list[dict[str, str]]:
    from app.core.security import create_access_token
    from app.models.user import User

    headers = []
    for i in range(5):
        user = User(id=uuid.uuid4(), phone=f"+21355590{i:04d}")
        db.add(user)
        await db.flush()
        token = create_access_token(str(user.id), user.role)
        headers.append({"Authorization": f"Bearer {token}"})
    await db.commit()
    return headers


@pytest.mark.asyncio
async def test_poi_rating_aggregation(
    client: AsyncClient,
    auth_headers: dict[str, str],
    alt_auth_headers: list[dict[str, str]],
):
    poi = await client.post(
        "/api/v1/pois",
        json={"name": "Ratable POI", "category": "park", "wilaya_id": 16},
        headers=auth_headers,
    )
    pid = poi.json()["id"]

    for score, hdr in zip([5, 4, 5, 3, 5], alt_auth_headers):
        await client.post(
            "/api/v1/reviews",
            json={"poi_id": pid, "overall_score": score},
            headers=hdr,
        )

    resp = await client.get(f"/api/v1/reviews/ratings/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 5
    assert data["average_score"] == 4.4
    assert data["distribution"] == {"3": 1, "4": 1, "5": 3}


@pytest.mark.asyncio
async def test_rating_no_reviews(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    poi = await client.post(
        "/api/v1/pois",
        json={"name": "Empty POI", "category": "other", "wilaya_id": 16},
        headers=auth_headers,
    )
    pid = poi.json()["id"]

    resp = await client.get(f"/api/v1/reviews/ratings/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_reviews"] == 0
    assert data["average_score"] == 0.0
    assert data["distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}


@pytest.mark.asyncio
async def test_rating_missing_poi(client: AsyncClient):
    resp = await client.get("/api/v1/reviews/ratings/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
