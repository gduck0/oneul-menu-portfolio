"""원본 버전별 음식과 영양 정보를 보존한다."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NutritionSnapshot(Base):
    __tablename__ = 'nutrition_snapshots'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    row_count: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (Index('uq_active_nutrition_snapshot', 'active', unique=True, postgresql_where=text('active = true')),)


class Food(Base):
    __tablename__ = 'foods'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey('app.nutrition_snapshots.id'))
    food_code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(300))
    normalized_name: Mapped[str] = mapped_column(String(300), index=True)
    company: Mapped[str | None] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(30), index=True)
    basis_amount: Mapped[Decimal] = mapped_column(Numeric(14, 5))
    basis_unit: Mapped[str] = mapped_column(String(2))
    energy_kcal: Mapped[Decimal | None] = mapped_column(Numeric(14, 5))
    protein_g: Mapped[Decimal | None] = mapped_column(Numeric(14, 5))
    fat_g: Mapped[Decimal | None] = mapped_column(Numeric(14, 5))
    carbohydrate_g: Mapped[Decimal | None] = mapped_column(Numeric(14, 5))
    provider: Mapped[str] = mapped_column(String(300))
    reference_date: Mapped[str] = mapped_column(String(10))
    production_date: Mapped[str | None] = mapped_column(String(10))
    source_weight: Mapped[str | None] = mapped_column(String(100))
    raw: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint('snapshot_id', 'food_code', name='uq_food_snapshot_code'),
        CheckConstraint('basis_amount > 0', name='ck_food_positive_basis'),
        CheckConstraint("basis_unit IN ('g', 'mL')", name='ck_food_basis_unit'),
        CheckConstraint('energy_kcal IS NULL OR energy_kcal >= 0', name='ck_food_energy'),
        CheckConstraint('protein_g IS NULL OR protein_g >= 0', name='ck_food_protein'),
        CheckConstraint('fat_g IS NULL OR fat_g >= 0', name='ck_food_fat'),
        CheckConstraint('carbohydrate_g IS NULL OR carbohydrate_g >= 0', name='ck_food_carbohydrate'),
    )
