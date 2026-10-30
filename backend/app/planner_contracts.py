from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator
from app.food_contracts import Nutrients, Preference, StrictModel

from app.meal_constraints import MealConstraints, MealKey


class FixedMeal(StrictModel):
    menu_id: str | None = Field(default=None, max_length=40)
    custom_name: str | None = Field(default=None, min_length=1, max_length=100)
    amount_g: Decimal | None = Field(default=None, gt=0, le=2000, decimal_places=2, allow_inf_nan=False)

    @model_validator(mode='after')
    def selected_menu(self):
        if (self.menu_id is None)==(self.custom_name is None):
            raise ValueError('등록 메뉴 또는 직접 입력 중 하나를 선택해 주세요.')
        if self.custom_name is not None:
            self.custom_name=self.custom_name.strip()
            if not self.custom_name:raise ValueError('음식 이름을 입력해 주세요.')
        return self


class PlanRequest(StrictModel):
    client_request_id: UUID = Field(default_factory=uuid4)
    plan_date: date
    energy_target: Decimal = Field(default=Decimal('1800'), ge=600, le=5000, allow_inf_nan=False)
    protein_target: Decimal | None = Field(default=None, ge=10, le=300, allow_inf_nan=False)
    carbohydrate_target: Decimal | None = Field(default=None, ge=20, le=800, allow_inf_nan=False)
    fat_target: Decimal | None = Field(default=None, ge=5, le=300, allow_inf_nan=False)
    meal_count: Literal[2, 3, 4] = 3
    preference: Preference | None = None
    constraints: dict[MealKey, MealConstraints] = Field(default_factory=dict)
    fixed_meals: dict[MealKey, FixedMeal] = Field(default_factory=dict)
    personalize: bool = True

    @model_validator(mode='after')
    def fixed_slots(self):
        slots={2:{'lunch','dinner'},3:{'breakfast','lunch','dinner'},4:{'breakfast','lunch','dinner','snack'}}[self.meal_count]
        if set(self.fixed_meals)-slots:
            raise ValueError('선택한 끼니 수에 포함된 메뉴만 고정할 수 있어요.')
        return self


class PlanEdit(StrictModel):
    client_request_id: UUID = Field(default_factory=uuid4)
    expected_version: int = Field(ge=1)
    meal_key: MealKey
    action: Literal['lock', 'replace', 'undo_replace', 'set', 'portion', 'add', 'remove', 'update_item']
    replacement_request_id: UUID | None = None
    locked: bool | None = None
    menu_id: str | None = Field(default=None, max_length=40)
    item_id: str | None = Field(default=None, max_length=80)
    amount_g: Decimal | None = Field(default=None, gt=0, le=2000, decimal_places=2, allow_inf_nan=False)
    custom_name: str | None = Field(default=None, min_length=1, max_length=100)
    constraints: MealConstraints | None = None

    @model_validator(mode='after')
    def action_fields(self):
        if self.action=='undo_replace' and self.replacement_request_id is None:
            raise ValueError('되돌릴 추천 변경 번호가 필요해요.')
        if self.action=='lock' and self.locked is None:
            raise ValueError('고정 상태가 필요해요.')
        if self.action in ('set', 'add', 'update_item') and (self.menu_id is None)==(self.custom_name is None):
            raise ValueError('등록 메뉴 또는 직접 입력 중 하나를 선택해 주세요.')
        if self.action=='portion' and (self.item_id is None or 'amount_g' not in self.model_fields_set):
            raise ValueError('변경할 음식과 양이 필요해요.')
        if self.action in ('remove', 'update_item') and self.item_id is None:
            raise ValueError('변경할 음식을 선택해 주세요.')
        if self.custom_name is not None:
            self.custom_name=self.custom_name.strip()
            if not self.custom_name:
                raise ValueError('음식 이름을 입력해 주세요.')
        return self


class PlanResponse(StrictModel):
    id: str
    version: int
    plan_date: date
    created_at: datetime
    updated_at: datetime
    settings: dict
    meals: list[dict]
    nutrients: Nutrients
    missing_nutrients: list[str]
    target_difference: dict
    notes: list[str]
    catalog_version: str


class PlanMealRecord(StrictModel):
    client_record_id: UUID = Field(default_factory=uuid4)
    expected_version: int = Field(ge=1)
    eaten_at: datetime
    amounts: dict[str, Decimal | None] = Field(default_factory=dict, max_length=20)
    skipped_item_ids: list[str] = Field(default_factory=list, max_length=12)

    @field_validator('skipped_item_ids')
    @classmethod
    def check_skipped_items(cls, values):
        if len(set(values)) != len(values) or any(not value or len(value) > 80 for value in values):
            raise ValueError('먹지 않은 음식을 중복 없이 선택해 주세요.')
        return values

    @field_validator('amounts')
    @classmethod
    def check_amounts(cls, values):
        if any(value is not None and (not value.is_finite() or value <= 0 or value > 2000 or value != value.quantize(Decimal('.01'))) for value in values.values()):
            raise ValueError('실제 먹은 양을 0보다 크고 2000g 이하로 소수 둘째 자리까지 입력해 주세요.')
        return values

    @field_validator('eaten_at')
    @classmethod
    def aware_date(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('식사 시각에 시간대가 필요해요.')
        return value
