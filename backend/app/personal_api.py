from datetime import timedelta
import hashlib
import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.food_catalog import find_food, nutrition
from app.personal_contracts import FeedbackRequest, FeedbackResponse, MealHistory, MealRequest, MealResponse
from app.personal_models import MealEntry, MenuFeedback
from app.record_models import RecommendationEvent
from app.preference_service import owner_identity
from app.security import utcnow
from app.session_dependency import get_session

router = APIRouter(prefix='/api')


def event_owner(event, user, guest_hash):
    return event.user_id == user.id if user else event.user_id is None and event.guest_token_hash == guest_hash


@router.post('/meals', response_model=MealResponse, status_code=201)
def save_meal(data: MealRequest, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    if data.eaten_at > utcnow() + timedelta(minutes=5):
        raise HTTPException(422, '미래의 식사 시각은 기록할 수 없어요.')
    values = data.model_dump(mode='json', exclude={'client_record_id'})
    digest = hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()
    existing = session.scalar(select(MealEntry).where(MealEntry.owner_key==owner,MealEntry.client_record_id==str(data.client_record_id)))
    if existing:
        if existing.input_hash != digest:
            raise HTTPException(409, '이미 사용한 기록 번호예요. 새 기록으로 입력해 주세요.')
        response.status_code=200
        return MealResponse.model_validate({**{key:value for key,value in existing.payload.items() if key != 'portion_reference'}, 'version':existing.version, 'cancelled_at':existing.cancelled_at})
    calculated = nutrition(*find_food(session,data.food_id), data.portion) if data.food_id else None
    result=MealResponse(id=str(uuid4()),name=calculated.food.name if calculated else data.name,food_id=data.food_id,
                        portion=data.portion,eaten_at=data.eaten_at,notes=data.notes,
                        nutrients=calculated.nutrients if calculated else {'energy_kcal':None,'protein_g':None,'fat_g':None,'carbohydrate_g':None},
                        nutrition=calculated.model_dump(mode='json') if calculated else None,nutrition_source='catalog' if calculated else 'unknown')
    statement=insert(MealEntry).values(id=result.id,owner_key=owner,client_record_id=str(data.client_record_id),input_hash=digest,
                                      eaten_at=data.eaten_at,payload=result.model_dump(mode='json'))
    created=session.execute(statement.on_conflict_do_nothing(index_elements=['owner_key','client_record_id']).returning(MealEntry.id)).scalar_one_or_none()
    session.commit()
    if created is None:
        existing=session.scalar(select(MealEntry).where(MealEntry.owner_key==owner,MealEntry.client_record_id==str(data.client_record_id)))
        if existing.input_hash != digest:
            raise HTTPException(409,'이미 사용한 기록 번호예요. 새 기록으로 입력해 주세요.')
        response.status_code=200
        return MealResponse.model_validate({**{key:value for key,value in existing.payload.items() if key != 'portion_reference'}, 'version':existing.version, 'cancelled_at':existing.cancelled_at})
    return result


@router.get('/meals', response_model=MealHistory)
def meals(request: Request,response: Response,limit: int=Query(default=20,ge=1,le=50),offset: int=Query(default=0,ge=0,le=10000),cancelled: bool=False,session=Depends(get_session)):
    owner,_,_=owner_identity(session,request,response)
    conditions=(MealEntry.owner_key==owner, MealEntry.cancelled_at.is_not(None) if cancelled else MealEntry.cancelled_at.is_(None))
    rows=session.scalars(select(MealEntry).where(*conditions).order_by(MealEntry.eaten_at.desc(),MealEntry.id).limit(limit).offset(offset)).all()
    total=session.scalar(select(func.count()).select_from(MealEntry).where(*conditions))
    return MealHistory(items=[MealResponse.model_validate({**{key:value for key,value in row.payload.items() if key != 'portion_reference'},'version':row.version,'cancelled_at':row.cancelled_at}) for row in rows],total=total)


def feedback_response(row):
    return FeedbackResponse(id=row.id,phase=row.phase,context_id=row.context_id,food_id=row.food_id,rating=row.rating,reason=row.reason,updated_at=row.updated_at)


@router.get('/feedback', response_model=list[FeedbackResponse])
def feedback_list(request: Request,response: Response,session=Depends(get_session)):
    owner,_,_=owner_identity(session,request,response)
    return [feedback_response(row) for row in session.scalars(select(MenuFeedback).where(MenuFeedback.owner_key==owner).order_by(MenuFeedback.updated_at.desc()).limit(500))]


@router.put('/feedback', response_model=FeedbackResponse)
def save_feedback(data: FeedbackRequest,request: Request,response: Response,session=Depends(get_session)):
    owner,user,guest=owner_identity(session,request,response)
    if data.phase=='recommendation':
        event=session.get(RecommendationEvent,str(data.context_id))
        if event is None or not event_owner(event,user,guest):
            raise HTTPException(404,'이 추천을 평가할 수 없어요.')
        allowed={item['nutrition']['food']['id'] for item in event.payload['items']} | {event.payload['original']['food']['id']}
        if data.food_id not in allowed:
            raise HTTPException(422,'추천에서 확인한 메뉴를 평가해 주세요.')
    else:
        meal=session.get(MealEntry,str(data.context_id))
        if meal is None or meal.owner_key!=owner or meal.cancelled_at is not None:
            raise HTTPException(404,'이 식사 기록을 평가할 수 없어요.')
        if data.food_id!=meal.payload['food_id']:
            raise HTTPException(422,'기록한 음식과 평가 메뉴가 일치해야 해요.')
    code=find_food(session,data.food_id)[0].food_code if data.food_id else None
    statement=insert(MenuFeedback).values(id=str(uuid4()),owner_key=owner,context_id=str(data.context_id),phase=data.phase,
                                          food_id=data.food_id,food_code=code,rating=data.rating,reason=data.reason,updated_at=utcnow())
    saved=session.execute(statement.on_conflict_do_update(constraint='uq_menu_feedback_context',set_={
        'rating':statement.excluded.rating,'reason':statement.excluded.reason,'updated_at':statement.excluded.updated_at}).returning(MenuFeedback.id)).scalar_one()
    session.commit()
    return feedback_response(session.get(MenuFeedback,saved))


@router.delete('/feedback/{feedback_id}',status_code=204)
def delete_feedback(feedback_id: UUID,request: Request,response: Response,session=Depends(get_session)):
    owner,_,_=owner_identity(session,request,response)
    row=session.get(MenuFeedback,str(feedback_id))
    if row is None or row.owner_key!=owner:
        raise HTTPException(404,'평가를 찾지 못했어요.')
    session.delete(row);session.commit()
