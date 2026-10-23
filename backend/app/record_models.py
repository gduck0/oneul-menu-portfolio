from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('app.users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecommendationEvent(Base):
    __tablename__ = 'recommendation_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('app.users.id'), index=True)
    guest_token_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (CheckConstraint('(user_id IS NULL) <> (guest_token_hash IS NULL)', name='ck_recommendation_one_owner'),)


class MealChoice(Base):
    __tablename__ = 'meal_choices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('app.users.id'), index=True)
    client_record_id: Mapped[str] = mapped_column(String(36))
    recommendation_id: Mapped[str] = mapped_column(ForeignKey('app.recommendation_events.id'))
    food_id: Mapped[str] = mapped_column(ForeignKey('app.foods.id'))
    selected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    nutrition: Mapped[dict] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(String(150))
    __table_args__ = (UniqueConstraint('user_id', 'client_record_id', name='uq_choice_client_record'),
                      UniqueConstraint('user_id', 'recommendation_id', name='uq_choice_recommendation'))


class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id: Mapped[str] = mapped_column(ForeignKey('app.users.id', ondelete='CASCADE'), primary_key=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    __table_args__ = (CheckConstraint('(height_cm IS NULL) = (weight_kg IS NULL)', name='ck_profile_complete_pair'),
                      CheckConstraint('height_cm IS NULL OR height_cm BETWEEN 100 AND 250', name='ck_profile_height'),
                      CheckConstraint('weight_kg IS NULL OR weight_kg BETWEEN 20 AND 300', name='ck_profile_weight'))
