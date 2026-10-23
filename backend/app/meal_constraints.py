from typing import Literal

from pydantic import Field, field_validator

from app.food_contracts import StrictModel

MealKey = Literal['breakfast', 'lunch', 'dinner', 'snack']


class MealConstraints(StrictModel):
    no_cook: bool = False
    prepared_sides: bool = False
    tools: list[Literal['pan', 'pot', 'rice', 'steam', 'stone']] = Field(default_factory=list, max_length=5)
    max_minutes: int | None = Field(default=None, ge=5, le=120)
    avoided_foods: list[str] = Field(default_factory=list, max_length=20)

    @field_validator('avoided_foods')
    @classmethod
    def clean_names(cls, values):
        values=list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v)>40 for v in values):
            raise ValueError('제외 이름은 40자 이하로 입력해 주세요.')
        return values
