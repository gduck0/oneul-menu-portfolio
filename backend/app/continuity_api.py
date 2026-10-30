from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import secrets
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field, field_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.food_contracts import Portion, StrictModel
from app.preference_service import owner_identity
from app.personal_contracts import MealResponse
from app.personal_models import GuestTransfer, MealChange, MealEntry, MenuFeedback, PersonalSettings
from app.planner_api import digest, update_plan
from app.planner_models import MealPlan
from app.security import GUEST_COOKIE, guest_identity, require_user, set_cookie, utcnow
from app.session_dependency import get_session

router = APIRouter(prefix='/api')


@router.get('/meal-groups')
def grouped_meals(request: Request, response: Response, limit: int = Query(default=10, ge=1, le=50),
                  offset: int = Query(default=0, ge=0, le=10000), cancelled: bool = False, session=Depends(get_session)):
    from app.meal_groups import meal_groups
    owner, _, _ = owner_identity(session, request, response)
    return meal_groups(session, owner, cancelled, limit, offset)


class MealAction(StrictModel):
    client_request_id: UUID = Field(default_factory=uuid4)
    expected_version: int = Field(ge=1)


class MealEdit(MealAction):
    portion: Portion | None
    eaten_at: datetime
    notes: str = Field(default='', max_length=300)

    @field_validator('eaten_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('식사 시각에 시간대가 필요해요.')
        return value


class TransferRequest(StrictModel):
    client_request_id: UUID = Field(default_factory=uuid4)
    include_settings: bool = True


def meal_response(row):
    return MealResponse.model_validate({**{key: value for key, value in row.payload.items() if key != 'portion_reference'}, 'version': row.version, 'cancelled_at': row.cancelled_at}).model_dump(mode='json')


def owned_meal(session, meal_id, owner):
    row = session.scalar(select(MealEntry).where(MealEntry.id == str(meal_id), MealEntry.owner_key == owner))
    if row is None:
        raise HTTPException(404, '식사 기록을 찾지 못했어요.')
    return row


def previous_change(session, owner, request_id, input_hash):
    row = session.scalar(select(MealChange).where(MealChange.owner_key == owner, MealChange.client_request_id == str(request_id)))
    if row:
        if row.input_hash != input_hash:
            raise HTTPException(409, '같은 변경 번호로 다른 내용을 저장할 수 없어요.')
        return row.payload
    return None


def save_change(session, row, data, action, before, result, input_hash):
    session.add(MealChange(id=str(uuid4()), owner_key=row.owner_key, client_request_id=str(data.client_request_id),
        meal_id=row.id, input_hash=input_hash, action=action, before=before, payload=result, created_at=utcnow()))
    session.commit()
    return result


@router.patch('/meals/{meal_id}')
def edit_meal(meal_id: UUID, data: MealEdit, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    input_hash = digest({'meal_id': str(meal_id), 'action': 'edit', **data.model_dump(mode='json', exclude={'client_request_id'})})
    previous = previous_change(session, owner, data.client_request_id, input_hash)
    if previous:
        return previous
    row = session.scalar(select(MealEntry).where(MealEntry.id == str(meal_id), MealEntry.owner_key == owner).with_for_update())
    if row is None:
        raise HTTPException(404, '식사 기록을 찾지 못했어요.')
    if row.version != data.expected_version or row.cancelled_at:
        raise HTTPException(409, '기록이 바뀌었어요. 최신 기록을 불러와 주세요.')
    if data.eaten_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(422, '미래의 식사 시각은 기록할 수 없어요.')
    before = [meal_response(row)]
    payload = deepcopy(row.payload)
    if data.portion is None and payload['food_id'] is not None:
        raise HTTPException(422, '등록 음식은 기준 분량을 선택하거나 먹은 양을 입력해 주세요.')
    if data.portion is not None and payload['portion'] is not None and data.portion.unit != payload['portion']['unit']:
        raise HTTPException(422, '기록한 g·mL 단위를 유지해 주세요.')
    # Keep the original per-unit reference, so repeated edits never compound rounding.
    if payload['food_id'] is not None:
        reference = payload.get('portion_reference') or {'portion': deepcopy(row.payload['portion']), 'nutrients': deepcopy(row.payload['nutrients'])}
        ratio = data.portion.amount / Decimal(reference['portion']['amount'])
        payload['nutrients'] = {key: None if value is None else str((Decimal(value) * ratio).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)) for key, value in reference['nutrients'].items()}
        payload['portion_reference'] = reference
    payload.update(portion=data.portion.model_dump(mode='json') if data.portion else None, eaten_at=data.eaten_at.isoformat(), notes=data.notes)
    if payload['nutrition']:
        payload['nutrition'] = {**payload['nutrition'], 'portion': payload['portion'], 'nutrients': payload['nutrients']}
    row.version += 1
    row.eaten_at = data.eaten_at
    row.payload = payload
    result = {'meal': meal_response(row)}
    return save_change(session, row, data, 'edit', before, result, input_hash)


@router.get('/meals/{meal_id}')
def meal_detail(meal_id: UUID, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    return meal_response(owned_meal(session, meal_id, owner))


def linked_plan(session, row, owner):
    plan_id = row.payload.get('plan_id')
    statement = select(MealPlan).where(MealPlan.owner_key == owner)
    if plan_id:
        statement = statement.where(MealPlan.id == plan_id)
    else:
        statement = statement.where(MealPlan.payload['meals'].contains([{'records': [{'id': row.id}]}]))
    return session.scalar(statement.with_for_update())


def change_meal_state(meal_id, data, action, request, response, session):
    owner, _, _ = owner_identity(session, request, response)
    input_hash = digest({'meal_id': str(meal_id), 'action': action, **data.model_dump(mode='json', exclude={'client_request_id'})})
    previous = previous_change(session, owner, data.client_request_id, input_hash)
    if previous:
        return previous
    row = owned_meal(session, meal_id, owner)
    plan = linked_plan(session, row, owner)
    meal = None
    if plan:
        meal = next((value for value in plan.payload['meals'] if value['key'] == row.payload.get('meal_key') or any(record['id'] == row.id for record in value.get('records', []))), None)
    ids = [row.id]
    if meal:
        ids = [record['id'] for record in meal.get('records', [])] if action == 'cancel' else meal.get('cancelled_record_ids', [])
        if row.id not in ids:
            raise HTTPException(409, '이 끼니에 새 기록이 있어요. 최신 식단을 확인해 주세요.')
    entries = list(session.scalars(select(MealEntry).where(MealEntry.owner_key == owner, MealEntry.id.in_(ids)).order_by(MealEntry.id).with_for_update().execution_options(populate_existing=True)))
    row = next((value for value in entries if value.id == str(meal_id)), None)
    if row is None or row.version != data.expected_version:
        raise HTTPException(409, '기록이 바뀌었어요. 최신 기록을 불러와 주세요.')
    if (action == 'cancel' and any(value.cancelled_at for value in entries)) or (action == 'restore' and any(not value.cancelled_at for value in entries)):
        raise HTTPException(409, '기록 상태가 바뀌었어요. 새로 불러와 주세요.')
    if action == 'restore' and meal and (meal.get('consumed') or digest(meal['items']) != meal.get('cancelled_items_hash')):
        raise HTTPException(409, '취소 후 메뉴가 바뀌었어요. 원기록은 보존되어 있으며 식사 추가로 다시 남길 수 있어요.')
    before = [meal_response(value) for value in entries]
    for value in entries:
        if meal:
            value.payload = {**value.payload, 'plan_id': plan.id, 'meal_key': meal['key']}
        value.cancelled_at = utcnow() if action == 'cancel' else None
        value.version += 1
    result = {'meals': [meal_response(value) for value in entries], 'plan': None}
    if meal:
        payload = deepcopy(plan.payload)
        target = next(value for value in payload['meals'] if value['key'] == meal['key'])
        if action == 'cancel':
            target.update(consumed=False, locked=meal.get('locked_before_record', True), records=[],
                cancelled_record_ids=ids, cancelled_items_hash=digest(meal['items']), reason='식사 완료를 되돌렸어요. 계획 메뉴와 취소한 기록은 보존했어요.')
        else:
            target.update(consumed=True, locked=True, records=[{'id': value.id, 'food_id': value.payload['food_id'], 'name': value.payload['name']} for value in entries], cancelled_record_ids=[])
        result['plan'] = update_plan(plan, payload)
    return save_change(session, row, data, action, before, result, input_hash)


@router.post('/meals/{meal_id}/cancel')
def cancel_meal(meal_id: UUID, data: MealAction, request: Request, response: Response, session=Depends(get_session)):
    return change_meal_state(meal_id, data, 'cancel', request, response, session)


@router.post('/meals/{meal_id}/restore')
def restore_meal(meal_id: UUID, data: MealAction, request: Request, response: Response, session=Depends(get_session)):
    return change_meal_state(meal_id, data, 'restore', request, response, session)


@router.get('/meals/{meal_id}/changes')
def meal_changes(meal_id: UUID, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    owned_meal(session, meal_id, owner)
    rows = session.scalars(select(MealChange).where(MealChange.owner_key == owner).where(
        (MealChange.meal_id == str(meal_id)) | MealChange.before.contains([{'id': str(meal_id)}])).order_by(MealChange.created_at.desc()).limit(50))
    return [{'action': row.action, 'created_at': row.created_at, 'before': row.before} for row in rows]


@router.get('/guest-data')
def guest_data(request: Request, response: Response, session=Depends(get_session)):
    require_user(session, request)
    guest = 'g:' + guest_identity(request, response)
    claimed = session.scalar(select(GuestTransfer.id).where(GuestTransfer.guest_key == guest))
    return {'plans': 0 if claimed else session.scalar(select(func.count()).select_from(MealPlan).where(MealPlan.owner_key == guest)),
        'meals': 0 if claimed else session.scalar(select(func.count()).select_from(MealEntry).where(MealEntry.owner_key == guest)),
        'settings': False if claimed else session.get(PersonalSettings, guest) is not None}


@router.post('/guest-data/import')
def import_guest(data: TransferRequest, request: Request, response: Response, session=Depends(get_session)):
    owner, user, guest_hash = owner_identity(session, request, response)
    if user is None:
        raise HTTPException(401, '로그인 후 가져올 수 있어요.')
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'transfer:' + owner})
    input_hash = digest({'include_settings': data.include_settings})
    previous = session.scalar(select(GuestTransfer).where(GuestTransfer.user_key == owner, GuestTransfer.client_request_id == str(data.client_request_id)))
    if previous:
        if previous.input_hash != input_hash:
            raise HTTPException(409, '같은 가져오기 번호의 설정이 달라요.')
        if previous.guest_key == 'g:' + guest_hash:
            set_cookie(response, GUEST_COOKIE, secrets.token_urlsafe(32), 30)
        return previous.payload
    guest = 'g:' + guest_hash
    if session.scalar(select(GuestTransfer.id).where(GuestTransfer.guest_key == guest)):
        raise HTTPException(409, '이미 가져온 체험 자료예요.')
    settings = session.get(PersonalSettings, guest)
    result = {'plans': 0, 'meals': 0, 'settings_imported': False, 'settings_kept': False}
    for model in (MealPlan, MealEntry, MealChange):
        request_column = MealEntry.client_record_id if model is MealEntry else model.client_request_id
        source_requests = select(request_column).where(model.owner_key == guest)
        if session.scalar(select(model.id).where(model.owner_key == owner, request_column.in_(source_requests)).limit(1)):
            raise HTTPException(409, '계정에 같은 요청 번호의 자료가 있어요. 기존 자료를 보호하기 위해 가져오기를 중단했어요.')
    if settings and data.include_settings:
        imported = session.execute(insert(PersonalSettings).values(owner_key=owner, payload=settings.payload, updated_at=utcnow()).on_conflict_do_nothing(index_elements=['owner_key']).returning(PersonalSettings.owner_key)).scalar_one_or_none()
        result.update(settings_imported=imported is not None, settings_kept=imported is None)
    for model, key in ((MealPlan, 'plans'), (MealEntry, 'meals'), (MenuFeedback, None), (MealChange, None)):
        count = session.execute(update(model).where(model.owner_key == guest).values(owner_key=owner)).rowcount
        if key:
            result[key] = count
    session.add(GuestTransfer(id=str(uuid4()), guest_key=guest, user_key=owner, client_request_id=str(data.client_request_id), input_hash=input_hash, payload=result, created_at=utcnow()))
    session.commit()
    set_cookie(response, GUEST_COOKIE, secrets.token_urlsafe(32), 30)
    return result
