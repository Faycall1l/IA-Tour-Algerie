import uuid

from pydantic import BaseModel, Field


class StationRead(BaseModel):
    id: uuid.UUID
    name: str
    name_ar: str | None = None
    name_en: str | None = None
    wilaya_id: int
    latitude: float
    longitude: float
    station_type: str
    operator: str
    address: str | None = None
    is_active: bool = True


class StationLineRef(BaseModel):
    line_id: uuid.UUID
    line_name: str
    mode: str
    operator: str
    color: str | None = None
    stop_order: int


class StationDetail(StationRead):
    lines: list[StationLineRef] = []


class LineStopRead(BaseModel):
    id: uuid.UUID
    station: StationRead
    stop_order: int
    distance_from_start_km: float | None = None
    travel_time_from_start_min: int | None = None
    departure_time: str | None = None
    arrival_time: str | None = None


class TransportLineRead(BaseModel):
    id: uuid.UUID
    name: str
    operator: str
    mode: str
    color: str | None = None
    description: str | None = None
    distance_km: float | None = None
    schedule_info: dict | None = None
    pricing_info: dict | None = None
    is_active: bool = True
    stops: list[LineStopRead] = []


class RouteSegment(BaseModel):
    mode: str
    operator: str
    line_name: str
    line_id: uuid.UUID | None = None
    line_color: str | None = None
    from_station: str
    to_station: str
    from_station_id: uuid.UUID
    to_station_id: uuid.UUID
    stop_count: int
    estimated_minutes: int | None = None
    departure_time: str | None = None
    arrival_time: str | None = None
    pricing: dict | None = None
    schedule: list[dict] | None = None


class RouteResult(BaseModel):
    from_lat: float
    from_lng: float
    to_lat: float
    to_lng: float
    from_name: str | None = None
    to_name: str | None = None
    segments: list[RouteSegment]
    total_transfers: int
    total_estimated_minutes: int | None = None


class NearestStation(BaseModel):
    station: StationRead
    distance_km: float
    lines: list[StationLineRef] = []


class POIAccess(BaseModel):
    poi_id: uuid.UUID
    poi_name: str
    nearest_stations: list[NearestStation]
    route_to_poi: RouteResult | None = None


# ── Turn-by-turn route plan schemas ──────────────────────────────────

class RoutePlanCoordinate(BaseModel):
    lat: float
    lng: float
    name: str


class RoutePlanResponse(BaseModel):
    from_point: RoutePlanCoordinate = Field(alias="from")
    to: RoutePlanCoordinate
    total_walking_km: float
    total_transit_km: float
    total_transfers: int
    total_estimated_minutes: int
    available_modes: list[str]
    is_walking_only: bool = False
    is_driving_recommended: bool = False
    steps: list[dict] = []

    model_config = {"populate_by_name": True}


class POIRoutePlanResponse(BaseModel):
    poi_id: uuid.UUID
    poi_name: str
    poi_lat: float
    poi_lng: float
    from_point: RoutePlanCoordinate = Field(alias="from")
    plan: RoutePlanResponse | None = None
    alternatives: list[RoutePlanResponse] = []
    poi_access: dict | None = None

    model_config = {"populate_by_name": True}
