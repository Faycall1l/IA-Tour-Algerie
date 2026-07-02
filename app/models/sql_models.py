from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class LocalAgency(Base):
    __tablename__ = "local_agencies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    license_number = Column(String(50), unique=True, nullable=False)
    wilaya = Column(String(50), nullable=False)
    contact_phone = Column(String(20), nullable=False)


class AtharTravelerProfile(Base):
    __tablename__ = "athar_traveler_profile"

    id = Column(String(36), primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    passport_hash = Column(String(64), unique=True, nullable=False)
    encrypted_identity = Column(LargeBinary, nullable=False)
    assigned_agency_id = Column(Integer, ForeignKey("local_agencies.id"))
    language_preference = Column(String(10), default="en")
    anonymous_geo_trail = Column(JSON, default=list)
