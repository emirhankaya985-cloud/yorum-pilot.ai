"""Owner-only Google Business Profile OAuth, secret vault, and read-only sync.

Production disabled until explicitly approved GBP credentials/permissions exist.
Never return OAuth tokens or sensitive Google responses to clients/logs.
"""
import hashlib
import os
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import identity, membership
from .config import get_settings
from .db import get_db
from .google_oauth import new_pkce, sign_state, verify_state, OAuthStateError
from .google_discovery import discover_accounts, discover_locations
from .google_reviews import REVIEW_SCOPE, GoogleReviewAccessError, prepare_review_drafts
from .models import GoogleOAuthAttempt, GoogleConnection, Location, utcnow

router = APIRouter(prefix="/api/organizations/{org_id}/google", tags=["Google Business Profile"])
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def _configuration(org_id):
    if os.getenv("GOOGLE_BUSINESS_API_APPROVED") != "true":
        raise HTTPException(503, "Google Business Profile API approval is required")
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    expected = get_settings().frontend_url + f"/api/organizations/{org_id}/google/callback"
    if (not client_id.endswith(".apps.googleusercontent.com") or
        not secret or not redirect.startswith("https://") or redirect != expected):
        raise HTTPException(503, "Google OAuth credentials or exact redirect URI are not configured")
    _vault()
    return client_id, secret, redirect


def _vault():
    value = os.getenv("GOOGLE_TOKEN_ENCRYPTION_KEY", "")
    try:
        return Fernet(value.encode("ascii"))
    except (ValueError, TypeError):
        raise HTTPException(503, "Google server token encryption is not configured") from None


def _owner(org_id, request, db, *, write=False):
    user = identity(request, db, write=write)
    membership(db, user, org_id, ("owner",))
    return user


def _http():
    return httpx.Client(follow_redirects=False, timeout=15)


def _token_call(payload):
    with _http() as client:
        try:
            response = client.post(TOKEN_URL, data=payload)
        except httpx.HTTPError:
            raise HTTPException(502, "Google token service unavailable") from None
    if response.status_code != 200:
        if response.status_code in (400, 401):
            raise HTTPException(401, "Google authorization expired or revoked")
        raise HTTPException(502, f"Google token exchange failed (HTTP {response.status_code})")
    try:
        data = response.json()
    except ValueError:
        raise HTTPException(502, "Invalid Google token response") from None
    if not isinstance(data, dict) or not isinstance(data.get("access_token"), str):
        raise HTTPException(502, "Invalid Google token response")
    granted_scopes = data.get("scope", "")
    if not isinstance(granted_scopes, str) or REVIEW_SCOPE not in granted_scopes.split():
        raise HTTPException(403, "Required Google Business Profile scope was not granted")
    return data


def _access(conn, org_id):
    _configuration(org_id)
    if conn is None or conn.revoked_at is not None:
        raise HTTPException(409, "Google Business Profile owner connection is not active")
    try:
        refresh = _vault().decrypt(conn.refresh_ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, "Encrypted Google grant is not readable") from None
    client_id, secret, _ = _configuration(org_id)
    try:
        data = _token_call({"client_id": client_id, "client_secret": secret,
                            "refresh_token": refresh, "grant_type": "refresh_token"})
    except HTTPException as exc:
        if exc.status_code == 401:
            conn.revoked_at = utcnow()
            conn.refresh_ciphertext = ""  # revoke locally, do not leave usable credentials
        raise
    return data["access_token"]


def _connected(db, org_id):
    return db.get(GoogleConnection, org_id)


@router.get("/status")
def google_status(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(org_id, request, db)
    conn = _connected(db, org_id)
    return {"connected": bool(conn and not conn.revoked_at),
            "approval_gate": os.getenv("GOOGLE_BUSINESS_API_APPROVED") == "true",
            "live_google_publish_enabled": False}


@router.post("/start")
def google_start(org_id: str, request: Request, db: Session = Depends(get_db)):
    user = _owner(org_id, request, db, write=True)
    client_id, _, redirect = _configuration(org_id)
    verifier, challenge = new_pkce()
    nonce = secrets.token_urlsafe(32)
    digest = hashlib.sha256(nonce.encode("ascii")).hexdigest()
    db.add(GoogleOAuthAttempt(
        nonce_hash=digest, organization_id=org_id, user_id=user.id,
        verifier_ciphertext=_vault().encrypt(verifier.encode("ascii")).decode("ascii"),
        expires_at=utcnow() + timedelta(minutes=10)))
    db.commit()
    state = sign_state(user.id, org_id, nonce)
    url = AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect,
        "response_type": "code", "scope": REVIEW_SCOPE,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent"})
    return {"authorization_url": url, "expires_minutes": 10}


@router.get("/callback")
def google_callback(org_id: str, request: Request, state: str = "",
                    code: str = "", error: str = "", db: Session = Depends(get_db)):
    user = _owner(org_id, request, db)
    client_id, client_secret, redirect = _configuration(org_id)
    try:
        nonce = verify_state(state, user.id, org_id)
    except OAuthStateError:
        raise HTTPException(400, "Invalid or expired Google OAuth state") from None
    digest = hashlib.sha256(nonce.encode("ascii")).hexdigest()
    # One-use atomic row claim across workers, before any provider exchange.
    row = db.scalar(select(GoogleOAuthAttempt).where(
        GoogleOAuthAttempt.nonce_hash == digest,
        GoogleOAuthAttempt.organization_id == org_id,
        GoogleOAuthAttempt.user_id == user.id))
    if row is None:
        raise HTTPException(400, "Unknown Google OAuth state")
    claim = db.execute(update(GoogleOAuthAttempt).where(
        GoogleOAuthAttempt.nonce_hash == digest,
        GoogleOAuthAttempt.used_at.is_(None),
        GoogleOAuthAttempt.expires_at > utcnow()).values(
            used_at=utcnow()).returning(GoogleOAuthAttempt.nonce_hash)).scalar_one_or_none()
    db.commit()
    if claim is None:
        raise HTTPException(409, "Google OAuth state already used or expired")
    if error or not code or len(code) > 2048:
        raise HTTPException(400, "Google owner authorization not completed")
    try:
        verifier = _vault().decrypt(row.verifier_ciphertext.encode("ascii")).decode("ascii")
    except (InvalidToken, UnicodeError):
        raise HTTPException(503, "Google OAuth challenge cannot be decrypted") from None
    data = _token_call({"code": code, "client_id": client_id,
                        "client_secret": client_secret, "redirect_uri": redirect,
                        "grant_type": "authorization_code", "code_verifier": verifier})
    refresh = data.get("refresh_token")
    if not isinstance(refresh, str) or len(refresh) < 8:
        raise HTTPException(409, "Google did not grant offline access; reconnect with consent")
    conn = _connected(db, org_id)
    if conn is None:
        conn = GoogleConnection(organization_id=org_id, user_id=user.id,
                                refresh_ciphertext="")
        db.add(conn)
    conn.user_id = user.id
    conn.refresh_ciphertext = _vault().encrypt(refresh.encode("utf-8")).decode("ascii")
    conn.updated_at = utcnow()
    conn.revoked_at = None
    db.commit()
    # Authorization code and tokens never appear in redirected URL.
    return RedirectResponse(get_settings().frontend_url + "/panel/ayarlar?google=connected",
                            status_code=303)


@router.get("/accounts")
def google_accounts(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(org_id, request, db)
    conn = _connected(db, org_id)
    token = _access(conn, org_id)
    try:
        accounts = discover_accounts(token)
    except GoogleReviewAccessError:
        raise HTTPException(424, "Google account discovery unavailable or unauthorized") from None
    return {"accounts": [{"name": a.name} for a in accounts]}


@router.get("/accounts/{account_id}/locations")
def google_locations(org_id: str, account_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(org_id, request, db)
    token = _access(_connected(db, org_id), org_id)
    try:
        names = {a.name for a in discover_accounts(token)}
        acct = "accounts/" + account_id
        if acct not in names:
            raise HTTPException(403, "Google account not granted to this owner")
        locations = discover_locations(token, acct)
    except GoogleReviewAccessError:
        raise HTTPException(424, "Google locations unavailable or unauthorized") from None
    return {"locations": [{"name": x.name, "title": x.title} for x in locations]}


from pydantic import BaseModel


class GoogleLocationSelection(BaseModel):
    account_name: str
    location_name: str


@router.post("/select-location")
def google_select_location(org_id: str, data: GoogleLocationSelection, request: Request,
                           db: Session = Depends(get_db)):
    _owner(org_id, request, db, write=True)
    token = _access(_connected(db, org_id), org_id)
    try:
        accounts = {a.name for a in discover_accounts(token)}
        if data.account_name not in accounts:
            raise HTTPException(403, "Google account not authorized")
        matches = {loc.name: loc for loc in discover_locations(token, data.account_name)}
    except GoogleReviewAccessError:
        raise HTTPException(424, "Google location verification failed") from None
    loc = matches.get(data.location_name)
    if loc is None:
        raise HTTPException(403, "Location not authorized to this owner")
    existing = db.scalar(select(Location).where(
        Location.google_resource_name == loc.review_parent))
    if existing and existing.organization_id != org_id:
        raise HTTPException(409, "Google location already bound to another organization")
    if existing is None:
        existing = Location(organization_id=org_id, name=loc.title,
                            google_resource_name=loc.review_parent, is_demo=False)
        db.add(existing)
    elif existing.is_demo:
        raise HTTPException(409, "Demo locations may never be converted into real locations")
    db.commit()
    return {"location_id": existing.id, "title": loc.title, "real_google_location": True}


@router.post("/sync/{location_id}")
def google_sync(org_id: str, location_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(org_id, request, db, write=True)
    location = db.scalar(select(Location).where(
        Location.id == location_id, Location.organization_id == org_id,
        Location.is_demo.is_(False)))
    if location is None:
        raise HTTPException(404, "Authorized real Google location not found")
    token = _access(_connected(db, org_id), org_id)
    # Recheck Google owner access on *every* import, never trust stored mapping alone.
    try:
        accounts = discover_accounts(token)
        authorized = any(location.google_resource_name in
                         {x.review_parent for x in discover_locations(token, a.name)}
                         for a in accounts)
        if not authorized:
            raise HTTPException(403, "Owner no longer has access to this Google location")
        result = prepare_review_drafts(db, org_id, location_id, token)
        db.commit()
    except GoogleReviewAccessError:
        db.rollback()
        raise HTTPException(424, "Google review read failed; no partial sync committed") from None
    return result


@router.post("/disconnect")
def google_disconnect(org_id: str, request: Request, db: Session = Depends(get_db)):
    _owner(org_id, request, db, write=True)
    conn = _connected(db, org_id)
    if conn is not None:
        # Local revocation is committed first; Google remote revocation is best-effort
        # and failures may require owner to revoke the app in Google Account settings.
        ciphertext = conn.refresh_ciphertext
        conn.refresh_ciphertext = ""
        conn.revoked_at = utcnow()
        db.commit()
        try:
            refresh = _vault().decrypt(ciphertext.encode("ascii")).decode("utf-8")
            with _http() as client:
                client.post(REVOKE_URL, data={"token": refresh}, timeout=8)
        except (InvalidToken, UnicodeError, httpx.HTTPError):
            pass
    return {"connected": False, "manual_google_revoke_may_be_required": True,
            "live_google_publish_enabled": False}
