from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from uuid import UUID, uuid4, uuid5
from typing import Annotated

from pydantic import Field

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.food_catalog import NUTRIENT_FIELDS, normalize_name
from decimal import Decimal, ROUND_HALF_UP
from app.preference_service import owner_identity, settings_for
from app.personal_contracts import MealResponse
from app.preference_contracts import SettingsRequest
from app.personal_models import MealEntry
from app.personal_ranking import rating_scores
from app.planner_contracts import PlanEdit, PlanMealRecord, PlanRequest, PlanResponse
from app.planner_models import MealPlan, PlanOperation
from app.planner_service import (
    build_meals,
    exclusion_conflicts,
    grouped_food_search,
    manual_item,
    menu_catalog,
    menu_definitions,
    replace_meal,
    sum_nutrition,
    update_summary,
)
from app.security import utcnow
from app.session_dependency import get_session

router = APIRouter(prefix='/api')
ExclusionName = Annotated[str, Field(max_length=40)]


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def plan_input_hashes(inputs):
    normalized = deepcopy(inputs)
    if not normalized.get('fixed_meals'):
        normalized.pop('fixed_meals', None)
    for conditions in normalized.get('constraints', {}).values():
        if not conditions.get('prepared_sides'):
            conditions.pop('prepared_sides', None)
    current = digest(normalized)
    compatible = {current, digest(inputs)}
    if normalized['energy_target'] == '1800':
        compatible.add(digest({**normalized, 'energy_target': 1800}))
    return current, compatible


def context(session, owner, settings):
    prefs = settings_for(session, owner) if settings.get('personalize', True) else SettingsRequest()
    prefs = prefs.model_copy(update={'goal': settings.get('preference') or prefs.goal})
    return prefs, rating_scores(session, owner) if settings.get('personalize', True) else {}


def recent_plan_meals(session, owner, exclude_plan=None):
    query = select(MealPlan).where(MealPlan.owner_key == owner)
    if exclude_plan:
        query = query.where(MealPlan.id != exclude_plan)
    rows = session.scalars(query.order_by(MealPlan.created_at.desc(), MealPlan.id).limit(5))
    recent = {}
    for row in rows:
        for meal in row.payload['meals']:
            if meal['items']:
                recent.setdefault(meal['key'], []).append(meal)
    return recent


def recent_replacements(session, row, key):
    # 기존 변경 전 스냅샷을 읽으며 이력 자체를 수정하지 않는다.
    snapshots = session.scalars(
        select(PlanOperation.payload)
        .where(
            PlanOperation.plan_id == row.id,
            PlanOperation.payload['replacement_before']['key'].as_string() == key,
        )
        .order_by(PlanOperation.payload['result']['version'].as_integer().desc())
        .limit(5)
    )
    return [snapshot['replacement_before'] for snapshot in snapshots]


def find_plan(session, plan_id, owner, locked=False):
    statement = select(MealPlan).where(MealPlan.id == str(plan_id), MealPlan.owner_key == owner)
    if locked:
        statement = statement.with_for_update()
    row = session.scalar(statement)
    if row is None:
        raise HTTPException(404, '식단 계획을 찾지 못했어요.')
    return row


def operation(session, row, request_id, input_hash, compatible=None):
    previous = session.scalar(
        select(PlanOperation).where(
            PlanOperation.plan_id == row.id, PlanOperation.client_request_id == str(request_id)
        )
    )
    if previous:
        if previous.input_hash not in (compatible or {input_hash}):
            raise HTTPException(409, '같은 변경 번호로 다른 내용을 저장할 수 없어요.')
        return (
            previous.payload['result']
            if 'replacement_before' in previous.payload
            else previous.payload
        )
    return None


def save_operation(session, row, request_id, input_hash, payload, replacement_before=None):
    stored = (
        {'result': payload, 'replacement_before': replacement_before}
        if replacement_before is not None
        else payload
    )
    session.add(
        PlanOperation(
            id=str(uuid4()),
            plan_id=row.id,
            client_request_id=str(request_id),
            input_hash=input_hash,
            payload=stored,
        )
    )
    session.commit()


def update_plan(row, payload):
    now = utcnow()
    row.version += 1
    row.updated_at = now
    payload.update(version=row.version, updated_at=now.isoformat())
    row.payload = update_summary(payload)
    return row.payload


@router.get('/planner/menus')
def planner_menus(
    q: str = Query(default='', max_length=80),
    role: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=24, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=10000),
    avoided_foods: list[ExclusionName] = Query(default=[], max_length=30),
    session=Depends(get_session),
):
    menus = menu_catalog(session)
    query = normalize_name(q)
    filtered = [
        menu
        for menu in menus
        if (role is None or menu['role'] == role)
        and (not query or any(query in normalize_name(alias) for alias in menu['aliases']))
    ]
    filtered.sort(key=lambda menu: (normalize_name(menu['name']) != query, menu['name']))
    return {
        'items': [
            {**menu, 'excluded_by': exclusion_conflicts(menu, avoided_foods)}
            for menu in filtered[offset : offset + limit]
        ],
        'total': len(filtered),
        'available_total': len(menus),
        'catalog_version': menu_definitions()['version'],
    }


@router.get('/planner/menu-exclusion-check')
def menu_exclusion_check(
    menu_id: str | None = Query(default=None, max_length=40),
    custom_name: str | None = Query(default=None, min_length=1, max_length=100),
    avoided_foods: list[ExclusionName] = Query(default=[], max_length=30),
    session=Depends(get_session),
):
    if (menu_id is None) == (custom_name is None):
        raise HTTPException(422, '등록 메뉴 또는 직접 입력 이름 중 하나를 선택해 주세요.')
    if menu_id is not None:
        menu = next((item for item in menu_catalog(session) if item['menu_id'] == menu_id), None)
        if menu is None:
            raise HTTPException(
                404, '현재 선택할 수 있는 메뉴를 찾지 못했어요. 다시 검색해 주세요.'
            )
    else:
        name = custom_name.strip()
        if not name:
            raise HTTPException(422, '메뉴 이름을 입력해 주세요.')
        menu = {
            'menu_id': 'name-check',
            'name': name,
            'source_name': name,
            'ingredients': [],
            'role': 'main',
        }
    return {
        'conflicts': exclusion_conflicts(menu, avoided_foods),
        'basis': 'menu_reference' if menu_id is not None else 'name_only',
    }


@router.get('/food-groups')
def food_groups(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10000),
    session=Depends(get_session),
):
    return grouped_food_search(session, q, limit, offset)


@router.post('/plans', response_model=PlanResponse, status_code=201)
def create_plan(
    data: PlanRequest, request: Request, response: Response, session=Depends(get_session)
):
    owner, _, _ = owner_identity(session, request, response)
    inputs = data.model_dump(mode='json', exclude={'client_request_id'})
    input_hash, compatible = plan_input_hashes(inputs)
    previous = session.scalar(
        select(MealPlan).where(
            MealPlan.owner_key == owner, MealPlan.client_request_id == str(data.client_request_id)
        )
    )
    if previous:
        if previous.input_hash not in compatible:
            raise HTTPException(409, '같은 생성 번호로 다른 계획을 만들 수 없어요.')
        response.status_code = 200
        return previous.payload
    menus = menu_catalog(session)
    if not menus:
        raise HTTPException(503, '식단용 메뉴 자료를 준비 중이에요.')
    prefs, scores = context(session, owner, inputs)
    inputs['preference'] = data.preference or prefs.goal
    now = utcnow()
    plan_id = str(uuid4())
    payload = {
        'id': plan_id,
        'version': 1,
        'plan_date': data.plan_date.isoformat(),
        'created_at': now.isoformat(),
        'updated_at': now.isoformat(),
        'settings': inputs,
        'meals': build_meals(data, menus, prefs, scores, recent_plan_meals(session, owner)),
        'catalog_version': menu_definitions()['version'],
    }
    payload = update_summary(payload)
    created = session.execute(
        insert(MealPlan)
        .values(
            id=plan_id,
            owner_key=owner,
            client_request_id=str(data.client_request_id),
            input_hash=input_hash,
            plan_date=data.plan_date,
            version=1,
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(constraint='uq_meal_plan_request')
        .returning(MealPlan.id)
    ).scalar_one_or_none()
    session.commit()
    if created is None:
        previous = session.scalar(
            select(MealPlan).where(
                MealPlan.owner_key == owner,
                MealPlan.client_request_id == str(data.client_request_id),
            )
        )
        if previous.input_hash not in compatible:
            raise HTTPException(409, '같은 생성 번호로 다른 계획을 만들 수 없어요.')
        response.status_code = 200
        return previous.payload
    return payload


@router.get('/plans', response_model=list[PlanResponse])
def plans(
    request: Request,
    response: Response,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    on_date: date | None = Query(default=None, alias='date'),
    session=Depends(get_session),
):
    owner, _, _ = owner_identity(session, request, response)
    query = select(MealPlan).where(MealPlan.owner_key == owner)
    if on_date is not None:
        query = query.where(MealPlan.plan_date == on_date)
    return [
        row.payload
        for row in session.scalars(
            query.order_by(MealPlan.plan_date.desc(), MealPlan.created_at.desc(), MealPlan.id)
            .limit(limit)
            .offset(offset)
        )
    ]


@router.get('/plan-history')
def plan_history(
    request: Request,
    response: Response,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    on_date: date | None = Query(default=None, alias='date'),
    session=Depends(get_session),
):
    owner, _, _ = owner_identity(session, request, response)
    conditions = [MealPlan.owner_key == owner]
    if on_date is not None:
        conditions.append(MealPlan.plan_date == on_date)
    rows = session.scalars(
        select(MealPlan)
        .where(*conditions)
        .order_by(MealPlan.plan_date.desc(), MealPlan.created_at.desc(), MealPlan.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        'items': [row.payload for row in rows],
        'total': session.scalar(select(func.count()).select_from(MealPlan).where(*conditions)),
    }


@router.get('/plans/{plan_id}', response_model=PlanResponse)
def plan(plan_id: UUID, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    return find_plan(session, plan_id, owner).payload


@router.get('/plans/{plan_id}/actual-meals')
def actual_plan_meals(
    plan_id: UUID, request: Request, response: Response, session=Depends(get_session)
):
    owner, _, _ = owner_identity(session, request, response)
    row = find_plan(session, plan_id, owner)
    consumed = [meal for meal in row.payload['meals'] if meal.get('consumed')]
    ids = {record['id'] for meal in consumed for record in meal.get('records', [])}
    entries = (
        {
            entry.id: entry
            for entry in session.scalars(
                select(MealEntry).where(
                    MealEntry.owner_key == owner,
                    MealEntry.id.in_(ids),
                    MealEntry.cancelled_at.is_(None),
                )
            )
        }
        if ids
        else {}
    )
    meals = {}
    for meal in consumed:
        record_ids = [record['id'] for record in meal.get('records', [])]
        available = (
            bool(record_ids)
            and len(set(record_ids)) == len(record_ids)
            and all(
                record_id in entries
                and entries[record_id].payload.get('plan_id') in [None, row.id]
                and entries[record_id].payload.get('meal_key') in [None, meal['key']]
                for record_id in record_ids
            )
        )
        if not available:
            meals[meal['key']] = {'state': 'unavailable'}
            continue
        items = [
            MealResponse.model_validate(
                {
                    **{
                        key: value
                        for key, value in entries[record_id].payload.items()
                        if key != 'portion_reference'
                    },
                    'version': entries[record_id].version,
                    'cancelled_at': None,
                }
            ).model_dump(mode='json')
            for record_id in record_ids
        ]
        nutrients, missing = sum_nutrition(items)
        skipped = list(
            dict.fromkeys(
                [item['name'] for item in meal.get('skipped_items', [])]
                + [name for item in items for name in item.get('skipped_foods', [])]
            )
        )
        meals[meal['key']] = {
            'state': 'ready',
            'items': items,
            'nutrients': nutrients,
            'missing_nutrients': missing,
            'skipped_foods': skipped,
        }
    return {'plan_id': row.id, 'plan_version': row.version, 'meals': meals}


@router.patch('/plans/{plan_id}', response_model=PlanResponse)
def edit_plan(
    plan_id: UUID,
    data: PlanEdit,
    request: Request,
    response: Response,
    session=Depends(get_session),
):
    owner, _, _ = owner_identity(session, request, response)
    row = find_plan(session, plan_id, owner, True)
    inputs = {'kind': 'edit', **data.model_dump(mode='json', exclude={'client_request_id'})}
    if inputs.get('replacement_request_id') is None:
        inputs.pop('replacement_request_id', None)
    compatible = {digest(inputs)}
    if inputs.get('constraints') and not inputs['constraints'].get('prepared_sides'):
        inputs['constraints'].pop('prepared_sides', None)
    input_hash = digest(inputs)
    compatible.add(input_hash)
    previous = operation(session, row, data.client_request_id, input_hash, compatible)
    if previous:
        return previous
    if row.version != data.expected_version:
        raise HTTPException(409, '다른 변경이 저장됐어요. 최신 계획을 다시 불러와 주세요.')
    payload = deepcopy(row.payload)
    meal = next((meal for meal in payload['meals'] if meal['key'] == data.meal_key), None)
    if meal is None:
        raise HTTPException(404, '이 계획의 끼니를 찾지 못했어요.')
    if meal.get('consumed'):
        raise HTTPException(
            409, '이미 먹은 것으로 기록한 끼니예요. 실제 식사 기록을 유지해 주세요.'
        )
    replacement_before = None
    if data.action == 'undo_replace':
        undo = meal.get('undo_replacement')
        if not undo or undo['request_id'] != str(data.replacement_request_id):
            raise HTTPException(
                409, '이 추천 변경은 더 이상 되돌릴 수 없어요. 최신 계획을 확인해 주세요.'
            )
        source = session.scalar(
            select(PlanOperation).where(
                PlanOperation.plan_id == row.id,
                PlanOperation.client_request_id == str(data.replacement_request_id),
            )
        )
        before = source.payload.get('replacement_before') if source else None
        if not before or before['key'] != data.meal_key:
            raise HTTPException(409, '되돌릴 추천 변경을 찾지 못했어요.')
        payload['meals'][payload['meals'].index(meal)] = deepcopy(before)
        result = update_plan(row, payload)
        save_operation(session, row, data.client_request_id, input_hash, result)
        return result
    previous_undo = meal.pop('undo_replacement', None)
    menus = menu_catalog(session)
    if data.action == 'lock':
        meal['locked'] = data.locked
    elif data.action == 'replace':
        before = deepcopy(meal)
        prefs, scores = context(session, owner, payload['settings'])
        recent = (
            [before]
            + recent_replacements(session, row, data.meal_key)
            + recent_plan_meals(session, owner, row.id).get(data.meal_key, [])
        )
        payload = replace_meal(
            payload,
            data.meal_key,
            menus,
            prefs,
            scores,
            data.constraints.model_dump(mode='json') if data.constraints else None,
            recent_meals=recent,
        )
        if meal['items'] != before['items']:
            replacement_before = before
            meal['undo_replacement'] = {
                'request_id': str(data.client_request_id),
                'names': [item['name'] for item in before['items']],
            }
        elif previous_undo:
            meal['undo_replacement'] = previous_undo
    elif data.action == 'set':
        item = manual_item(menus, data.menu_id, data.custom_name, data.amount_g)
        meal.update(
            items=[item],
            status='ready',
            reason='직접 정한 메뉴예요. 다른 끼니를 바꿔도 유지해요. 끼니 전체 고정은 따로 선택할 수 있어요.',
            minutes=item['minutes'],
        )
        meal['nutrients'], _ = sum_nutrition(meal['items'])
    elif data.action in ('add', 'remove', 'update_item'):
        if data.action == 'add':
            if len(meal['items']) >= 12:
                raise HTTPException(422, '한 끼에 음식은 12개까지 담을 수 있어요.')
            item = manual_item(menus, data.menu_id, data.custom_name, data.amount_g)
            item['item_id'] = str(uuid4())
            meal['items'].append(item)
        else:
            index = next(
                (
                    index
                    for index, item in enumerate(meal['items'])
                    if item['item_id'] == data.item_id
                ),
                None,
            )
            if index is None:
                raise HTTPException(404, '변경할 음식을 찾지 못했어요.')
            if data.action == 'remove':
                meal['items'].pop(index)
            else:
                item = manual_item(menus, data.menu_id, data.custom_name, data.amount_g)
                item['item_id'] = str(uuid4())
                meal['items'][index] = item
        if not meal['items']:
            meal['locked'] = False
        meal.update(
            status='ready' if meal['items'] else 'empty',
            minutes=None,
            reason='직접 구성한 끼니예요. 다른 끼니를 바꿔도 유지해요. 끼니 전체 고정은 따로 선택할 수 있어요.',
        )
        meal['nutrients'], _ = sum_nutrition(meal['items'])
    else:
        item = next((item for item in meal['items'] if item['item_id'] == data.item_id), None)
        if item is None:
            raise HTTPException(404, '변경할 음식을 찾지 못했어요.')
        if item['menu_id']:
            if data.amount_g is None:
                raise HTTPException(
                    422, '등록 메뉴는 기준 분량을 선택하거나 먹을 양을 입력해 주세요.'
                )
            reference = item.get('reference_nutrients')
            if reference is None:
                raise HTTPException(
                    409, '기록 당시의 영양 기준을 확인하지 못했어요. 메뉴를 다시 선택해 주세요.'
                )
            item['amount_g'] = str(data.amount_g)
            item['nutrients'] = {
                field: str(
                    (Decimal(reference[field]) * data.amount_g / 100).quantize(
                        Decimal('.01'), rounding=ROUND_HALF_UP
                    )
                )
                for field in NUTRIENT_FIELDS
            }
        else:
            item['amount_g'] = str(data.amount_g) if data.amount_g is not None else None
        meal['nutrients'], _ = sum_nutrition(meal['items'])
        meal['reason'] = (
            '입력한 분량으로 참고 영양을 다시 계산했어요.'
            if item['menu_id']
            else '직접 입력 음식의 분량을 저장했어요. 모르는 분량과 영양은 추정하지 않아요.'
        )
    result = update_plan(row, payload)
    save_operation(session, row, data.client_request_id, input_hash, result, replacement_before)
    return result


@router.post('/plans/{plan_id}/meals/{meal_key}/record')
def record_plan_meal(
    plan_id: UUID,
    meal_key: str,
    data: PlanMealRecord,
    request: Request,
    response: Response,
    session=Depends(get_session),
):
    if data.eaten_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(422, '미래의 식사 시각은 기록할 수 없어요.')
    owner, _, _ = owner_identity(session, request, response)
    row = find_plan(session, plan_id, owner, True)
    inputs = data.model_dump(mode='json', exclude={'client_record_id'})
    if not inputs.get('amounts'):
        inputs.pop('amounts', None)
    if not inputs.get('skipped_item_ids'):
        inputs.pop('skipped_item_ids', None)
    input_hash = digest({'kind': 'record', 'meal_key': meal_key, **inputs})
    previous = operation(session, row, data.client_record_id, input_hash)
    if previous:
        return previous
    if row.version != data.expected_version:
        raise HTTPException(409, '계획이 변경됐어요. 최신 계획을 확인해 주세요.')
    payload = deepcopy(row.payload)
    meal = next((meal for meal in payload['meals'] if meal['key'] == meal_key), None)
    if meal is None:
        raise HTTPException(404, '이 계획의 끼니를 찾지 못했어요.')
    if meal.get('consumed'):
        raise HTTPException(409, '이미 먹은 것으로 기록한 끼니예요.')
    if not meal['items']:
        raise HTTPException(422, '먹은 메뉴를 먼저 선택해 주세요.')
    item_ids = {item['item_id'] for item in meal['items']}
    skipped = set(data.skipped_item_ids)
    if (set(data.amounts) | skipped) - item_ids:
        raise HTTPException(422, '이 끼니의 음식만 기록할 수 있어요.')
    if set(data.amounts) & skipped:
        raise HTTPException(422, '먹지 않은 음식에는 실제 먹은 양을 함께 입력할 수 없어요.')
    if skipped == item_ids:
        raise HTTPException(
            422, '먹은 음식을 하나 이상 선택해 주세요. 아직 먹지 않았다면 기록 창을 닫아 주세요.'
        )
    skipped_foods = [item['name'] for item in meal['items'] if item['item_id'] in skipped]
    records = []
    for item in meal['items']:
        if item['item_id'] in skipped:
            continue
        amount = data.amounts.get(
            item['item_id'], Decimal(item['amount_g']) if item['amount_g'] is not None else None
        )
        if amount is None and item['food'] is not None:
            raise HTTPException(
                422, '등록 메뉴는 기준 분량을 선택하거나 실제 먹은 양을 입력해 주세요.'
            )
        ratio = (
            amount / Decimal(item['amount_g'])
            if amount is not None and item['amount_g'] is not None
            else None
        )
        nutrients = {
            field: (
                None
                if value is None or ratio is None
                else str((Decimal(value) * ratio).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
            )
            for field, value in item['nutrients'].items()
        }
        portion = {'amount': str(amount), 'unit': 'g'} if amount is not None else None
        calculated = (
            {
                'food': item['food'],
                'portion': portion,
                'nutrients': nutrients,
                'missing_nutrients': [],
            }
            if item['food']
            else None
        )
        result = MealResponse(
            id=str(uuid4()),
            name=item['name'],
            food_id=item['food']['id'] if item['food'] else None,
            portion=portion,
            eaten_at=data.eaten_at,
            notes='식단 계획에서 먹은 식사로 기록',
            nutrients=nutrients,
            nutrition=calculated,
            nutrition_source='menu_reference' if calculated else 'unknown',
            plan_id=row.id,
            meal_key=meal_key,
            record_group_id=str(data.client_record_id),
            skipped_foods=skipped_foods,
        )
        body = result.model_dump(mode='json')
        session.add(
            MealEntry(
                id=result.id,
                owner_key=owner,
                client_record_id=str(uuid5(data.client_record_id, item['item_id'])),
                input_hash=input_hash,
                eaten_at=data.eaten_at,
                payload=body,
            )
        )
        records.append(body)
    meal.pop('undo_replacement', None)
    meal.update(
        locked_before_record=meal['locked'],
        consumed=True,
        locked=True,
        skipped_items=[
            {'item_id': item['item_id'], 'name': item['name']}
            for item in meal['items']
            if item['item_id'] in skipped
        ],
        records=[
            {'id': record['id'], 'food_id': record['food_id'], 'name': record['name']}
            for record in records
        ],
        reason='먹은 것으로 기록했어요. 실제 분량은 식사 기록에서 확인하고 수정할 수 있어요.',
    )
    updated = update_plan(row, payload)
    result = {'plan': updated, 'records': records}
    save_operation(session, row, data.client_record_id, input_hash, result)
    return result
