from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.dialects.postgresql import insert

from app.personal_models import PersonalSettings
from app.preference_contracts import SettingsRequest
from app.preference_service import owner_identity, settings_for
from app.security import utcnow
from app.session_dependency import get_session

router = APIRouter(prefix='/api')


@router.get('/preferences', response_model=SettingsRequest)
def preferences(request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    return settings_for(session, owner)


@router.put('/preferences', response_model=SettingsRequest)
def save_preferences(data: SettingsRequest, request: Request, response: Response, session=Depends(get_session)):
    owner, _, _ = owner_identity(session, request, response)
    statement = insert(PersonalSettings).values(owner_key=owner, payload=data.model_dump(mode='json'), updated_at=utcnow())
    session.execute(statement.on_conflict_do_update(index_elements=['owner_key'], set_={'payload':statement.excluded.payload,'updated_at':statement.excluded.updated_at}))
    session.commit()
    return data
