"""Data lifecycle: cached text and all derived drafts are deleted within 30 days."""
from datetime import timedelta
from sqlalchemy import delete
from sqlalchemy.orm import Session
from .models import Review, utcnow

CACHE_DAYS = 28  # safety margin before Google's 30 calendar day limit


def cache_expiry():
    return utcnow() + timedelta(days=CACHE_DAYS)


def purge_expired(db: Session) -> int:
    expired_ids = [r.id for r in db.query(Review.id).filter(Review.expires_at <= utcnow()).all()]
    if expired_ids:
        # ORM delete invokes child Draft cascade; no text retained in operational audit.
        for review in db.query(Review).filter(Review.id.in_(expired_ids)).all():
            db.delete(review)
        db.commit()
    return len(expired_ids)
