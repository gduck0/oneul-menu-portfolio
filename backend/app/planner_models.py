from datetime import date, datetime
from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class MealPlan(Base):
    __tablename__='meal_plans'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(66),index=True)
    client_request_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    plan_date: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('owner_key','client_request_id',name='uq_meal_plan_request'),CheckConstraint('version > 0',name='ck_meal_plan_version'))


class PlanOperation(Base):
    __tablename__='plan_operations'
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('app.meal_plans.id'))
    client_request_id: Mapped[str] = mapped_column(String(36))
    input_hash: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    __table_args__=(UniqueConstraint('plan_id','client_request_id',name='uq_plan_operation_request'),)
