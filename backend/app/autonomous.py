"""Free scheduled read-only Google sync and private owner Telegram digests.

No SMTP, Google reply publication or automatic onboarding. GitHub Actions
schedule is best effort, not a continuously running worker.
"""
import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError

from .db import SessionLocal
from .models import (
    AutonomousRun, AutonomousSyncBlock, AutonomousDigest, AutonomousOrgRun,
    GoogleConnection, Location, Organization, Review, TelegramBinding,
    Membership, utcnow,
)
from .google_reviews import GoogleReviewAccessError, prepare_review_drafts
from .google_discovery import discover_accounts, discover_locations
from .google_routes import _access
from .telegram_bot import _api, _token

TRT = ZoneInfo("Europe/Istanbul")
LEASE = timedelta(minutes=12)


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def slot_key(kind, now):
    local = now.astimezone(TRT)
    slot = local.strftime("%Y%m%d%H") if kind == "sync" else local.strftime("%Y%m%d")
    return f"{kind}:{slot}"


def digest_business_day(now):
    """Gracefully handle a GitHub 23:59 TRT schedule delayed past midnight.

    Only 00:00–00:59 TRT is a bounded catch-up for the previous reporting day.
    The actual lease always uses the real execution time, not the backdated slot.
    """
    local = now.astimezone(TRT)
    if local.hour == 0:
        return (local - timedelta(days=1)).replace(
            hour=23, minute=59, second=0, microsecond=0).astimezone(timezone.utc)
    return now


def next_nominal(now):
    local = now.astimezone(TRT)
    hourly = local.replace(minute=17, second=0, microsecond=0)
    if hourly <= local:
        hourly += timedelta(hours=1)
    daily = local.replace(hour=23, minute=59, second=0, microsecond=0)
    if daily <= local:
        daily += timedelta(days=1)
    return {"sync": hourly.isoformat(), "digest": daily.isoformat()}


def claim(factory, kind, now, slot_time=None):
    key = slot_key(kind, slot_time or now)
    with factory() as db:
        if db.get(AutonomousRun, key) is None:
            db.add(AutonomousRun(key=key, kind=kind, status="ready"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
        item = db.execute(update(AutonomousRun).where(
            AutonomousRun.key == key,
            AutonomousRun.status.notin_(("success", "partial", "blocked")),
            AutonomousRun.attempts < 3,
            or_(AutonomousRun.status != "running",
                AutonomousRun.lease_until < now)
        ).values(status="running", attempts=AutonomousRun.attempts + 1,
                 started_at=now, lease_until=now + LEASE
        ).execution_options(synchronize_session=False).returning(
            AutonomousRun.key)).scalar_one_or_none()
        db.commit()
    return key if item else None


def finish(factory, key, status, counts=None, error_code=None):
    counts = counts or {}
    with factory() as db:
        row = db.get(AutonomousRun, key)
        row.status = status
        row.lease_until = None
        row.finished_at = utcnow()
        row.read_count = counts.get("read", 0)
        row.new_count = counts.get("new", 0)
        row.updated_count = counts.get("updated", 0)
        row.error_code = error_code
        db.commit()


def record_org(db, key, org_id, status, counts=None, error_code=None):
    """One row per authorized organization and slot; no cross-tenant data."""
    counts = counts or {}
    row_id = f"{key}:{org_id}"
    row = db.get(AutonomousOrgRun, row_id)
    if row is None:
        row = AutonomousOrgRun(id=row_id, organization_id=org_id, status=status)
        db.add(row)
    row.status = status
    row.read_count = counts.get("read", 0)
    row.new_count = counts.get("new", 0)
    row.updated_count = counts.get("updated", 0)
    row.error_code = error_code
    row.finished_at = utcnow()
    db.commit()


def google_sync(factory, key):
    totals = {"read": 0, "new": 0, "updated": 0}
    if os.getenv("GOOGLE_BUSINESS_API_APPROVED") != "true":
        return totals, "blocked", "GBP_API_APPROVAL_MISSING"
    with factory() as db:
        orgs = db.scalars(select(GoogleConnection.organization_id).where(
            GoogleConnection.revoked_at.is_(None)).limit(100)).all()
    if not orgs:
        return totals, "blocked", "OWNER_OAUTH_NOT_CONNECTED"
    failures = []
    for org_id in orgs:
        with factory() as db:
            conn = db.get(GoogleConnection, org_id)
            if conn is None or conn.revoked_at is not None:
                continue
            version = conn.updated_at.isoformat()
            block = db.get(AutonomousSyncBlock, org_id)
            if block and block.grant_version == version:
                failures.append(block.reason_code)
                record_org(db, key, org_id, "blocked", error_code=block.reason_code)
                continue
            locations = db.scalars(select(Location).where(
                Location.organization_id == org_id,
                Location.is_demo.is_(False),
                Location.google_resource_name.is_not(None)).limit(100)).all()
            if not locations:
                failures.append("OWNER_LOCATION_NOT_SELECTED")
                record_org(db, key, org_id, "blocked", error_code="OWNER_LOCATION_NOT_SELECTED")
                continue
            try:
                org_counts = {"read": 0, "new": 0, "updated": 0}
                token = _access(db, conn, org_id)
                accessible = {
                    l.review_parent
                    for account in discover_accounts(token)
                    for l in discover_locations(token, account.name)
                }
                if any(l.google_resource_name not in accessible for l in locations):
                    raise HTTPException(403, "Owner no longer has access")
                for loc in locations:
                    before = db.scalar(select(func.count(Review.id)).where(
                        Review.organization_id == org_id, Review.location_id == loc.id)) or 0
                    outcome = prepare_review_drafts(db, org_id, loc.id, token)
                    after = db.scalar(select(func.count(Review.id)).where(
                        Review.organization_id == org_id, Review.location_id == loc.id)) or 0
                    added = after - before
                    org_counts["read"] += outcome["read"]
                    org_counts["new"] += added
                    org_counts["updated"] += outcome["drafts_created_or_refreshed"] - added
                record_org(db, key, org_id, "success", counts=org_counts)
                for metric in totals:
                    totals[metric] += org_counts[metric]
                if block:
                    db.delete(block)
                    db.commit()
            except (HTTPException, GoogleReviewAccessError) as exc:
                http_status = exc.status_code if isinstance(exc, HTTPException) else None
                desc = str(exc) if http_status is None else ""
                db.rollback()
                denied = (http_status in (401, 403, 409) or
                          "HTTP 401" in desc or "HTTP 403" in desc)
                if denied:
                    code = "GOOGLE_PERMISSION_REVOKED"
                    if db.get(AutonomousSyncBlock, org_id) is None:
                        db.add(AutonomousSyncBlock(
                            organization_id=org_id, grant_version=version, reason_code=code))
                    else:
                        block = db.get(AutonomousSyncBlock, org_id)
                        block.grant_version = version
                        block.reason_code = code
                    db.commit()
                elif http_status == 429 or "HTTP 429" in desc:
                    code = "GOOGLE_QUOTA_LIMIT"
                else:
                    code = "GOOGLE_PROVIDER_UNAVAILABLE"
                record_org(db, key, org_id, "blocked", error_code=code)
                failures.append(code)
    if failures:
        return totals, ("partial" if totals["read"] else "blocked"), failures[0]
    return totals, "success", None


def daily_counts(db, now, org_id):
    """Only selected tenant's accepted Google syncs and sanitized errors."""
    local = now.astimezone(TRT)
    since = local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    rows = db.scalars(select(AutonomousOrgRun).where(
        AutonomousOrgRun.organization_id == org_id,
        AutonomousOrgRun.finished_at >= since,
        AutonomousOrgRun.finished_at <= now)).all()
    last = db.scalar(select(AutonomousOrgRun.finished_at).where(
        AutonomousOrgRun.organization_id == org_id,
        AutonomousOrgRun.status == "success"
    ).order_by(AutonomousOrgRun.finished_at.desc()).limit(1))
    error = db.scalar(select(AutonomousOrgRun.error_code).where(
        AutonomousOrgRun.organization_id == org_id,
        AutonomousOrgRun.error_code.is_not(None)
    ).order_by(AutonomousOrgRun.finished_at.desc()).limit(1))
    return {
        "ok": sum(r.status == "success" for r in rows),
        "failed": sum(r.status in ("failed", "partial", "blocked") for r in rows),
        "new": sum(r.new_count for r in rows),
        "updated": sum(r.updated_count for r in rows),
        "last_sync": _aware(last).astimezone(TRT).isoformat() if last else "henüz yok",
        "last_error": error or "yok",
    }

def report_message(org, metrics):
    return (
        f"📊 YorumPilot | {org.name[:64]}\n"
        f"Çalışan görev: {metrics['ok']}; başarısız/engelli: {metrics['failed']}\n"
        f"Yeni yorum: {metrics['new']}; güncellenen: {metrics['updated']}\n"
        f"Hazırlanan/yenilenen taslak: {metrics['new'] + metrics['updated']}\n"
        f"Son başarılı senkronizasyon: {metrics['last_sync']}\n"
        f"Son hata: {metrics['last_error']}\n"
        "SiteNöbet: bu raporda doğrulanmış site verisi bağlı değil.\n"
        "Google yanıtı ve e-posta gönderilmedi."
    )


async def daily_digest(factory, now, sender):
    with factory() as db:
        org_ids = db.scalars(select(TelegramBinding.organization_id).where(
            TelegramBinding.enabled.is_(True)).limit(100)).all()
    if not org_ids:
        return {}, "blocked", "TELEGRAM_OWNER_NOT_LINKED"
    if sender is _api and not _token():
        return {}, "blocked", "TELEGRAM_BOT_NOT_CONFIGURED"
    delivered, uncertain = 0, 0
    for org_id in org_ids:
        with factory() as db:
            bind = db.get(TelegramBinding, org_id)
            member = (db.scalar(select(Membership).where(
                Membership.organization_id == org_id,
                Membership.user_id == bind.user_id,
                Membership.role.in_(("owner", "admin")))) if bind else None)
            org = db.get(Organization, org_id)
            if not bind or not bind.enabled or bind.chat_id != bind.telegram_user_id or not member or not org:
                continue
            key = f"daily:{now.astimezone(TRT).strftime('%Y%m%d')}:{org_id}"
            if db.get(AutonomousDigest, key) is None:
                db.add(AutonomousDigest(event_key=key, organization_id=org_id, status="ready"))
                try:
                    db.commit()
                except IntegrityError:
                    db.rollback()
            claimed = db.execute(update(AutonomousDigest).where(
                AutonomousDigest.event_key == key, AutonomousDigest.status == "ready"
            ).values(status="sending", attempted_at=utcnow()
            ).execution_options(synchronize_session=False).returning(
                AutonomousDigest.event_key)).scalar_one_or_none()
            db.commit()
            if not claimed:
                continue
            text = report_message(org, daily_counts(db, now, org_id))
            chat_id = bind.chat_id
        try:
            response = await sender("sendMessage", {
                "chat_id": chat_id, "text": text, "disable_web_page_preview": True})
            message_id = response.get("message_id") if isinstance(response, dict) else None
            if type(message_id) is not int or message_id <= 0:
                raise ValueError("No confirmed Telegram message ID")
        except Exception:
            # Provider could have accepted before connection failed; never resend blindly.
            with factory() as db:
                item = db.get(AutonomousDigest, key)
                item.status = "unknown"
                db.commit()
            uncertain += 1
        else:
            with factory() as db:
                item = db.get(AutonomousDigest, key)
                item.status = "sent"
                item.receipt_id = message_id
                item.sent_at = utcnow()
                db.commit()
            delivered += 1
    return {"read": delivered, "new": 0, "updated": 0}, (
        "partial" if uncertain else "success" if delivered else "blocked"
    ), ("TELEGRAM_DELIVERY_UNCERTAIN" if uncertain else
        None if delivered else "NO_AUTHORIZED_PRIVATE_CHAT")


def run_once(kind, *, factory=SessionLocal, now=None, syncer=None, sender=_api):
    if kind not in ("sync", "digest"):
        raise ValueError("Unsupported automation job")
    now = now or utcnow()
    reporting_time = digest_business_day(now) if kind == "digest" else now
    key = claim(factory, kind, now, slot_time=reporting_time)
    if key is None:
        return {"status": "already_claimed", "next_nominal_trt": next_nominal(now)}
    counts = {}
    try:
        if kind == "sync":
            counts, status, code = (syncer(factory) if syncer else google_sync(factory, key))
        else:
            counts, status, code = asyncio.run(daily_digest(factory, reporting_time, sender))
        finish(factory, key, status, counts, code)
        return {"status": status, "error_code": code,
                "counts": counts, "next_nominal_trt": next_nominal(now)}
    except Exception:
        finish(factory, key, "failed", counts, "UNEXPECTED_AUTOMATION_ERROR")
        return {"status": "failed", "error_code": "UNEXPECTED_AUTOMATION_ERROR",
                "next_nominal_trt": next_nominal(now)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", choices=("sync", "digest"), required=True)
    args = parser.parse_args()
    result = run_once(args.job)
    print(json.dumps(result, ensure_ascii=False))
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
