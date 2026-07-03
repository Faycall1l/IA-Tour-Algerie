import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_report_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 25,
            "transport_mode": "taxi",
            "price_dzd": 1500,
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_reports(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 25,
            "transport_mode": "taxi",
            "price_dzd": 1500,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["origin_wilaya_id"] == 16
    assert data["dest_wilaya_id"] == 25
    assert data["transport_mode"] == "taxi"
    assert data["price_dzd"] == 1500.0

    list_resp = await client.get("/api/v1/prices")
    assert list_resp.status_code == 200
    feed = list_resp.json()
    assert feed["total"] >= 1


@pytest.mark.asyncio
async def test_create_report_same_wilaya_fails(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 16,
            "transport_mode": "taxi",
            "price_dzd": 500,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_report_invalid_wilaya(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    resp = await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 999,
            "dest_wilaya_id": 25,
            "transport_mode": "taxi",
            "price_dzd": 500,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_estimate_returns_prices(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    prices = [1200, 1500, 1300, 1800, 1400]
    for p in prices:
        await client.post(
            "/api/v1/prices",
            json={
                "origin_wilaya_id": 16,
                "dest_wilaya_id": 25,
                "transport_mode": "taxi",
                "price_dzd": p,
            },
            headers=auth_headers,
        )

    resp = await client.get(
        "/api/v1/prices/estimate",
        params={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 25,
            "transport_mode": "taxi",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["range"]["min"] == 1200
    assert data["range"]["max"] == 1800
    assert data["range"]["median"] == 1400
    assert data["range"]["count"] == 5
    assert "Algiers" in data["advice"]
    assert "Constantine" in data["advice"]


@pytest.mark.asyncio
async def test_estimate_no_data(
    client: AsyncClient,
):
    resp = await client.get(
        "/api/v1/prices/estimate",
        params={
            "origin_wilaya_id": 1,
            "dest_wilaya_id": 2,
            "transport_mode": "bus",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["range"] is None
    assert data["advice"] is None


@pytest.mark.asyncio
async def test_filter_by_transport_mode(
    client: AsyncClient,
    auth_headers: dict[str, str],
):
    await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 25,
            "transport_mode": "taxi",
            "price_dzd": 1500,
        },
        headers=auth_headers,
    )
    await client.post(
        "/api/v1/prices",
        json={
            "origin_wilaya_id": 16,
            "dest_wilaya_id": 25,
            "transport_mode": "bus",
            "price_dzd": 800,
        },
        headers=auth_headers,
    )

    resp = await client.get("/api/v1/prices", params={"transport_mode": "bus"})
    assert resp.status_code == 200
    feed = resp.json()
    assert all(r["transport_mode"] == "bus" for r in feed["items"])
