import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_poi_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/pois",
        json={
            "name": "Basilique Notre-Dame d'Afrique",
            "category": "religious",
            "wilaya_id": 31,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_pois(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/pois",
        json={
            "name": "Basilique Notre-Dame d'Afrique",
            "category": "religious",
            "wilaya_id": 31,
            "latitude": 35.789,
            "longitude": -0.445,
            "description": "A beautiful basilica in Oran",
        },
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Basilique Notre-Dame d'Afrique"
    assert data["category"] == "religious"
    assert data["wilaya_id"] == 31

    list_resp = await client.get("/api/v1/pois")
    assert list_resp.status_code == 200
    feed = list_resp.json()
    assert feed["total"] >= 1
    assert feed["items"][0]["id"] == data["id"]


@pytest.mark.asyncio
async def test_create_poi_invalid_wilaya(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/pois",
        json={
            "name": "Nowhere",
            "category": "other",
            "wilaya_id": 999,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_poi_invalid_category(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/pois",
        json={
            "name": "Bad Category",
            "category": "invalid_cat",
            "wilaya_id": 16,
        },
        headers=admin_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_poi_by_id(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    created = await client.post(
        "/api/v1/pois",
        json={
            "name": "Tassili n'Ajjer",
            "category": "natural",
            "wilaya_id": 11,
        },
        headers=admin_headers,
    )
    poi_id = created.json()["id"]

    resp = await client.get(f"/api/v1/pois/{poi_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Tassili n'Ajjer"


@pytest.mark.asyncio
async def test_get_missing_poi_404(client: AsyncClient):
    resp = await client.get("/api/v1/pois/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_pois(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    await client.post(
        "/api/v1/pois",
        json={"name": "Le Jardin d'Essai", "category": "park", "wilaya_id": 16},
        headers=admin_headers,
    )
    await client.post(
        "/api/v1/pois",
        json={"name": "Casbah d'Alger", "category": "historical", "wilaya_id": 16},
        headers=admin_headers,
    )

    resp = await client.get("/api/v1/pois", params={"search": "Casbah"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Casbah d'Alger"


@pytest.mark.asyncio
async def test_filter_pois_by_wilaya_and_category(
    client: AsyncClient,
    admin_headers: dict[str, str],
):
    for name, cat, wid in [
        ("Notre-Dame d'Afrique", "religious", 31),
        ("Santa Cruz Fort", "historical", 31),
        ("Basilique Saint-Augustin", "religious", 16),
    ]:
        await client.post(
            "/api/v1/pois",
            json={"name": name, "category": cat, "wilaya_id": wid},
            headers=admin_headers,
        )

    resp = await client.get("/api/v1/pois", params={"wilaya_id": 31, "category": "religious"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Notre-Dame d'Afrique"
