from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from app.food_source import convert_row
from app.food_models import Food, NutritionSnapshot
from app.main import app
from app.planner_service import menu_definitions
from test_food_api import catalog_client


@pytest.fixture
def planner_client(catalog_client):
    client,session,ids,_=catalog_client
    snapshot=session.scalar(select(NutritionSnapshot).where(NutritionSnapshot.active.is_(True)))
    present=set(session.scalars(select(Food.food_code).where(Food.snapshot_id==snapshot.id)))
    for row in menu_definitions()['reference_rows']:
        if row['FOOD_CD'] not in present:
            session.add(Food(**convert_row(row,snapshot.id)))
    session.flush()
    return client,session


def create(client,**changes):
    body={'client_request_id':str(uuid4()),'plan_date':date.today().isoformat(),'energy_target':'1800',**changes}
    response=client.post('/api/plans',json=body)
    assert response.status_code==201,response.text
    return response.json(),body


def change(client,plan,meal_key,action,**fields):
    body={'client_request_id':str(uuid4()),'expected_version':plan['version'],'meal_key':meal_key,'action':action,**fields}
    response=client.patch('/api/plans/'+plan['id'],json=body)
    assert response.status_code==200,response.text
    return response.json(),body
