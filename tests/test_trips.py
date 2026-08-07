import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestTripEndpoints:
    async def test_create_trip(self, client: AsyncClient, auth_headers: dict[str, str], sample_poi):  # noqa: ARG002
        payload = {
            "title": "Weekend in Tizi Ouzou",
            "total_budget_dzd": 15000,
            "wilaya_ids": [15],
        }
        resp = await client.post("/api/v1/trips", json=payload, headers=auth_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == payload["title"]
        assert data["total_budget_dzd"] == payload["total_budget_dzd"]
        assert data["status"] == "active"
        assert data["days"] == []
        assert data["budget_spent"] == 0
        assert data["budget_remaining"] == payload["total_budget_dzd"]

    async def test_create_trip_with_dates(self, client: AsyncClient, auth_headers: dict[str, str]):
        """Regression: date strings previously 500'd (str bound to Date column)."""
        resp = await client.post(
            "/api/v1/trips",
            json={
                "title": "Dates trip",
                "start_date": "2026-08-10",
                "end_date": "2026-08-12",
                "total_days": 3,
                "wilaya_ids": [16],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["start_date"] == "2026-08-10"
        assert data["end_date"] == "2026-08-12"

    async def test_list_trips(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.get("/api/v1/trips", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_get_trip(self, client: AsyncClient, auth_headers: dict[str, str]):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Get test", "wilaya_ids": [1]},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]
        resp = await client.get(f"/api/v1/trips/{trip_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == trip_id

    async def test_get_trip_not_found(self, client: AsyncClient, auth_headers: dict[str, str]):
        resp = await client.get(f"/api/v1/trips/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_update_trip(self, client: AsyncClient, auth_headers: dict[str, str]):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Update me", "wilaya_ids": [1]},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]
        resp = await client.put(
            f"/api/v1/trips/{trip_id}",
            json={"title": "Updated", "total_budget_dzd": 20000},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"
        assert resp.json()["total_budget_dzd"] == 20000

    async def test_delete_trip(self, client: AsyncClient, auth_headers: dict[str, str]):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Delete me", "wilaya_ids": [1]},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]
        resp = await client.delete(f"/api/v1/trips/{trip_id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_add_trip_item_poi(
        self, client: AsyncClient, auth_headers: dict[str, str], sample_poi
    ):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Trip with POI"},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/trips/{trip_id}/items",
            json={
                "item_type": "poi",
                "item_id": str(sample_poi.id),
                "day_number": 1,
                "time_slot": "morning",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["days"]) == 1
        assert len(data["days"][0]["items"]) == 1
        item = data["days"][0]["items"][0]
        assert item["item_name"] == sample_poi.name
        assert item["item_type"] == "poi"

    async def test_add_trip_item_poi_not_found(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Trip bad POI", "wilaya_ids": [1]},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]

        resp = await client.post(
            f"/api/v1/trips/{trip_id}/items",
            json={
                "item_type": "poi",
                "item_id": str(uuid.uuid4()),
                "day_number": 1,
                "time_slot": "morning",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_trip_item(
        self, client: AsyncClient, auth_headers: dict[str, str], sample_poi
    ):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Update item"},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]

        add = await client.post(
            f"/api/v1/trips/{trip_id}/items",
            json={
                "item_type": "poi",
                "item_id": str(sample_poi.id),
                "day_number": 1,
                "time_slot": "morning",
            },
            headers=auth_headers,
        )
        item_id = add.json()["days"][0]["items"][0]["id"]

        resp = await client.put(
            f"/api/v1/trips/{trip_id}/items/{item_id}",
            json={"time_slot": "afternoon", "sort_order": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        item = resp.json()["days"][0]["items"][0]
        assert item["time_slot"] == "afternoon"

    async def test_delete_trip_item(
        self, client: AsyncClient, auth_headers: dict[str, str], sample_poi
    ):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Delete item"},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]

        add = await client.post(
            f"/api/v1/trips/{trip_id}/items",
            json={
                "item_type": "poi",
                "item_id": str(sample_poi.id),
                "day_number": 1,
                "time_slot": "morning",
            },
            headers=auth_headers,
        )
        item_id = add.json()["days"][0]["items"][0]["id"]

        resp = await client.delete(
            f"/api/v1/trips/{trip_id}/items/{item_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        if data["days"]:
            assert len(data["days"][0]["items"]) == 0

    async def test_optimize_trip(
        self, client: AsyncClient, auth_headers: dict[str, str], sample_poi
    ):
        create = await client.post(
            "/api/v1/trips",
            json={"title": "Optimize"},
            headers=auth_headers,
        )
        trip_id = create.json()["id"]

        await client.post(
            f"/api/v1/trips/{trip_id}/items",
            json={
                "item_type": "poi",
                "item_id": str(sample_poi.id),
                "day_number": 1,
                "time_slot": "morning",
            },
            headers=auth_headers,
        )

        resp = await client.post(
            f"/api/v1/trips/{trip_id}/optimize",
            headers=auth_headers,
        )
        assert resp.status_code == 200

    async def test_trip_brief(self, client: AsyncClient, db):
        from app.models.wilaya import Wilaya
        from sqlalchemy import select

        existing = await db.execute(select(Wilaya).where(Wilaya.id == 1))
        if not existing.scalar_one_or_none():
            db.add(Wilaya(id=1, name_ar="أدرار", name_en="Adrar", name_fr="Adrar"))
            await db.commit()

        resp = await client.get("/api/v1/trips/brief/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["wilaya_id"] == 1
        assert "wilaya_name" in data

    async def test_trip_brief_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/trips/brief/99999")
        assert resp.status_code == 404

    async def test_unauthorized_access(self, client: AsyncClient):
        resp = await client.get("/api/v1/trips")
        assert resp.status_code == 401

    async def test_filter_trips_by_status(self, client: AsyncClient, auth_headers: dict[str, str]):
        await client.post(
            "/api/v1/trips",
            json={"title": "Active trip", "wilaya_ids": [1]},
            headers=auth_headers,
        )
        resp = await client.get("/api/v1/trips?status=active", headers=auth_headers)
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "active"
