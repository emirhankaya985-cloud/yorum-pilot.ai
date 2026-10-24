"""OAuth building blocks only; live callbacks and tokens deliberately not enabled."""
import base64
import hashlib
import secrets
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .config import get_settings


class OAuthStateError(Exception):
    pass


def new_pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).decode('ascii').rstrip('=')
    return verifier, challenge


def _signer():
    return URLSafeTimedSerializer(get_settings().secret_key, salt='yorumpilot-google-oauth-state-v1')


def sign_state(user_id: str, organization_id: str, nonce: str):
    return _signer().dumps({'uid':user_id,'org':organization_id,'nonce':nonce})


def verify_state(value: str, user_id: str, organization_id: str, *, max_age: int = 600):
    try:
        payload = _signer().loads(value, max_age=max_age)
    except (BadSignature, SignatureExpired):
        raise OAuthStateError('OAuth state invalid or expired') from None
    if payload.get('uid')!=user_id or payload.get('org')!=organization_id:
        raise OAuthStateError('OAuth state account mismatch')
    return payload['nonce']
