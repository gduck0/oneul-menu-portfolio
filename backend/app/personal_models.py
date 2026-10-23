from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PersonalSettings(Base):
    __tablename__ = 'personal_settings'
    owner_key: Mapped[str] = mapped_column(String(66), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MealEntry(Base):
    __tablename__ = 'meal_entries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(66), index=True)
    client_record_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    eaten_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text('1'))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('owner_key', 'client_record_id', name='uq_meal_entry_request'),)


class MenuFeedback(Base):
    __tablename__ = 'menu_feedback'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(66), index=True)
    context_id: Mapped[str] = mapped_column(String(36))
    phase: Mapped[str] = mapped_column(String(20))
    food_id: Mapped[str | None] = mapped_column(ForeignKey('app.foods.id'))
    food_code: Mapped[str | None] = mapped_column(String(80))
    rating: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str | None] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('owner_key', 'context_id', 'phase', 'food_id', name='uq_menu_feedback_context', postgresql_nulls_not_distinct=True),
                      CheckConstraint("phase IN ('recommendation', 'consumed')", name='ck_feedback_phase'),
                      CheckConstraint("rating IN ('like', 'neutral', 'dislike')", name='ck_feedback_rating'))


class MealChange(Base):
    __tablename__ = 'meal_changes'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(66), index=True)
    client_request_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    meal_id: Mapped[str] = mapped_column(ForeignKey('app.meal_entries.id'))
    action: Mapped[str] = mapped_column(String(20))
    before: Mapped[list] = mapped_column(JSONB)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('owner_key', 'client_request_id', name='uq_meal_change_request'),)


class GuestTransfer(Base):
    __tablename__ = 'guest_transfers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    guest_key: Mapped[str] = mapped_column(String(66), unique=True)
    user_key: Mapped[str] = mapped_column(String(66))
    client_request_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('user_key', 'client_request_id', name='uq_guest_transfer_request'),)
