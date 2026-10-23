from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.account_contracts import Credentials, Identity, PublicUser
from app.record_models import AuthSession, User
from app.security import SESSION_COOKIE, cookie_token, create_session, current_user, guest_identity, login_attempts, password_hash, password_matches, token_hash, utcnow
from app.session_dependency import get_session

router = APIRouter(prefix='/api/auth')


@router.get('/me', response_model=Identity)
def me(request: Request, response: Response, session=Depends(get_session)):
    guest_identity(request, response)
    user = current_user(session, request)
    return Identity(user=PublicUser(id=user.id, username=user.username) if user else None)


@router.post('/register', response_model=Identity, status_code=201)
def register(data: Credentials, request: Request, response: Response, session=Depends(get_session)):
    if session.scalar(select(User.id).where(User.username == data.username)):
        raise HTTPException(status_code=409, detail='이미 사용 중인 아이디예요.')
    user = User(id=str(uuid4()), username=data.username, password_hash=password_hash(data.password.get_secret_value()), created_at=utcnow())
    try:
        session.add(user)
        session.flush()
        create_session(session, response, user)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail='이미 사용 중인 아이디예요.') from None
    return Identity(user=PublicUser(id=user.id, username=user.username))


@router.post('/login', response_model=Identity)
def login(data: Credentials, request: Request, response: Response, session=Depends(get_session)):
    key = token_hash((request.client.host if request.client else '') + ':' + data.username)
    login_attempts.check(key)
    user = session.scalar(select(User).where(User.username == data.username))
    matched = password_matches(data.password.get_secret_value(), user.password_hash) if user else bool(password_hash(data.password.get_secret_value()) and False)
    if not matched:
        login_attempts.fail(key)
        raise HTTPException(status_code=401, detail='아이디와 비밀번호를 확인해 주세요.')
    login_attempts.clear(key)
    old_token = cookie_token(request.cookies.get(SESSION_COOKIE))
    if old_token:
        old = session.get(AuthSession, token_hash(old_token))
        if old is not None:
            session.delete(old)
    create_session(session, response, user)
    session.commit()
    return Identity(user=PublicUser(id=user.id, username=user.username))


@router.post('/logout', status_code=204)
def logout(request: Request, response: Response, session=Depends(get_session)):
    token = cookie_token(request.cookies.get(SESSION_COOKIE))
    if token:
        entry = session.get(AuthSession, token_hash(token))
        if entry is not None:
            session.delete(entry)
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path='/')
