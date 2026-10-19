from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from app.food_catalog import find_food, nutrition, search_foods, summarize
from app.food_contracts import FoodSummary, NutritionResponse, Portion, SearchResponse, Unit
from app.session_dependency import get_session


router = APIRouter(prefix='/api')
FoodId = Annotated[str, Path(pattern=r'^[a-f0-9]{64}$')]


@router.get('/foods', response_model=SearchResponse)
def foods(q: Annotated[str, Query(min_length=1, max_length=80)],
          limit: Annotated[int, Query(ge=1, le=50)] = 20,
          offset: Annotated[int, Query(ge=0, le=10000)] = 0, session=Depends(get_session)):
    return search_foods(session, q.strip(), limit, offset)


@router.get('/foods/{food_id}', response_model=FoodSummary)
def food_detail(food_id: FoodId, session=Depends(get_session)):
    return summarize(*find_food(session, food_id))


@router.get('/foods/{food_id}/nutrition', response_model=NutritionResponse)
def food_nutrition(food_id: FoodId,
                   amount: Annotated[Decimal, Query(gt=0, le=10000, allow_inf_nan=False, decimal_places=3)],
                   unit: Unit, session=Depends(get_session)):
    return nutrition(*find_food(session, food_id), Portion(amount=amount, unit=unit))
