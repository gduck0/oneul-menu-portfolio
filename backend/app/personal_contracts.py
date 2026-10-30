from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from app.food_contracts import Nutrients, Portion, Preference, StrictModel
from app.preference_contracts import SettingsRequest

Rating = Literal['like', 'neutral', 'dislike']
FeedbackReason = Literal['taste', 'purpose', 'unavailable', 'portion', 'variety']


class MealRequest(StrictModel):
    client_record_id: UUID = Field(default_factory=uuid4)
    food_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    name: str | None = Field(default=None, min_length=1, max_length=100)
    portion: Portion | None = None
    eaten_at: datetime
    notes: str = Field(default='', max_length=300)

    @model_validator(mode='after')
    def check_food_and_date(self):
        if self.food_id is not None and self.portion is None:
            raise ValueError('등록 음식은 기준 분량을 선택하거나 먹은 양을 입력해 주세요.')
        if (self.food_id is None) == (self.name is None):
            raise ValueError('등록 음식 또는 직접 입력 이름 중 하나를 선택해 주세요.')
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError('음식 이름을 입력해 주세요.')
        if self.eaten_at.tzinfo is None or self.eaten_at.utcoffset() is None:
            raise ValueError('식사 시각에 시간대가 필요해요.')
        return self


class MealResponse(StrictModel):
    id: str
    name: str
    food_id: str | None
    portion: Portion | None
    eaten_at: datetime
    notes: str
    nutrients: Nutrients
    nutrition: dict | None
    nutrition_source: Literal['catalog', 'unknown', 'menu_reference']
    version: int = 1
    cancelled_at: datetime | None = None
    plan_id: str | None = None
    meal_key: str | None = None
    record_group_id: str | None = None
    skipped_foods: list[str] = Field(default_factory=list)


class MealHistory(StrictModel):
    items: list[MealResponse]
    total: int


class FeedbackRequest(StrictModel):
    phase: Literal['recommendation', 'consumed']
    context_id: UUID
    food_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    rating: Rating
    reason: FeedbackReason | None = None


class FeedbackResponse(FeedbackRequest):
    id: str
    updated_at: datetime
