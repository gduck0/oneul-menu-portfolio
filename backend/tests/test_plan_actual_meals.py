from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from app.main import app
from app.personal_models import MealEntry
from app.planner_models import MealPlan
from app.planner_service import menu_catalog
from app.security import utcnow
from test_food_api import catalog_client
from test_planner import planner_client, create, change
from test_continuity import action, record


def rice_plan(client,session):
    rice=next(menu for menu in menu_catalog(session) if menu['name']=='기장밥')
    plan,_=create(client)
    return change(client,plan,'breakfast','set',menu_id=rice['menu_id'],amount_g='160')[0]


def actual(client,plan):
    response=client.get(f"/api/plans/{plan['id']}/actual-meals")
    assert response.status_code==200,response.text
    return response.json()


def test_actual_summary_uses_latest_record_without_overwriting_plan_or_retry(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    planned=deepcopy(plan['meals'][0])
    result,request=record(client,plan,{planned['items'][0]['item_id']:'80'})
    saved=deepcopy(result['plan'])
    before_get=client.get('/api/plans/'+plan['id']).json()
    entry=result['records'][0]
    value=actual(client,saved)
    assert value['plan_version']==saved['version']
    assert value['meals']['breakfast']['items'][0]['portion']['amount']=='80'
    assert value['meals']['breakfast']['nutrients']==entry['nutrients']
    edit={'client_request_id':str(uuid4()),'expected_version':entry['version'],'portion':{'amount':'100','unit':'g'},'eaten_at':entry['eaten_at'],'notes':'실제 분량 수정'}
    updated=client.patch('/api/meals/'+entry['id'],json=edit).json()['meal']
    latest=actual(client,saved)['meals']['breakfast']
    assert latest['items'][0]['portion']['amount']=='100' and latest['nutrients']==updated['nutrients']
    assert client.get('/api/plans/'+plan['id']).json()==before_get
    assert session.get(MealPlan,plan['id']).payload==saved
    assert saved['meals'][0]['items']==planned['items']
    assert client.post(f"/api/plans/{plan['id']}/meals/breakfast/record",json=request).json()==result


def test_partial_nutrition_unknown_amount_and_skipped_foods_are_not_zero(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    plan,_=change(client,plan,'breakfast','add',custom_name='분량 모르는 반찬')
    plan,_=change(client,plan,'breakfast','add',custom_name='안 먹은 반찬',amount_g='30')
    before=deepcopy(plan['meals'][0]['items'])
    response=client.post(f"/api/plans/{plan['id']}/meals/breakfast/record",json={'expected_version':plan['version'],'eaten_at':datetime.now(timezone.utc).isoformat(),'amounts':{before[0]['item_id']:'80',before[1]['item_id']:None},'skipped_item_ids':[before[2]['item_id']]})
    assert response.status_code==200,response.text
    saved=response.json()['plan']
    summary=actual(client,saved)['meals']['breakfast']
    assert summary['state']=='ready' and len(summary['items'])==2
    assert summary['items'][1]['portion'] is None
    assert summary['items'][1]['nutrients']['energy_kcal'] is None
    assert 'energy_kcal' in summary['missing_nutrients']
    assert summary['skipped_foods']==['안 먹은 반찬']
    assert saved['meals'][0]['items']==before


def test_cancel_restore_summary_follows_active_record_links(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    result,_=record(client,plan)
    cancelled,_=action(client,result['records'][0],'cancel')
    assert actual(client,cancelled['plan'])['meals']=={}
    restored,_=action(client,cancelled['meals'][0],'restore')
    assert actual(client,restored['plan'])['meals']['breakfast']['items'][0]['id']==result['records'][0]['id']


def test_summary_does_not_expose_another_owner_plan(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    saved,_=record(client,plan)
    with TestClient(app) as other:
        assert other.get(f"/api/plans/{plan['id']}/actual-meals").status_code==404
    row=session.get(MealEntry,saved['records'][0]['id'])
    row.owner_key='guest:another-owner'
    session.flush()
    assert actual(client,saved['plan'])['meals']['breakfast']=={'state':'unavailable'}


def test_missing_or_cancelled_link_is_unavailable_instead_of_planned_fallback(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    saved,_=record(client,plan)
    before_get=client.get('/api/plans/'+plan['id']).json()
    row=session.get(MealEntry,saved['records'][0]['id'])
    row.cancelled_at=utcnow()
    session.flush()
    assert actual(client,saved['plan'])['meals']['breakfast']=={'state':'unavailable'}
    assert client.get('/api/plans/'+plan['id']).json()==before_get


def test_legacy_owned_links_are_read_without_backfilling_business_data(planner_client):
    client,session=planner_client
    plan=rice_plan(client,session)
    saved,_=record(client,plan)
    row=session.get(MealEntry,saved['records'][0]['id'])
    row.payload={key:value for key,value in row.payload.items() if key not in ['plan_id','meal_key','record_group_id']}
    session.flush()
    before=deepcopy(row.payload)
    assert actual(client,saved['plan'])['meals']['breakfast']['state']=='ready'
    assert row.payload==before
    row.payload={**row.payload,'plan_id':str(uuid4())}
    session.flush()
    assert actual(client,saved['plan'])['meals']['breakfast']=={'state':'unavailable'}
