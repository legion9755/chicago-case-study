"""
backend/models.py
ORM models (SQLAlchemy 2.0 typed style) that follow the assignment's data model:

    chicago_crime (fact)  ──►  iucr               (iucr_code)
                          ──►  police_beat_info   (beat_num)
                          ──►  district_ps_info   (district_code)
                          ──►  ward_office        (ward_no)
                          ──►  city_community     (community_code)
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


# ---------------------------------------------------------------------------
# Dimension (lookup) tables
# ---------------------------------------------------------------------------
class Iucr(Base):
    __tablename__ = "iucr"
    iucr_code: Mapped[str] = mapped_column(String(4), primary_key=True)
    primary_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[Optional[str]] = mapped_column(String(128))
    index_code: Mapped[Optional[str]] = mapped_column(String(1))


class CityCommunity(Base):
    __tablename__ = "city_community"
    community_code: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    community_name: Mapped[str] = mapped_column(String(64))
    population: Mapped[Optional[int]] = mapped_column(Integer)
    area_sqmile: Mapped[Optional[float]] = mapped_column(Float)
    area_sqkm: Mapped[Optional[float]] = mapped_column(Float)
    density_per_sqmi: Mapped[Optional[float]] = mapped_column(Float)
    density_per_sqkm: Mapped[Optional[float]] = mapped_column(Float)


class DistrictPsInfo(Base):
    __tablename__ = "district_ps_info"
    district_code: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    district_name: Mapped[str] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(128))
    city: Mapped[Optional[str]] = mapped_column(String(32))
    state: Mapped[Optional[str]] = mapped_column(String(2))
    zip: Mapped[Optional[str]] = mapped_column(String(10))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    phone: Mapped[Optional[str]] = mapped_column(String(40))
    fax: Mapped[Optional[str]] = mapped_column(String(40))
    tty: Mapped[Optional[str]] = mapped_column(String(40))
    x_coordinate: Mapped[Optional[float]] = mapped_column(Float)
    y_coordinate: Mapped[Optional[float]] = mapped_column(Float)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    location: Mapped[Optional[str]] = mapped_column(String(64))


class WardOffice(Base):
    __tablename__ = "ward_office"
    ward_no: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    alderman: Mapped[Optional[str]] = mapped_column(String(64))
    address: Mapped[Optional[str]] = mapped_column(String(128))
    city: Mapped[Optional[str]] = mapped_column(String(32))
    state: Mapped[Optional[str]] = mapped_column(String(2))
    zipcode: Mapped[Optional[str]] = mapped_column(String(10))
    ward_phone: Mapped[Optional[str]] = mapped_column(String(40))
    ward_fax: Mapped[Optional[str]] = mapped_column(String(40))
    email: Mapped[Optional[str]] = mapped_column(String(128))
    website: Mapped[Optional[str]] = mapped_column(String(255))
    location: Mapped[Optional[str]] = mapped_column(String(64))
    location_address: Mapped[Optional[str]] = mapped_column(String(128))
    location_city: Mapped[Optional[str]] = mapped_column(String(32))
    location_state: Mapped[Optional[str]] = mapped_column(String(2))
    location_zip: Mapped[Optional[str]] = mapped_column(String(10))
    city_hall_address: Mapped[Optional[str]] = mapped_column(String(128))
    city_hall_city: Mapped[Optional[str]] = mapped_column(String(32))
    city_hall_state: Mapped[Optional[str]] = mapped_column(String(2))
    city_hall_zipcode: Mapped[Optional[str]] = mapped_column(String(10))
    city_hall_phone: Mapped[Optional[str]] = mapped_column(String(40))


class PoliceBeatInfo(Base):
    __tablename__ = "police_beat_info"
    beat_num: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    district: Mapped[Optional[int]] = mapped_column(Integer)
    sector: Mapped[Optional[int]] = mapped_column(Integer)
    beat: Mapped[Optional[int]] = mapped_column(Integer)


# ---------------------------------------------------------------------------
# Fact table
# ---------------------------------------------------------------------------
class ChicagoCrime(Base):
    __tablename__ = "chicago_crime"
    case_number: Mapped[str] = mapped_column(String(12), primary_key=True)
    id: Mapped[int] = mapped_column(Integer, unique=True)
    date: Mapped[datetime] = mapped_column(DateTime)
    block: Mapped[Optional[str]] = mapped_column(String(64))
    iucr_code: Mapped[str] = mapped_column(ForeignKey("iucr.iucr_code"))
    location_desc: Mapped[Optional[str]] = mapped_column(String(80))
    arrest: Mapped[bool] = mapped_column(Boolean, default=False)
    domestic: Mapped[bool] = mapped_column(Boolean, default=False)
    beat_num: Mapped[Optional[int]] = mapped_column(ForeignKey("police_beat_info.beat_num"))
    district_code: Mapped[Optional[int]] = mapped_column(ForeignKey("district_ps_info.district_code"))
    ward_no: Mapped[Optional[int]] = mapped_column(ForeignKey("ward_office.ward_no"))
    community_code: Mapped[Optional[int]] = mapped_column(ForeignKey("city_community.community_code"))
    fbi_code: Mapped[Optional[str]] = mapped_column(String(4))
    x_coordinate: Mapped[Optional[float]] = mapped_column(Float)
    y_coordinate: Mapped[Optional[float]] = mapped_column(Float)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    day_of_week: Mapped[str] = mapped_column(String(9))
    hour: Mapped[int] = mapped_column(Integer)
    date_of_update: Mapped[Optional[datetime]] = mapped_column(DateTime)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    location: Mapped[Optional[str]] = mapped_column(String(64))

    __table_args__ = (
        Index("idx_crime_year", "year"),
        Index("idx_crime_community", "community_code"),
        Index("idx_crime_iucr", "iucr_code"),
    )


# Registry used by the CRUD API: URL name -> (model, human label)
DIMENSIONS = {
    "communities": (CityCommunity, "City community areas"),
    "districts": (DistrictPsInfo, "Police districts / stations"),
    "wards": (WardOffice, "Ward offices"),
    "beats": (PoliceBeatInfo, "Police beats"),
    "iucr": (Iucr, "IUCR crime codes"),
}

# SQL views used by Use Case 4 and the dashboard (window functions need SQLite >= 3.25)
VIEWS_SQL = {
    "vw_crime_yearly": """
        CREATE VIEW vw_crime_yearly AS
        SELECT year,
               COUNT(*)                          AS total_crimes,
               SUM(arrest)                       AS total_arrests,
               ROUND(100.0 * AVG(arrest), 2)     AS arrest_rate_pct,
               SUM(domestic)                     AS domestic_crimes
        FROM chicago_crime
        GROUP BY year""",
    "vw_crime_by_category": """
        CREATE VIEW vw_crime_by_category AS
        SELECT i.primary_type,
               COUNT(*)                                             AS total_crimes,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)   AS pct_of_total,
               SUM(c.arrest)                                        AS total_arrests,
               ROUND(100.0 * AVG(c.arrest), 2)                      AS arrest_rate_pct
        FROM chicago_crime c
        JOIN iucr i ON i.iucr_code = c.iucr_code
        GROUP BY i.primary_type""",
}
