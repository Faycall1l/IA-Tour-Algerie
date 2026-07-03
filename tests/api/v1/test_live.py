import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_post_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/live/posts", data={"caption": "hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_and_list_posts(client: AsyncClient, auth_headers: dict[str, str]):
    resp = await client.post(
        "/api/v1/live/posts",
        data={"caption": "Algiers is beautiful!"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    post = resp.json()
    assert post["caption"] == "Algiers is beautiful!"
    assert post["photo_url"] is not None

    feed = await client.get("/api/v1/live/posts")
    assert feed.status_code == 200
    data = feed.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["caption"] == "Algiers is beautiful!"


@pytest.mark.asyncio
async def test_get_single_post(client: AsyncClient, auth_headers: dict[str, str]):
    created = await client.post(
        "/api/v1/live/posts",
        data={"caption": "Hello from Tizi Ouzou!"},
        headers=auth_headers,
    )
    post_id = created.json()["id"]

    resp = await client.get(f"/api/v1/live/posts/{post_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == post_id


@pytest.mark.asyncio
async def test_get_missing_post_returns_404(client: AsyncClient):
    resp = await client.get("/api/v1/live/posts/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
