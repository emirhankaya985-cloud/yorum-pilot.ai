"""Stored Google content expires; operational audit contains no review text."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, ForeignKey, DateTime, Text, UniqueConstraint, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def uid():
    return uuid4().hex


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Membership(Base):
    __tablename__ = 'organization_members'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    role: Mapped[str] = mapped_column(String(12), default='owner')
    __table_args__ = (UniqueConstraint('organization_id', 'user_id'),)


class Location(Base):
    __tablename__ = 'business_locations'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    google_resource_name: Mapped[str | None] = mapped_column(String(220), nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class Review(Base):
    __tablename__ = 'reviews_cache'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    location_id: Mapped[str] = mapped_column(ForeignKey('business_locations.id'), index=True)
    external_id: Mapped[str] = mapped_column(String(200))
    revision: Mapped[str] = mapped_column(String(80))
    stars: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str] = mapped_column(String(24))
    priority: Mapped[str] = mapped_column(String(24))
    category: Mapped[str] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(12), default='tr')
    status: Mapped[str] = mapped_column(String(28), default='awaiting_approval')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    draft: Mapped['Draft | None'] = relationship(back_populates='review', cascade='all, delete-orphan', uselist=False)
    __table_args__ = (UniqueConstraint('organization_id', 'location_id', 'external_id'),)


class Draft(Base):
    __tablename__ = 'ai_drafts'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    review_id: Mapped[str] = mapped_column(ForeignKey('reviews_cache.id', ondelete='CASCADE'), unique=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_revision: Mapped[str] = mapped_column(String(80))
    review: Mapped[Review] = relationship(back_populates='draft')


class Publication(Base):
    __tablename__ = 'reply_publications'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    review_id: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(28))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('organization_id','idempotency_key'),)


class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(48))
    object_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class TelegramPairing(Base):
    """A single-use code digest; raw code never enters persistent storage."""
    __tablename__ = 'telegram_pairings'
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TelegramBinding(Base):
    __tablename__ = 'telegram_bindings'
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    telegram_user_id: Mapped[str] = mapped_column(String(28))
    chat_id: Mapped[str] = mapped_column(String(28))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramUpdate(Base):
    """Incoming Telegram update_id de-duplication survives Render restarts."""
    __tablename__ = 'telegram_updates'
    update_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoogleOAuthAttempt(Base):
    """One-time owner-scoped OAuth challenge, PKCE verifier encrypted at rest."""
    __tablename__ = "google_oauth_attempts"
    nonce_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GoogleConnection(Base):
    """Server-only encrypted refresh token; never returned to browser."""
    __tablename__ = "google_connections"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    refresh_ciphertext: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AutonomousRun(Base):
    """Persistent cron slot, lease, metrics and sanitized errors."""
    __tablename__ = "autonomous_runs"
    key: Mapped[str] = mapped_column(String(96), primary_key=True)
    kind: Mapped[str] = mapped_column(String(12), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_count: Mapped[int] = mapped_column(Integer, default=0)
    new_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(48), nullable=True)


class AutonomousSyncBlock(Base):
    """Do not retry an unchanged Google grant after permission rejection."""
    __tablename__ = "autonomous_sync_blocks"
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    grant_version: Mapped[str] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(48))


class AutonomousDigest(Base):
    """Owner-only daily report; unknown Telegram outcome must not replay."""
    __tablename__ = "autonomous_digests"
    event_key: Mapped[str] = mapped_column(String(96), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    receipt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
