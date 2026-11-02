"""Headless cron logic: DB-backed locks, owner-only reports and no blind resend."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.autonomous import run_once, slot_key, next_nominal, daily_counts, record_org
from app.models import AutonomousRun, AutonomousDigest, AutonomousOrgRun, Location, Membership
from .conftest import signup
from .test_telegram_bot import activate, link


TIME = datetime(2026, 11, 2, 20, 59, tzinfo=timezone.utc)


def test_hourly_sync_ledger_survives_new_sessions_and_deduplicates(client):
    calls = []
    def sync(_):
        calls.append(1)
        return {"read": 4, "new": 2, "updated": 1}, "success", None
    first = run_once("sync", now=TIME, factory=client.db_factory, syncer=sync)
    second = run_once("sync", now=TIME, factory=client.db_factory, syncer=sync)
    assert first["status"] == "success"
    assert second["status"] == "already_claimed"
    assert len(calls) == 1
    with client.db_factory() as db:
        run = db.get(AutonomousRun, slot_key("sync", TIME))
        assert run.status == "success" and run.new_count == 2
    tomorrow = run_once("sync", now=TIME + timedelta(hours=1),
                        factory=client.db_factory, syncer=sync)
    assert tomorrow["status"] == "success" and len(calls) == 2


def test_disabled_google_api_has_persistent_sanitized_block(client, monkeypatch):
    monkeypatch.delenv("GOOGLE_BUSINESS_API_APPROVED", raising=False)
    result = run_once("sync", now=TIME, factory=client.db_factory)
    assert result["status"] == "blocked"
    assert result["error_code"] == "GBP_API_APPROVAL_MISSING"
    assert run_once("sync", now=TIME, factory=client.db_factory)["status"] == "already_claimed"


def test_transient_failure_is_limited_and_no_raw_exception_in_status(client):
    def explode(_):
        raise RuntimeError("sensitive provider details must not reach output")
    for _ in range(3):
        answer = run_once("sync", now=TIME, factory=client.db_factory, syncer=explode)
        assert answer.get("error_code") == "UNEXPECTED_AUTOMATION_ERROR"
        assert "sensitive" not in str(answer)
    assert run_once("sync", now=TIME, factory=client.db_factory,
                    syncer=explode)["status"] == "already_claimed"


def test_nominal_turkey_times_dont_claim_exact_dispatch(client):
    values = next_nominal(datetime(2026, 11, 2, 19, 20, tzinfo=timezone.utc))
    assert values["digest"].startswith("2026-11-02T23:59")
    assert "+03:00" in values["digest"]
    assert values["sync"].startswith("2026-11-02T23:17")


def test_daily_digest_uses_private_confirmed_chat_and_one_receipt(client, monkeypatch):
    sent = activate(monkeypatch)
    org = signup(client)
    link(client, org, sent, update_id=81001)
    delivered = []
    async def send(method, payload):
        delivered.append((method, payload))
        return {"message_id": 321}
    first = run_once("digest", now=TIME, factory=client.db_factory, sender=send)
    second = run_once("digest", now=TIME, factory=client.db_factory, sender=send)
    assert first["status"] == "success"
    assert second["status"] == "already_claimed"
    assert len(delivered) == 1 and delivered[0][0] == "sendMessage"
    message = delivered[0][1]["text"]
    assert "Yeni yorum: 0" in message and "Son başarılı senkronizasyon" in message
    assert "DEMO" not in message
    assert "SiteNöbet:" in message and "doğrulanmış site verisi bağlı değil" in message
    with client.db_factory() as db:
        rows = db.scalars(select(AutonomousDigest)).all()
        assert len(rows) == 1 and rows[0].receipt_id == 321 and rows[0].status == "sent"


def test_ambiguous_telegram_send_never_replays(client, monkeypatch):
    sent = activate(monkeypatch)
    org = signup(client)
    link(client, org, sent, update_id=81002)
    calls = []
    async def flaky(method, payload):
        calls.append(1)
        raise RuntimeError("provider may have accepted")
    result = run_once("digest", now=TIME, factory=client.db_factory, sender=flaky)
    assert result["status"] == "partial"
    assert result["error_code"] == "TELEGRAM_DELIVERY_UNCERTAIN"
    assert run_once("digest", now=TIME, factory=client.db_factory, sender=flaky)["status"] == "already_claimed"
    assert len(calls) == 1
    with client.db_factory() as db:
        row = db.scalar(select(AutonomousDigest))
        assert row.status == "unknown" and row.receipt_id is None


def test_unlinked_or_demoted_owner_receives_no_report(client, monkeypatch):
    org = signup(client)
    delivery = []
    async def mock_sender(*_):
        delivery.append(1)
        return {"message_id": 99}
    result = run_once("digest", now=TIME, factory=client.db_factory, sender=mock_sender)
    assert result["error_code"] == "TELEGRAM_OWNER_NOT_LINKED"
    sent = activate(monkeypatch)
    link(client, org, sent, update_id=81003)
    with client.db_factory() as db:
        member = db.scalar(select(Membership).where(Membership.organization_id == org))
        member.role = "viewer"
        db.commit()
    future = run_once("digest", now=TIME + timedelta(days=1),
                      factory=client.db_factory, sender=mock_sender)
    assert future["status"] == "blocked"
    assert not delivery


def test_daily_metrics_are_strictly_org_scoped(client):
    first = signup(client)
    client.cookies.clear()
    second = signup(client, "other-autonomy@example.com", "Other org")
    with client.db_factory() as db:
        record_org(db, "sync:2026110220", first, "success",
                   {"read": 3, "new": 2, "updated": 1})
        record_org(db, "sync:2026110220", second, "success",
                   {"read": 10, "new": 9, "updated": 1})
    with client.db_factory() as db:
        for row in db.scalars(select(AutonomousOrgRun)).all():
            row.finished_at = TIME - timedelta(minutes=1)
        db.commit()
    with client.db_factory() as db:
        one = daily_counts(db, TIME, first)
        two = daily_counts(db, TIME, second)
    assert one["new"] == 2 and one["updated"] == 1
    assert two["new"] == 9 and two["updated"] == 1
    assert one["new"] != two["new"]
