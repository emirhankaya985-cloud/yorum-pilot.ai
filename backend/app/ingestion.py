"""Idempotent review upsert, meant to be called only after Google identity validation."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Review, Draft
from .ai import RuleBasedProvider
from .lifecycle import cache_expiry


def ingest(db: Session, org_id: str, location_id: str, external_id: str, revision: str, text: str, stars: int):
    if not (1 <= stars <= 5) or len(text) > 16000:
        raise ValueError('Invalid review payload')
    review = db.scalar(select(Review).where(Review.organization_id == org_id,
                                            Review.location_id == location_id,
                                            Review.external_id == external_id))
    if review and review.revision == revision:
        return review, False
    analysis = RuleBasedProvider().analyze(text, stars)
    if review:
        # An update invalidates prior approval, preventing stale replies.
        review.revision = revision
        review.content = text
        review.stars = stars
        review.sentiment = analysis.sentiment
        review.priority = analysis.priority
        review.category = analysis.category
        review.language = analysis.language
        review.status = 'awaiting_approval'
        review.expires_at = cache_expiry()
        if review.draft:
            review.draft.text = analysis.reply_draft
            review.draft.approved_by = None
            review.draft.approved_at = None
            review.draft.review_revision = revision
        else:
            review.draft = Draft(text=analysis.reply_draft, review_revision=revision)
    else:
        review = Review(organization_id=org_id, location_id=location_id,
                        external_id=external_id, revision=revision, content=text,
                        stars=stars, sentiment=analysis.sentiment, priority=analysis.priority,
                        category=analysis.category, language=analysis.language,
                        status='awaiting_approval', expires_at=cache_expiry())
        review.draft = Draft(text=analysis.reply_draft, review_revision=revision)
        db.add(review)
    db.flush()
    return review, True
