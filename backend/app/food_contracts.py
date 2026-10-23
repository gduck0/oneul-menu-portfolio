from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Unit = Literal['g', 'mL']
Preference = Literal['balanced', 'energy', 'protein', 'similarity']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Source(StrictModel):
    snapshot_id: str
    food_code: str
    provider: str
    reference_date: str
    production_date: str | None
    retrieved_at: datetime
    url: str


class Nutrients(StrictModel):
    energy_kcal: Decimal | None
    protein_g: Decimal | None
    fat_g: Decimal | None
    carbohydrate_g: Decimal | None


class FoodSummary(StrictModel):
    id: str
    name: str
    company: str | None
    basis_amount: Decimal
    basis_unit: Unit
    source_weight: str | None
    nutrients: Nutrients
    source: Source


class SearchResponse(StrictModel):
    query: str
    total: int
    requires_confirmation: bool
    items: list[FoodSummary]


class Portion(StrictModel):
    amount: Decimal = Field(gt=0, le=10000, decimal_places=3, allow_inf_nan=False)
    unit: Unit


class NutritionResponse(StrictModel):
    food: FoodSummary
    portion: Portion
    nutrients: Nutrients
    missing_nutrients: list[str]
