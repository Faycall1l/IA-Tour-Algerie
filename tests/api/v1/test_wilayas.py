import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_wilayas(client: AsyncClient):
    resp = await client.get("/api/v1/wilayas")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 58
    assert data[0]["name_fr"] == "Adrar"
    assert data[0]["name_ar"] == "أدرار"


@pytest.mark.asyncio
async def test_search_wilayas(client: AsyncClient):
    resp = await client.get("/api/v1/wilayas?search=Alger")
    assert resp.status_code == 200
    data = resp.json()
    assert any(w["name_fr"] == "Alger" for w in data)


@pytest.mark.asyncio
async def test_get_wilaya(client: AsyncClient):
    resp = await client.get("/api/v1/wilayas/16")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name_en"] == "Algiers"


@pytest.mark.asyncio
async def test_get_missing_wilaya_404(client: AsyncClient):
    resp = await client.get("/api/v1/wilayas/999")
    assert resp.status_code == 404
