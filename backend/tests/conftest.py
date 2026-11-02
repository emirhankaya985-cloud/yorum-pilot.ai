import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.rate_limit import _history as _rate_history, _lock as _rate_lock


@pytest.fixture
def client():
    # Test cases share an in-process module; isolate abuse counters between
    # independent synthetic accounts without changing production rate limits.
    with _rate_lock:
        _rate_history.clear()
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        c.db_factory = factory
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def signup(c, email='admin@example.com', org='Deneme işletmesi'):
    r=c.post('/api/auth/register',json={'email':email,'password':'my-secure-test-password-123', 'organization_name':org})
    assert r.status_code==201,r.text
    return r.json()['organization_id']


def csrf(c):
    return {'x-csrf-token':c.cookies.get('yp_csrf')}
