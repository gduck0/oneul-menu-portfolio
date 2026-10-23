import secrets

from fastapi import HTTPException
from sqlalchemy import select, text

from app.personal_models import GuestTransfer, PersonalSettings
from app.preference_contracts import SettingsRequest
from app.security import GUEST_COOKIE, current_user, guest_identity, set_cookie, token_hash


def owner_identity(session, request, response):
    user = current_user(session, request)
    guest = guest_identity(request, response)
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))'), {'key': 'guest:' + guest})
        if user is None and session.scalar(select(GuestTransfer.id).where(GuestTransfer.guest_key == 'g:' + guest)):
            raise HTTPException(409, '체험 자료를 계정으로 옮겼어요. 새로고침해 주세요.')
    elif user is None and session.scalar(select(GuestTransfer.id).where(GuestTransfer.guest_key == 'g:' + guest)):
        token = secrets.token_urlsafe(32)
        set_cookie(response, GUEST_COOKIE, token, 30)
        guest = token_hash(token)
    return ('u:' + user.id if user else 'g:' + guest), user, guest


def settings_for(session, owner):
    row = session.get(PersonalSettings, owner)
    return SettingsRequest.model_validate(row.payload) if row else SettingsRequest()
