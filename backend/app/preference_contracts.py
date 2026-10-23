from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.food_contracts import Preference, StrictModel
from app.meal_constraints import MealConstraints, MealKey


class SettingsRequest(StrictModel):
    goal: Preference = 'balanced'
    favorite_foods: list[str] = Field(default_factory=list, max_length=10)
    avoided_foods: list[str] = Field(default_factory=list, max_length=10)
    frequent_foods: list[str] = Field(default_factory=list, max_length=10)
    energy_target: Decimal | None = Field(default=None, ge=600, le=5000, allow_inf_nan=False)
    meal_count: Literal[2, 3, 4] = 3
    default_constraints: dict[MealKey, MealConstraints] = Field(default_factory=dict)

    @field_validator('favorite_foods', 'avoided_foods', 'frequent_foods')
    @classmethod
    def clean_names(cls, names):
        values = list(dict.fromkeys(name.strip() for name in names if name.strip()))
        if any(len(name) > 40 for name in values):
            raise ValueError('음식 이름은 40자 이하로 입력해 주세요.')
        return values

    @model_validator(mode='after')
    def no_conflicting_preferences(self):
        if set(self.favorite_foods) & set(self.avoided_foods):
            raise ValueError('같은 음식을 선호와 제외에 함께 넣을 수 없어요.')
        return self
