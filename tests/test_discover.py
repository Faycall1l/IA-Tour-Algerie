import uuid

import pytest
from app.models.experience import Experience
from app.models.poi import POI
from app.models.stay import Stay
from app.models.user import User
from app.models.wilaya import Wilaya
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


class TestDiscoverEndpoints:
    async def _seed_wilaya(self, db: AsyncSession) -> Wilaya:
        existing = await db.get(Wilaya, 1)
        if existing:
            return existing
        w = Wilaya(id=1, name_ar="أدرار", name_en="Adrar", name_fr="Adrar")
        db.add(w)
        await db.commit()
        await db.refresh(w)
        return w

    async def test_discover_wilaya_not_found(self, client: AsyncClient):
        resp = await client.get("/api/v1/discover/wilayas/999")
        assert resp.status_code == 404

    async def test_discover_empty_wilaya(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        resp = await client.get("/api/v1/discover/wilayas/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["wilaya_id"] == 1
        assert data["wilaya_name"] == "Adrar"
        assert data["pois"] == []
        assert data["experiences"] == []
        assert data["stays"] == []

    async def test_discover_with_pois_experiences_stays(
        self,
        client: AsyncClient,
        db: AsyncSession,
    ):
        await self._seed_wilaya(db)

        provider = User(id=uuid.uuid4(), phone="+213555888001", role="agency")
        db.add(provider)
        await db.commit()

        poi = POI(
            name="Grande Mosquée",
            category="religious",
            wilaya_id=1,
            latitude=36.737,
            longitude=3.068,
            description="Iconic mosque",
            entry_fee_dzd=0,
        )
        db.add(poi)
        await db.flush()

        exp = Experience(
            provider_id=provider.id,
            title="Guided Mosque Tour",
            category="tour",
            wilaya_id=1,
            price_dzd=1500,
            duration_hours=2,
            status="active",
        )
        db.add(exp)
        await db.flush()

        stay = Stay(
            provider_id=provider.id,
            name="Riad Test",
            property_type="riad",
            wilaya_id=1,
            price_per_night_dzd=8000,
            is_active=True,
        )
        db.add(stay)
        await db.commit()

        resp = await client.get("/api/v1/discover/wilayas/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["pois"]) == 1
        assert data["pois"][0]["name"] == "Grande Mosquée"
        assert len(data["experiences"]) == 1
        assert data["experiences"][0]["title"] == "Guided Mosque Tour"
        assert len(data["stays"]) == 1
        assert data["stays"][0]["name"] == "Riad Test"
        assert data["stays"][0]["price_per_night_dzd"] == 8000

    async def test_discover_excludes_inactive_stays(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        provider = User(id=uuid.uuid4(), phone="+213555888002", role="agency")
        db.add(provider)
        await db.commit()

        active = Stay(
            provider_id=provider.id,
            name="Active Stay",
            property_type="hotel",
            wilaya_id=1,
            price_per_night_dzd=5000,
            is_active=True,
        )
        inactive = Stay(
            provider_id=provider.id,
            name="Inactive Stay",
            property_type="hotel",
            wilaya_id=1,
            price_per_night_dzd=3000,
            is_active=False,
        )
        db.add_all([active, inactive])
        await db.commit()

        resp = await client.get("/api/v1/discover/wilayas/1")
        data = resp.json()
        assert len(data["stays"]) == 1
        assert data["stays"][0]["name"] == "Active Stay"

    async def test_discover_excludes_draft_experiences(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        provider = User(id=uuid.uuid4(), phone="+213555888003", role="agency")
        db.add(provider)
        await db.commit()

        active = Experience(
            provider_id=provider.id,
            title="Active Tour",
            category="tour",
            wilaya_id=1,
            price_dzd=1000,
            status="active",
        )
        draft = Experience(
            provider_id=provider.id,
            title="Draft Tour",
            category="tour",
            wilaya_id=1,
            price_dzd=500,
            status="draft",
        )
        db.add_all([active, draft])
        await db.commit()

        resp = await client.get("/api/v1/discover/wilayas/1")
        data = resp.json()
        assert len(data["experiences"]) == 1
        assert data["experiences"][0]["title"] == "Active Tour"

    async def test_experiences_by_poi(self, client: AsyncClient, db: AsyncSession):
        await self._seed_wilaya(db)
        provider = User(id=uuid.uuid4(), phone="+213555888004", role="guide")
        db.add(provider)
        await db.commit()

        poi = POI(name="Djamaa El Djazair", category="religious", wilaya_id=1)
        db.add(poi)
        await db.flush()

        exp = Experience(
            provider_id=provider.id,
            title="Mosque Visit with Guide",
            category="tour",
            wilaya_id=1,
            price_dzd=2000,
            description="Visit the beautiful Djamaa El Djazair mosque",
            status="active",
        )
        db.add(exp)
        await db.commit()

        resp = await client.get(f"/api/v1/discover/experiences/by-poi/{poi.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0

    async def test_experiences_by_poi_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/discover/experiences/by-poi/{uuid.uuid4()}")
        assert resp.status_code == 404
