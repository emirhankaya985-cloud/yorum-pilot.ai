"""Owner-only GBP OAuth flow: one-use state, encrypted grants, scope, tenant protection."""
from urllib.parse import urlparse, parse_qs

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select

from app.models import GoogleConnection, GoogleOAuthAttempt, Location
from .conftest import signup, csrf


@pytest.fixture
def approved(monkeypatch, client):
    import app.google_routes as routes
    org = signup(client)
    origin = "https://yorumpilot-web.onrender.com"
    callback = origin + f"/api/organizations/{org}/google/callback"
    monkeypatch.setenv("FRONTEND_URL", origin)
    monkeypatch.setenv("GOOGLE_BUSINESS_API_APPROVED", "true")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "synthetic.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-only-not-real")
    monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URI", callback)
    monkeypatch.setenv("GOOGLE_TOKEN_ENCRYPTION_KEY", Fernet.generate_key().decode())
    return org, routes


def _start(client, org):
    response = client.post(f"/api/organizations/{org}/google/start",
                           headers=csrf(client))
    assert response.status_code == 200, response.text
    params = parse_qs(urlparse(response.json()["authorization_url"]).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["https://www.googleapis.com/auth/business.manage"]
    assert params["access_type"] == ["offline"]
    assert params["redirect_uri"] == [
        f"https://yorumpilot-web.onrender.com/api/organizations/{org}/google/callback"]
    assert "client_secret" not in params
    return params["state"][0]


def test_google_oauth_not_enabled_without_external_approval(client):
    org = signup(client)
    response = client.post(f"/api/organizations/{org}/google/start",
                           headers=csrf(client))
    assert response.status_code == 503
    assert not response.text.find("token=") >= 0


def test_one_time_oauth_encrypted_refresh_and_safe_redirect(approved, client, monkeypatch):
    org, routes = approved
    assert client.post(f"/api/organizations/{org}/google/start").status_code == 403
    state = _start(client, org)
    called = []
    def exchange(data):
        called.append(data)
        return {"access_token": "access-secret",
                "refresh_token": "refresh-secret-not-real",
                "scope": "https://www.googleapis.com/auth/business.manage"}
    monkeypatch.setattr(routes, "_token_call", exchange)
    url = f"/api/organizations/{org}/google/callback"
    done = client.get(url, params={"state":state,"code":"test-auth-code"}, follow_redirects=False)
    assert done.status_code == 303
    assert "code=" not in done.headers["location"]
    assert "access-secret" not in done.text
    assert called[0]["grant_type"] == "authorization_code"
    assert len(called[0]["code_verifier"]) >= 43
    with client.db_factory() as db:
        grant = db.get(GoogleConnection, org)
        assert grant is not None
        assert "refresh-secret" not in grant.refresh_ciphertext
        assert grant.revoked_at is None
        assert db.scalar(select(GoogleOAuthAttempt)).used_at is not None
    again = client.get(url, params={"state":state,"code":"test-auth-code"})
    assert again.status_code == 409
    assert len(called) == 1


def test_denied_oauth_consumes_state_and_scope_is_required(approved, client, monkeypatch):
    org, routes = approved
    state = _start(client, org)
    url = f"/api/organizations/{org}/google/callback"
    assert client.get(url, params={"state":state,"error":"access_denied"}).status_code == 400
    assert client.get(url, params={"state":state,"code":"abc"}).status_code == 409
    other = _start(client, org)
    monkeypatch.setattr(routes, "_token_call",
                        lambda _: (_ for _ in ()).throw(__import__("fastapi").HTTPException(
                            403, "Required Google Business Profile scope was not granted")))
    assert client.get(url, params={"state":other,"code":"abc"}).status_code == 403
    with client.db_factory() as db:
        assert db.get(GoogleConnection, org) is None


def test_owner_scope_disconnect_and_tenant_isolation(approved, client, monkeypatch):
    org, routes = approved
    state = _start(client, org)
    monkeypatch.setattr(routes, "_token_call", lambda _: {
        "access_token": "access-token", "refresh_token": "refresh-token",
        "scope": "https://www.googleapis.com/auth/business.manage"})
    client.get(f"/api/organizations/{org}/google/callback",
               params={"state":state,"code":"code"},follow_redirects=False)
    class DummyClient:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def post(self, *args, **kwargs):
            class Reply:
                status_code = 200
            return Reply()
    monkeypatch.setattr(routes, "_http", lambda: DummyClient())
    assert client.get(f"/api/organizations/{org}/google/status").json()["connected"]
    status = client.post(f"/api/organizations/{org}/google/disconnect",
                         headers=csrf(client))
    assert status.status_code == 200
    assert not status.json()["connected"]
    with client.db_factory() as db:
        grant = db.get(GoogleConnection, org)
        assert grant.refresh_ciphertext == ""
        assert grant.revoked_at is not None


def test_demo_not_touched_and_no_unverified_location_mapping(approved, client, monkeypatch):
    org, routes = approved
    state = _start(client, org)
    monkeypatch.setattr(routes, "_token_call", lambda _: {
        "access_token": "access-token", "refresh_token": "refresh-token",
        "scope": "https://www.googleapis.com/auth/business.manage"})
    client.get(f"/api/organizations/{org}/google/callback",
               params={"state":state,"code":"test-code"},follow_redirects=False)
    monkeypatch.setattr(routes, "discover_accounts",
                        lambda token: [type("A", (), {"name":"accounts/1"})()])
    monkeypatch.setattr(routes, "discover_locations",
                        lambda token, account: [type("L", (), {
                            "name":"locations/2", "title":"Verified owner location",
                            "review_parent":"accounts/1/locations/2"})()])
    forbidden = client.post(f"/api/organizations/{org}/google/select-location",
                            json={"account_name":"accounts/1","location_name":"locations/999"},
                            headers=csrf(client))
    assert forbidden.status_code == 403
    ok = client.post(f"/api/organizations/{org}/google/select-location",
                     json={"account_name":"accounts/1","location_name":"locations/2"},
                     headers=csrf(client))
    assert ok.status_code == 200, ok.text
    location_id = ok.json()["location_id"]
    dup = client.post(f"/api/organizations/{org}/google/select-location",
                      json={"account_name":"accounts/1","location_name":"locations/2"},
                      headers=csrf(client))
    assert dup.status_code == 200 and dup.json()["location_id"] == location_id
    with client.db_factory() as db:
        entries = db.scalars(select(Location).where(Location.organization_id==org)).all()
        assert sum(l.is_demo for l in entries) == 1
        assert sum(not l.is_demo for l in entries) == 1
