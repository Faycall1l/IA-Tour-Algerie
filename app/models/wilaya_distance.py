from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin

ROAD_CLASSIFICATIONS = ("autoroute", "national", "mountain", "desert", "coastal")


class WilayaDistance(TimestampMixin, Base):
    __tablename__ = "wilaya_distances"
    __table_args__ = (
        CheckConstraint(
            f"road_classification IN {ROAD_CLASSIFICATIONS}",
            name="ck_road_classification",
        ),
        CheckConstraint("driving_distance_km >= 0", name="ck_distance_positive"),
        CheckConstraint("driving_time_minutes >= 0", name="ck_time_positive"),
    )

    origin_wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id", ondelete="CASCADE"), primary_key=True
    )
    dest_wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id", ondelete="CASCADE"), primary_key=True
    )
    driving_distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    driving_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    road_classification: Mapped[str] = mapped_column(String(20), nullable=False)
    has_train_route: Mapped[bool] = mapped_column(default=False)
    has_direct_flight: Mapped[bool] = mapped_column(default=False)
