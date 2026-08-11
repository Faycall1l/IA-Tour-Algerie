import uuid

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin
class Station(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "stations"
    __allow_unmapped__ = True

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name_ar: Mapped[str | None] = mapped_column(String(200))
    name_en: Mapped[str | None] = mapped_column(String(200))
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    station_type: Mapped[str] = mapped_column(String(20), nullable=False)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class TransportLine(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "transport_lines"
    __allow_unmapped__ = True

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))
    description: Mapped[str | None] = mapped_column(String(500))
    distance_km: Mapped[float | None] = mapped_column(Float)
    schedule_info: Mapped[dict | None] = mapped_column(JSON)
    pricing_info: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    stops: list["LineStop"] = relationship(
        back_populates="line", lazy="selectin", order_by="LineStop.stop_order"
    )


class LineStop(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "line_stops"
    __allow_unmapped__ = True

    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transport_lines.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stop_order: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_start_km: Mapped[float | None] = mapped_column(Float)
    travel_time_from_start_min: Mapped[int | None] = mapped_column(Integer)
    departure_time: Mapped[str | None] = mapped_column(String(5))
    arrival_time: Mapped[str | None] = mapped_column(String(5))

    line: TransportLine = relationship(back_populates="stops", lazy="joined")
    station: Station = relationship(lazy="joined")


class StationTransfer(UUIDPkMixin, TimestampMixin, Base):
    """A walking transfer edge between two stations.

    Connects stations that are physically close but not served by the same
    line (e.g. a bus stop 300m from a train station). Lets routing reach
    stations that no line serves directly by walking to the nearest served
    stop. Always stored/read symmetrically (both directions).
    """

    __tablename__ = "transfers"
    __allow_unmapped__ = True

    from_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    walking_time_min: Mapped[float] = mapped_column(Float, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="spatial")

    from_station: Station = relationship(foreign_keys=[from_station_id], lazy="joined")
    to_station: Station = relationship(foreign_keys=[to_station_id], lazy="joined")
