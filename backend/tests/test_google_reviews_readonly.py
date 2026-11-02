"""Offline acceptance for official read-only GBP reviews. No Google/SMTP calls."""
import httpx
import pytest
from sqlalchemy import select

from app.google_reviews import (
    GoogleReviewAccessError, REVIEW_SCOPE, prepare_review_drafts,
    read_verified_reviews,
)
from app.models import Location, Review, User, utcnow
from .conftest import signup


def _mock(payloads):
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.url.host == "mybusiness.googleapis.com"
        assert request.url.path == "/v4/accounts/100/locations/200/reviews"
        assert request.headers.get("Authorization") == "Bearer " + "s" * 40
        return httpx.Response(200, json=payloads[min(len(seen)-1, len(payloads)-1)])
    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def _item(text="Çok iyi", updated="2026-10-31T10:00:00Z"):
    return {"reviewId": "review-101", "comment": text,
            "starRating": "FIVE", "updateTime": updated}


def test_google_reader_is_bounded_read_only_and_skips_rating_only():
    assert REVIEW_SCOPE == "https://www.googleapis.com/auth/business.manage"
    http, seen = _mock([
        {"reviews": [_item(), {"reviewId": "rating-only", "starRating": "FOUR"}],
         "nextPageToken": "page-2"},
        {"reviews": [{"reviewId": "review-102", "comment": "Geç geldi",
                      "starRating": "TWO", "updateTime": "2026-11-01T00:00:00Z"}]},
    ])
    with http:
        rows = read_verified_reviews("s"*40, "accounts/100/locations/200", client=http)
    assert len(rows) == 2
    assert [r.stars for r in rows] == [5, 2]
    assert len(seen) == 2 and seen[1].url.params["pageToken"] == "page-2"


def test_reader_rejects_untrusted_location_without_network():
    http, seen = _mock([])
    with http:
        for path in ("https://evil.test", "accounts/1/locations/../../secrets",
                     "accounts/1/locations/2/reviews", "accounts/foo/locations/200"):
            with pytest.raises(GoogleReviewAccessError):
                read_verified_reviews("s"*40, path, client=http)
        with pytest.raises(GoogleReviewAccessError):
            read_verified_reviews("", "accounts/100/locations/200", client=http)
    assert not seen


def test_google_403_is_redacted_and_no_reply_api_called():
    seen = []
    def deny(request):
        seen.append(request)
        return httpx.Response(403, json={"message": "private account details"})
    with httpx.Client(transport=httpx.MockTransport(deny)) as http:
        with pytest.raises(GoogleReviewAccessError, match="HTTP 403") as exc:
            read_verified_reviews("s"*40, "accounts/100/locations/200", client=http)
    assert "private account details" not in str(exc.value)
    assert "s"*40 not in str(exc.value)
    assert len(seen) == 1 and seen[0].method == "GET"


def test_reader_rejects_pagination_loop_without_claiming_completion():
    http, seen = _mock([{"reviews": [_item()], "nextPageToken": "repeat"},
                        {"reviews": [], "nextPageToken": "repeat"}])
    with http:
        with pytest.raises(GoogleReviewAccessError, match="repeating"):
            read_verified_reviews("s"*40, "accounts/100/locations/200", client=http)
    assert len(seen) == 2


def test_google_drafts_are_idempotent_and_update_revokes_approval(client):
    org = signup(client)
    with client.db_factory() as db:
        loc = db.scalar(select(Location).where(Location.organization_id == org))
        loc.is_demo = False
        loc.google_resource_name = "accounts/100/locations/200"
        location_id = loc.id
        db.commit()

    def run_with(comment, time):
        http, _ = _mock([{"reviews": [_item(comment, time)]}])
        with client.db_factory() as db, http:
            outcome = prepare_review_drafts(db, org, location_id, "s"*40, client=http)
            db.commit()
        return outcome

    first = run_with("Çok iyi", "2026-10-31T10:00:00Z")
    second = run_with("Çok iyi", "2026-10-31T10:00:00Z")
    assert first == {"read": 1, "drafts_created_or_refreshed": 1,
                     "google_replies_published": 0}
    assert second["drafts_created_or_refreshed"] == 0
    with client.db_factory() as db:
        review = db.scalar(select(Review).where(Review.external_id == "review-101"))
        user_id = db.scalar(select(User.id))
        review.draft.approved_by = user_id
        review.draft.approved_at = utcnow()
        review.status = "approved"
        db.commit()
    changed = run_with("Gecikme vardı", "2026-11-01T10:00:00Z")
    assert changed["drafts_created_or_refreshed"] == 1
    with client.db_factory() as db:
        rows = db.scalars(select(Review).where(Review.external_id == "review-101")).all()
        assert len(rows) == 1 and rows[0].status == "awaiting_approval"
        assert rows[0].draft.approved_by is None
        assert rows[0].draft.review_revision == rows[0].revision


def test_demo_location_cannot_be_synced_even_with_token(client):
    org = signup(client)
    with client.db_factory() as db:
        loc = db.scalar(select(Location).where(Location.organization_id == org))
        loc.google_resource_name = "accounts/100/locations/200"
        db.commit()
        http, seen = _mock([{"reviews": [_item()]}])
        with http:
            with pytest.raises(GoogleReviewAccessError, match="non-demo"):
                prepare_review_drafts(db, org, loc.id, "s"*40, client=http)
        assert not seen
