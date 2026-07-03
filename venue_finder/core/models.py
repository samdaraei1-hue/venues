from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Venue(Base):
    __tablename__ = "venues"
    __table_args__ = (
        UniqueConstraint("source_url", name="uq_venues_source_url"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    venue_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    postal_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    street_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    distance_from_frankfurt_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    driving_time_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    minimum_booking_guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    maximum_guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    indoor_sleeping_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_beds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    camping_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    camping_capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    camper_van_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    parties_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    loud_music_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dj_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sound_system_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outdoor_party_area: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bbq_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fire_place: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    swimming_pool: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lake_or_river_nearby: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    private_property: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    quiet_hours_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quiet_hours_end: Mapped[str | None] = mapped_column(String(16), nullable=True)

    price_per_night: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_per_person: Mapped[float | None] = mapped_column(Float, nullable=True)
    camping_price_per_person: Mapped[float | None] = mapped_column(Float, nullable=True)
    indoor_accommodation_price_per_person: Mapped[float | None] = mapped_column(Float, nullable=True)
    cleaning_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    security_deposit: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_fees: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    minimum_nights: Mapped[int | None] = mapped_column(Integer, nullable=True)

    available_dates: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    booking_calendar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    owner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    number_of_reviews: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    party_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    suitability_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    restrictions_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | list | None] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (UniqueConstraint("keyword", name="uq_keywords_keyword"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
