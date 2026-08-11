"""Artisan API: nearest-transit walking edges on detail/list + route-to-artisan."""

import uuid
from unittest.mock import AsyncMock

import pytest
from app.api.deps import get_poi_transit_router
from app.main import app
from app.models.artisan import Artisan, ArtisanTransitAccess
from app.models.station import Station
from app.services.poi_transit_router import RoutePlan, StepCoordinate, WalkingStep
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def artisan_with_transit(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    station = Station(
        name="Gare Routière Alger",
        name_ar="محطة المسافرين",
        wilaya_id=16,
        latitude=36.7716,
        longitude=3.0601,
        station_type="bus",
        operator="SOGRAL",
    )
    artisan = Artisan(
        name="Atelier Bijoux Kabyles",
        craft_type="jewelry",
        wilaya_id=16,
        latitude=36.7712,
        longitude=3.0604,
        address="Rue des Bijoutiers",
        is_verified=True,
        metadata_={"osm_id": 999991, "osm_type": "node"},
    )
    db.add_all([station, artisan])
    await db.flush()
    db.add(
        ArtisanTransitAccess(
            artisan_id=artisan.id,
            station_id=station.id,
            distance_m=45.0,
            walking_time_min=1.0,
            rank=0,
        )
    )
    await db.commit()
    return artisan.id, station.id


async def test_get_artisan_includes_nearest_transit(client: AsyncClient, artisan_with_transit):
    artisan_id, station_id = artisan_with_transit
    resp = await client.get(f"/api/v1/artisans/{artisan_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Atelier Bijoux Kabyles"
    assert data["craft_type"] == "jewelry"
    nearest = data["nearest_transit"]
    assert len(nearest) == 1
    assert nearest[0]["station_id"] == str(station_id)
    assert nearest[0]["station_name"] == "Gare Routière Alger"
    assert nearest[0]["station_type"] == "bus"
    assert nearest[0]["operator"] == "SOGRAL"
    assert nearest[0]["rank"] == 0
    assert nearest[0]["distance_m"] == 45.0


async def test_list_artisans_includes_nearest_transit(
    client: AsyncClient, artisan_with_transit
):
    artisan_id, station_id = artisan_with_transit
    resp = await client.get("/api/v1/artisans?wilaya_id=16")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(
        item["id"] == str(artisan_id) and item["nearest_transit"][0]["rank"] == 0
        for item in items
    )


async def test_artisan_without_transit_has_empty_list(db: AsyncSession, client: AsyncClient):
    artisan = Artisan(
        name="Potier isolé",
        craft_type="pottery",
        wilaya_id=1,
        latitude=33.4,
        longitude=0.1,
    )
    db.add(artisan)
    await db.commit()
    resp = await client.get(f"/api/v1/artisans/{artisan.id}")
    assert resp.status_code == 200
    assert resp.json()["nearest_transit"] == []


async def test_route_to_artisan_returns_plan_and_transit(
    client: AsyncClient, artisan_with_transit
):
    artisan_id, _station_id = artisan_with_transit

    def make_plan():
        return RoutePlan(
            from_lat=36.77,
            from_lng=3.05,
            from_name="Your location",
            to_lat=36.7712,
            to_lng=3.0604,
            to_name="Atelier Bijoux Kabyles",
            total_walking_km=0.05,
            total_transit_km=0,
            total_transfers=0,
            total_estimated_minutes=5,
            steps=[
                WalkingStep(
                    from_location=StepCoordinate(36.77, 3.05, "Your location"),
                    to_location=StepCoordinate(36.7712, 3.0604, "Atelier Bijoux Kabyles"),
                    distance_km=0.05,
                    estimated_minutes=5,
                    description="Walk 0.1 km to Atelier Bijoux Kabyles.",
                )
            ],
            available_modes=["walking"],
            is_walking_only=True,
        )

    fake_router = AsyncMock()
    fake_router.route_to = AsyncMock(side_effect=lambda **kw: make_plan())
    app.dependency_overrides[get_poi_transit_router] = lambda: fake_router
    try:
        resp = await client.get(
            f"/api/v1/transport/route-to-artisan/{artisan_id}",
            params={"from_lat": 36.77, "from_lng": 3.05},
        )
    finally:
        app.dependency_overrides.pop(get_poi_transit_router, None)
    assert resp.status_code == 200
    data = resp.json()
    assert data["artisan_name"] == "Atelier Bijoux Kabyles"
    assert data["craft_type"] == "jewelry"
    assert data["plan"]["to"]["name"] == "Atelier Bijoux Kabyles"
    assert data["plan"]["is_walking_only"] is True
    assert data["nearest_transit"][0]["distance_m"] == 45.0


async def test_route_to_artisan_missing_404(client: AsyncClient):
    resp = await client.get(
        f"/api/v1/transport/route-to-artisan/{uuid.uuid4()}",
        params={"from_lat": 36.77, "from_lng": 3.05},
    )
    assert resp.status_code == 200
    assert "error" in resp.json()


async def test_route_to_artisan_no_coords(db: AsyncSession, client: AsyncClient):
    artisan = Artisan(
        name="Artisan sans position",
        craft_type="other",
        wilaya_id=1,
        latitude=None,
        longitude=None,
    )
    db.add(artisan)
    await db.commit()
    resp = await client.get(
        f"/api/v1/transport/route-to-artisan/{artisan.id}",
        params={"from_lat": 36.77, "from_lng": 3.05},
    )
    assert resp.status_code == 200
    assert "error" in resp.json()
