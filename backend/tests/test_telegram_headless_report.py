"""Headless Telegram report: owner-only, private-only, no Google publish or demo data."""
from sqlalchemy import select

from app.ingestion import ingest
from app.models import Location, Membership
from .conftest import signup
from .test_telegram_bot import activate, link, signed_headers


def _say(client, update_id, user_id, command):
    return client.post('/api/telegram/webhook',
                       headers=signed_headers(),
                       json={'update_id': update_id, 'message': {
                           'chat': {'id': user_id, 'type': 'private'},
                           'from': {'id': user_id}, 'text': command}})


def test_unpaired_telegram_must_not_show_org_report(client, monkeypatch):
    sent = activate(monkeypatch)
    org = signup(client)
    assert _say(client, 60001, 1234567, '/rapor').status_code == 200
    assert 'yetkili bir işletme bulunmuyor' in sent[-1][1]['text']
    assert org not in sent[-1][1]['text']


def test_paired_owner_receives_real_only_counts_without_browser(client, monkeypatch):
    sent = activate(monkeypatch)
    org = signup(client)
    link(client, org, sent, update_id=60002)
    with client.db_factory() as db:
        loc = Location(organization_id=org, name='Synthetic authorized location',
                       is_demo=False, google_resource_name='accounts/100/locations/200')
        db.add(loc)
        db.flush()
        ingest(db, org, loc.id, 'synthetic-review', 'v1',
               'Synthetic customer private review text', 3)
        db.commit()
    previous = len(sent)
    assert _say(client, 60003, 1234567, '/rapor').status_code == 200
    assert len(sent) == previous + 1
    report = sent[-1][1]['text']
    assert 'gerçek yorum=1' in report
    assert 'onay bekleyen=1' in report
    assert 'Demo kayıtları hariçtir' in report
    assert 'Synthetic customer private review text' not in report
    assert 'Google yanıtı yayımlamaz' in report
    assert _say(client, 60004, 9876543, '/rapor').status_code == 200
    assert 'gerçek yorum=1' not in sent[-1][1]['text']
    old = len(sent)
    assert _say(client, 60003, 1234567, '/rapor').json()['duplicate']
    assert len(sent) == old


def test_revoked_membership_removes_report_access(client, monkeypatch):
    sent = activate(monkeypatch)
    org = signup(client)
    link(client, org, sent, update_id=60005)
    with client.db_factory() as db:
        member = db.scalar(select(Membership).where(Membership.organization_id == org))
        member.role = 'viewer'
        db.commit()
    assert _say(client, 60006, 1234567, '/rapor').status_code == 200
    assert 'yetkili bir işletme bulunmuyor' in sent[-1][1]['text']
