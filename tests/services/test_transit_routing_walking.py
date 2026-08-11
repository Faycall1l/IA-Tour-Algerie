"""Walking-transfer edges wired into TransitGraph via the `transfers` table."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.station import LineStop, Station, StationTransfer, TransportLine
from app.services.transit_routing import TransitRoutingService


async def _seed(db: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Served stations A-B on line L, orphan C connected to A by walking."""
    a = Station(
        name="Station A",
        wilaya_id=1,
        latitude=36.75,
        longitude=3.05,
        station_type="bus",
        operator="Test",
    )
    b = Station(
        name="Station B",
        wilaya_id=1,
        latitude=36.76,
        longitude=3.06,
        station_type="bus",
        operator="Test",
    )
    c = Station(
        name="Station C (orphan)",
        wilaya_id=1,
        latitude=36.7505,
        longitude=3.051,
        station_type="bus",
        operator="Test",
    )
    line = TransportLine(
        name="Test Line",
        operator="Test",
        mode="bus",
    )
    db.add_all([a, b, c, line])
    await db.flush()

    db.add_all(
        [
            LineStop(line_id=line.id, station_id=a.id, stop_order=0),
            LineStop(line_id=line.id, station_id=b.id, stop_order=1),
            StationTransfer(
                from_station_id=c.id,
                to_station_id=a.id,
                distance_m=150.0,
                walking_time_min=2.0,
                source="orphan_connect",
            ),
        ]
    )
    await db.commit()
    return c.id, a.id, b.id


@pytest.mark.asyncio
async def test_walking_edge_makes_orphan_reachable(db: AsyncSession) -> None:
    orphan_id, hub_id, _served_id = await _seed(db)

    svc = TransitRoutingService()
    await svc.ensure_loaded(db)

    # Orphan has a walking edge toward the served station it connects to.
    orphan_edges = svc._graph._adj[orphan_id]
    assert any(e.operator == "Walking" and e.to_station_id == hub_id for e in orphan_edges)

    # Walking edge is present in both directions.
    served_edges = svc._graph._adj[hub_id]
    assert any(e.operator == "Walking" and e.to_station_id == orphan_id for e in served_edges)


@pytest.mark.asyncio
async def test_route_includes_walking_segment(db: AsyncSession) -> None:
    orphan_id, _hub_id, served_id = await _seed(db)

    svc = TransitRoutingService()
    await svc.ensure_loaded(db)

    route = svc._graph.find_route(orphan_id, served_id)
    assert route is not None
    assert route.segments[0].mode == "walking"
    assert route.segments[0].operator == "Walking"
    assert route.segments[0].estimated_minutes == 2
