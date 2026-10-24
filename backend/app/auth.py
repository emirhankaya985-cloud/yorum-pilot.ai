"""Authenticated cookie + double-submit CSRF; no email or password in session."""
import hmac
import secrets
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import HTTPException, Request, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .models import User, Membership

ph = PasswordHasher()


def hash_password(plain: str):
    return ph.hash(plain)


def verify_password(stored: str, plain: str):
    try:
        return ph.verify(stored, plain)
    except (VerifyMismatchError, VerificationError):
        return False


def serializer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt='yorum-pilot-session-v1')


def set_session(response: Response, user_id: str):
    settings = get_settings()
    csrf = secrets.token_urlsafe(32)
    response.set_cookie('yp_session', serializer().dumps({'sub': user_id, 'csrf': csrf}), httponly=True,
                        secure=settings.cookie_secure, samesite='lax', max_age=604800, path='/')
    response.set_cookie('yp_csrf', csrf, httponly=False, secure=settings.cookie_secure,
                        samesite='lax', max_age=604800, path='/')


def clear_session(response: Response):
    response.delete_cookie('yp_session', path='/')
    response.delete_cookie('yp_csrf', path='/')


def identity(request: Request, db: Session, *, write: bool = False):
    cookie = request.cookies.get('yp_session', '')
    try:
        data = serializer().loads(cookie, max_age=604800)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, 'Oturum açmanız gerekiyor') from None
    if write:
        expected = data.get('csrf', '')
        supplied = request.headers.get('x-csrf-token', '')
        cookie_csrf = request.cookies.get('yp_csrf', '')
        if not (expected and supplied and cookie_csrf and
                hmac.compare_digest(expected, supplied) and hmac.compare_digest(expected, cookie_csrf)):
            raise HTTPException(403, 'CSRF doğrulaması başarısız')
    user = db.get(User, data.get('sub', ''))
    if not user:
        raise HTTPException(401, 'Kullanıcı bulunamadı')
    return user


def membership(db: Session, user: User, org_id: str, roles: tuple[str,...] = ('owner','admin','editor','viewer')):
    m = db.scalar(select(Membership).where(Membership.user_id==user.id, Membership.organization_id==org_id))
    if not m or m.role not in roles:
        # Hide whether a foreign resource exists.
        raise HTTPException(404, 'Kaynak bulunamadı')
    return m
