from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from threading import Lock
import time

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.record_models import AuthSession, User
from app.settings import get_settings

SESSION_COOKIE = 'oneul_portfolio_session'
GUEST_COOKIE = 'oneul_portfolio_guest'
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 17, 8, 1
HASH_LOCK = Lock()


def utcnow():
    return datetime.now(timezone.utc)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def cookie_token(value: str | None) -> str | None:
    return value if value and re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else None


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    with HASH_LOCK:
        result = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, maxmem=256 * 1024 * 1024, dklen=64)
    return f'scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt}${result.hex()}'


def password_matches(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt, digest = stored.split('$')
        if (algorithm, int(n), int(r), int(p)) != ('scrypt', SCRYPT_N, SCRYPT_R, SCRYPT_P):
            return False
        return hmac.compare_digest(password_hash(password, salt), stored)
    except (ValueError, TypeError):
        return False


def set_cookie(response: Response, name: str, value: str, days: int):
    response.set_cookie(name, value, max_age=days * 86400, httponly=True, secure=get_settings().cookie_secure, samesite='lax', path='/')


def guest_identity(request: Request, response: Response) -> str:
    token = cookie_token(request.cookies.get(GUEST_COOKIE))
    if token is None:
        token = secrets.token_urlsafe(32)
        set_cookie(response, GUEST_COOKIE, token, 30)
    return token_hash(token)


def current_user(session: Session, request: Request) -> User | None:
    token = cookie_token(request.cookies.get(SESSION_COOKIE))
    if token is None:
        return None
    auth_session = session.get(AuthSession, token_hash(token))
    if auth_session is None or auth_session.expires_at <= utcnow():
        return None
    return session.get(User, auth_session.user_id)


def require_user(session: Session, request: Request) -> User:
    user = current_user(session, request)
    if user is None:
        raise HTTPException(status_code=401, detail='로그인 후 이용해 주세요.')
    return user


def create_session(session: Session, response: Response, user: User):
    token = secrets.token_urlsafe(32)
    session.add(AuthSession(token_hash=token_hash(token), user_id=user.id, expires_at=utcnow() + timedelta(days=7)))
    set_cookie(response, SESSION_COOKIE, token, 7)


class LoginAttempts:
    def __init__(self):
        self.lock = Lock()
        self.attempts: dict[str, list[float]] = {}

    def check(self, key: str):
        with self.lock:
            cutoff = time.monotonic() - 60
            self.attempts = {k: [t for t in values if t >= cutoff] for k, values in self.attempts.items() if any(t >= cutoff for t in values)}
            if len(self.attempts.get(key, [])) >= 5:
                raise HTTPException(status_code=429, detail='잠시 후 다시 로그인해 주세요.', headers={'Retry-After': '60'})

    def fail(self, key: str):
        with self.lock:
            self.attempts.setdefault(key, []).append(time.monotonic())

    def clear(self, key: str):
        with self.lock:
            self.attempts.pop(key, None)


login_attempts = LoginAttempts()
