import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.wilaya import Wilaya
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestStayEndpoints:

    async def _seed_wilaya(self, db: AsyncSession) -> Wilaya:
        existing = await db.get(Wilaya, 1)
        if existing:
            return existing
        w = Wilaya(id=1, name_ar="أدرار", name_en="Adrar", name_fr="Adrar")
        db.add(w)
        await db.commit()
        await db.refresh(w)
        return w

    async def _make_hotel_user(self, db: AsyncSession) -> User:
        u = User(id=uuid.uuid4(), phone="+213555999001", role="hotel")
        db.add(u)
        await db.commit()
        await db.refresh(u)
        return u

    async def test_create_stay_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/v1/stays", json={"name": "Test"})
        assert resp.status_code == 401

    async def test_create_stay_requires_hotel_role(self, client: AsyncClient, db: AsyncSession, auth_headers: dict[str, str]):
        resp = await client.post(
            "/api/v1/stays",
            json={"name": "Test Stay", "property_type": "hotel", "wilaya_id": 1, "price_per_night_dzd": 5000},
            headers=auth_headers,
        )
        assert resp.status_code == 403

    async def test_create_and_get_stay(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        user = await self._make_hotel_user(db)
        from app.core.security import create_access_token
        token = create_access_token(str(user.id), "hotel")
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "name": "Riad El Djemaa",
            "property_type": "riad",
            "wilaya_id": 1,
            "price_per_night_dzd": 8000,
            "description": "Beautiful riad in the casbah",
            "amenities": ["wifi", "breakfast", "ac"],
            "max_guests": 4,
            "total_rooms": 3,
            "check_in_time": "14:00",
            "check_out_time": "11:00",
        }
        resp = await client.post("/api/v1/stays", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == payload["name"]
        assert data["property_type"] == "riad"
        assert data["price_per_night_dzd"] == 8000
        assert data["is_active"] is True
        assert data["provider_id"] == str(user.id)
        assert data["amenities"] == ["wifi", "breakfast", "ac"]

        stay_id = data["id"]
        resp2 = await client.get(f"/api/v1/stays/{stay_id}")
        assert resp2.status_code == 200
        assert resp2.json()["name"] == payload["name"]

    async def test_list_stays_empty(self, client: AsyncClient):
        resp = await client.get("/api/v1/stays")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_stays_with_filters(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        user = await self._make_hotel_user(db)
        from app.core.security import create_access_token
        token = create_access_token(str(user.id), "hotel")
        headers = {"Authorization": f"Bearer {token}"}

        await client.post(
            "/api/v1/stays",
            json={"name": "Hotel A", "property_type": "hotel", "wilaya_id": 1, "price_per_night_dzd": 5000},
            headers=headers,
        )
        await client.post(
            "/api/v1/stays",
            json={"name": "Riad B", "property_type": "riad", "wilaya_id": 1, "price_per_night_dzd": 12000},
            headers=headers,
        )

        # Filter by property_type
        resp = await client.get("/api/v1/stays?property_type=riad")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Riad B"

        # Filter by price range
        resp = await client.get("/api/v1/stays?min_price=10000&max_price=15000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    async def test_get_stay_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/stays/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_update_stay(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        user = await self._make_hotel_user(db)
        from app.core.security import create_access_token
        token = create_access_token(str(user.id), "hotel")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post(
            "/api/v1/stays",
            json={"name": "Old Name", "property_type": "hotel", "wilaya_id": 1, "price_per_night_dzd": 5000},
            headers=headers,
        )
        stay_id = create.json()["id"]

        resp = await client.put(
            f"/api/v1/stays/{stay_id}",
            json={"name": "New Name", "price_per_night_dzd": 7000},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"
        assert resp.json()["price_per_night_dzd"] == 7000

    async def test_update_other_users_stay_forbidden(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        user = await self._make_hotel_user(db)
        from app.core.security import create_access_token
        token = create_access_token(str(user.id), "hotel")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post(
            "/api/v1/stays",
            json={"name": "Mine", "property_type": "hotel", "wilaya_id": 1, "price_per_night_dzd": 5000},
            headers=headers,
        )
        stay_id = create.json()["id"]

        other = User(id=uuid.uuid4(), phone="+213555999002", role="hotel")
        db.add(other)
        await db.commit()
        other_token = create_access_token(str(other.id), "hotel")
        other_headers = {"Authorization": f"Bearer {other_token}"}

        resp = await client.put(
            f"/api/v1/stays/{stay_id}",
            json={"name": "Hacked"},
            headers=other_headers,
        )
        assert resp.status_code == 403

    async def test_delete_stay(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        user = await self._make_hotel_user(db)
        from app.core.security import create_access_token
        token = create_access_token(str(user.id), "hotel")
        headers = {"Authorization": f"Bearer {token}"}

        create = await client.post(
            "/api/v1/stays",
            json={"name": "Delete me", "property_type": "hotel", "wilaya_id": 1, "price_per_night_dzd": 5000},
            headers=headers,
        )
        stay_id = create.json()["id"]
        resp = await client.delete(f"/api/v1/stays/{stay_id}", headers=headers)
        assert resp.status_code == 204
