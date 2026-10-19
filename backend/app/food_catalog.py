from decimal import Decimal, ROUND_HALF_UP
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.food_contracts import FoodSummary, Nutrients, NutritionResponse, Portion, SearchResponse, Source
from app.food_models import Food, NutritionSnapshot


NUTRIENT_FIELDS = ('energy_kcal', 'protein_g', 'fat_g', 'carbohydrate_g')
ALIASES = {
    '치킨': ('닭튀김', '닭구이', '치킨'),
    '돈까스': ('돈까스', '돈가스'),
    '짜장면': ('짜장면', '자장면'),
    '자장면': ('짜장면', '자장면'),
}


def normalize_name(value: str) -> str:
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).casefold()


def summarize(food: Food, snapshot: NutritionSnapshot) -> FoodSummary:
    return FoodSummary(
        id=food.id, name=food.name, company=food.company,
        basis_amount=food.basis_amount, basis_unit=food.basis_unit, source_weight=food.source_weight,
        nutrients=Nutrients(**{field: getattr(food, field) for field in NUTRIENT_FIELDS}),
        source=Source(snapshot_id=snapshot.id, food_code=food.food_code, provider=food.provider,
                      reference_date=food.reference_date, production_date=food.production_date,
                      retrieved_at=snapshot.retrieved_at, url=snapshot.source_url),
    )


def find_food(session: Session, food_id: str) -> tuple[Food, NutritionSnapshot]:
    row = session.execute(select(Food, NutritionSnapshot).join(NutritionSnapshot).where(Food.id == food_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail='등록된 음식을 찾지 못했어요.')
    return row[0], row[1]


def search_foods(session: Session, query: str, limit: int, offset: int) -> SearchResponse:
    normalized = normalize_name(query)
    if not normalized:
        raise HTTPException(status_code=422, detail='음식 이름을 입력해 주세요.')
    terms = ALIASES.get(normalized, (normalized,))
    matches = or_(*(Food.normalized_name.contains(term, autoescape=True) for term in terms))
    base = select(Food, NutritionSnapshot).join(NutritionSnapshot).where(NutritionSnapshot.active.is_(True), matches)
    total = session.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    ordered = base.order_by(Food.normalized_name.in_(terms).desc(), Food.company.is_(None).desc(),
                            (Food.basis_unit == 'g').desc(), func.length(Food.name), Food.name, Food.food_code, Food.id)
    items = [summarize(food, snapshot) for food, snapshot in session.execute(ordered.limit(limit).offset(offset))]
    return SearchResponse(query=query, total=total, requires_confirmation=total > 1, items=items)


def nutrition(food: Food, snapshot: NutritionSnapshot, portion: Portion) -> NutritionResponse:
    if food.basis_unit != portion.unit:
        raise HTTPException(status_code=422, detail=f'이 음식의 기준 단위는 {food.basis_unit}예요. 밀도 자료 없이 g와 mL를 바꿀 수 없어요.')
    factor = portion.amount / food.basis_amount
    values = {field: None if getattr(food, field) is None else (getattr(food, field) * factor).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
              for field in NUTRIENT_FIELDS}
    return NutritionResponse(food=summarize(food, snapshot), portion=portion, nutrients=Nutrients(**values),
                             missing_nutrients=[field for field, value in values.items() if value is None])
