import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.station import Station, TransportLine
from app.models.transport_operator import TransportOperator
from app.models.wilaya_distance import WilayaDistance
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def sample_wilaya_distances(db: AsyncSession):
    distances = [
        WilayaDistance(
            origin_wilaya_id=16,
            dest_wilaya_id=31,
            driving_distance_km=400,
            driving_time_minutes=240,
            road_classification="autoroute",
        ),
        WilayaDistance(
            origin_wilaya_id=31,
            dest_wilaya_id=16,
            driving_distance_km=400,
            driving_time_minutes=240,
            road_classification="autoroute",
        ),
        WilayaDistance(
            origin_wilaya_id=16,
            dest_wilaya_id=25,
            driving_distance_km=450,
            driving_time_minutes=270,
            road_classification="national",
        ),
    ]
    db.add_all(distances)
    await db.commit()
    return distances


@pytest.fixture
async def sample_operators(db: AsyncSession):
    ops = [
        TransportOperator(
            name="SNTF",
            name_ar="الشركة الوطنية للنقل بالسكك الحديدية",
            mode="train",
            is_active=True,
            phone="+213 21 63 30 00",
            website="https://sntf.dz",
        ),
        TransportOperator(
            name="Air Algérie",
            name_ar="الخطوط الجوية الجزائرية",
            mode="flight",
            is_active=True,
            phone="+213 21 66 40 00",
            website="https://airalgerie.dz",
        ),
    ]
    db.add_all(ops)
    await db.commit()
    return ops


@pytest.fixture
async def sample_stations(db: AsyncSession):
    line = TransportLine(
        id=uuid.uuid4(),
        name="Ligne 1 Train",
        mode="train",
        operator="SNTF",
        is_active=True,
    )
    db.add(line)
    await db.flush()
    stations = [
        Station(
            id=uuid.uuid4(),
            name="Gare d'Alger",
            station_type="train",
            latitude=36.75,
            longitude=3.06,
            wilaya_id=16,
            operator="SNTF",
        ),
        Station(
            id=uuid.uuid4(),
            name="Gare d'Oran",
            station_type="train",
            latitude=35.69,
            longitude=-0.63,
            wilaya_id=31,
            operator="SNTF",
        ),
    ]
    db.add_all(stations)
    await db.commit()
    return stations, line


# ── GET /transport/routes/{origin}/{dest} ──────────────────────────


@pytest.mark.asyncio
async def test_get_route_returns_options(
    client: AsyncClient,
    sample_wilaya_distances: list,  # noqa: ARG001  # seeds DB rows
):
    mock_opt = MagicMock()
    mock_opt.mode = "train"
    mock_opt.line_name = "SNTF Alger-Oran"
    mock_opt.operator = "SNTF"
    mock_opt.cost_dzd = 1500
    mock_opt.duration_min = 240
    mock_opt.schedule = "08:00-20:00"
    mock_opt.pricing = {"1st": 2500, "2nd": 1500}
    mock_opt.transfers = 0
    mock_opt.contacts = []

    with patch("app.api.v1.endpoints.transport.MultiModalRouter") as mock_router:
        mock_router.return_value.get_inter_wilaya_options = AsyncMock(return_value=[mock_opt])
        resp = await client.get("/api/v1/transport/routes/16/31")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_wilaya_id"] == 16
    assert data["dest_wilaya_id"] == 31
    assert len(data["options"]) == 1
    assert data["options"][0]["mode"] == "train"
    assert data["options"][0]["cost_dzd"] == 1500


@pytest.mark.asyncio
async def test_get_route_fallback_to_flat(
    client: AsyncClient,
    sample_wilaya_distances: list,  # noqa: ARG001  # seeds the DB rows
):
    with patch("app.api.v1.endpoints.transport.MultiModalRouter") as mock_router:
        mock_router.return_value.get_inter_wilaya_options = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/transport/routes/16/31")
    assert resp.status_code == 200
    data = resp.json()
    assert "driving_distance_km" in data
    assert data["driving_distance_km"] == 400


@pytest.mark.asyncio
async def test_get_route_no_route(client: AsyncClient):
    with patch("app.api.v1.endpoints.transport.MultiModalRouter") as mock_router:
        mock_router.return_value.get_inter_wilaya_options = AsyncMock(return_value=[])
        resp = await client.get("/api/v1/transport/routes/1/58")
    assert resp.status_code == 200
    data = resp.json()
    assert data["error"] == "No route found"


# ── GET /transport/routes/from/{origin} ────────────────────────────


@pytest.mark.asyncio
async def test_get_routes_from(
    client: AsyncClient,
    sample_wilaya_distances: list,  # noqa: ARG001  # seeds the DB rows
):
    resp = await client.get("/api/v1/transport/routes/from/16")
    assert resp.status_code == 200
    data = resp.json()
    assert data["origin_wilaya_id"] == 16
    assert len(data["destinations"]) >= 1
    dests = [d["dest_wilaya_id"] for d in data["destinations"]]
    assert 31 in dests


@pytest.mark.asyncio
async def test_get_routes_from_no_data(client: AsyncClient):
    resp = await client.get("/api/v1/transport/routes/from/58")
    assert resp.status_code == 200
    data = resp.json()
    assert data["destinations"] == []


# ── GET /transport/stations ────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_stations(
    client: AsyncClient,
    sample_stations: tuple,
):
    from app.main import app

    stations, line = sample_stations
    mock_routing = app.state.transit_routing
    mock_routing.list_stations = AsyncMock(
        return_value=[
            {
                "id": str(s.id),
                "name": s.name,
                "station_type": s.station_type,
                "wilaya_id": s.wilaya_id,
            }
            for s in stations
        ]
    )
    resp = await client.get("/api/v1/transport/stations")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_stations_filter_type(
    client: AsyncClient,
    sample_stations: tuple,
):
    from app.main import app

    stations, line = sample_stations
    mock_routing = app.state.transit_routing
    mock_routing.list_stations = AsyncMock(
        return_value=[
            {"id": str(stations[0].id), "name": stations[0].name, "station_type": "train"}
        ]
    )
    resp = await client.get("/api/v1/transport/stations?type=train")
    assert resp.status_code == 200
    data = resp.json()
    for s in data:
        assert s["station_type"] == "train"


@pytest.mark.asyncio
async def test_list_stations_filter_wilaya(
    client: AsyncClient,
    sample_stations: tuple,
):
    from app.main import app

    mock_routing = app.state.transit_routing
    mock_routing.list_stations = AsyncMock(
        return_value=[
            {"id": str(sample_stations[0][0].id), "name": "Gare d'Alger", "wilaya_id": 16}
        ]
    )
    resp = await client.get("/api/v1/transport/stations?wilaya_id=16")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    for s in data:
        assert s["wilaya_id"] == 16


# ── GET /transport/lines ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_lines(
    client: AsyncClient,
    sample_stations: tuple,
):
    from app.main import app

    mock_routing = app.state.transit_routing
    mock_routing.list_lines = AsyncMock(
        return_value=[
            {
                "id": str(sample_stations[1].id),
                "name": "Ligne 1 Train",
                "mode": "train",
                "operator": "SNTF",
            }
        ]
    )
    resp = await client.get("/api/v1/transport/lines")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_list_lines_filter_mode(
    client: AsyncClient,
    sample_stations: tuple,
):
    from app.main import app

    mock_routing = app.state.transit_routing
    mock_routing.list_lines = AsyncMock(
        return_value=[{"id": str(sample_stations[1].id), "name": "Ligne 1 Train", "mode": "train"}]
    )
    resp = await client.get("/api/v1/transport/lines?mode=train")
    assert resp.status_code == 200
    data = resp.json()
    for line in data:
        assert line["mode"] == "train"


# ── GET /transport/operators ───────────────────────────────────────


@pytest.mark.asyncio
async def test_list_operators(
    client: AsyncClient,
    sample_operators: list,  # noqa: ARG001  # seeds the DB rows
):
    resp = await client.get("/api/v1/transport/operators")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2
    names = {o["name"] for o in data}
    assert "SNTF" in names
    assert "Air Algérie" in names


@pytest.mark.asyncio
async def test_list_operators_filter_mode(
    client: AsyncClient,
    sample_operators: list,  # noqa: ARG001  # seeds the DB rows
):
    resp = await client.get("/api/v1/transport/operators?mode=train")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "SNTF"
    assert data[0]["phone"] == "+213 21 63 30 00"
    assert data[0]["website"] == "https://sntf.dz"


@pytest.mark.asyncio
async def test_list_operators_empty(client: AsyncClient):
    resp = await client.get("/api/v1/transport/operators")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


# ── GET /transport/plan ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_plan_route_no_route(client: AsyncClient):
    from app.main import app
    from app.services.poi_transit_router import RoutePlan

    mock_router = app.state.poi_transit_router
    mock_router.route_to = AsyncMock(
        return_value=RoutePlan(
            from_lat=36.75,
            from_lng=3.06,
            from_name="Your location",
            to_lat=35.69,
            to_lng=-0.63,
            to_name="Destination",
            total_walking_km=120.0,
            total_transit_km=0.0,
            total_transfers=0,
            total_estimated_minutes=1440,
            available_modes=["walking"],
            is_walking_only=True,
            is_driving_recommended=True,
        )
    )

    resp = await client.get(
        "/api/v1/transport/plan",
        params={
            "from_lat": 36.75,
            "from_lng": 3.06,
            "to_lat": 35.69,
            "to_lng": -0.63,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_walking_only"] is True
    assert data["total_transit_km"] == 0
    assert data["steps"] == []


# ── GET /transport/access/{poi_id} ─────────────────────────────────


@pytest.mark.asyncio
async def test_poi_access(client: AsyncClient):
    from app.main import app

    mock_routing = app.state.transit_routing

    mock_result = MagicMock()
    mock_result.model_dump.return_value = {
        "poi_id": str(uuid.uuid4()),
        "nearest_stations": [],
    }
    mock_routing.poi_access = AsyncMock(return_value=mock_result)

    poi_id = uuid.uuid4()
    resp = await client.get(
        f"/api/v1/transport/access/{poi_id}",
        params={"lat": 36.75, "lng": 3.06, "name": "Test POI"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "nearest_stations" in data
