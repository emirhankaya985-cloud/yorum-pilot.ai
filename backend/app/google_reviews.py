"""Official Google Business Profile review reader; no OAuth secrets stored, no replies sent.

Call only with a scoped short-lived OAuth token from a verified, explicitly
authorized business owner. This is a library boundary, not a live OAuth route.
"""
from dataclasses import dataclass
from hashlib import sha256
import re

import httpx
from sqlalchemy import select

from .ingestion import ingest
from .models import Location

REVIEW_SCOPE = "https://www.googleapis.com/auth/business.manage"
_REVIEW_PATH = re.compile(r"accounts/[0-9]+/locations/[0-9]+\Z")
_STARS = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}


class GoogleReviewAccessError(RuntimeError):
    """Sanitized error: never include OAuth tokens or customer review content."""


@dataclass(frozen=True)
class GoogleReviewSnapshot:
    external_id: str
    revision: str
    comment: str
    stars: int


def _parse_review(raw):
    if not isinstance(raw, dict):
        raise GoogleReviewAccessError("Invalid Google review response")
    rid = raw.get("reviewId")
    rating = raw.get("starRating")
    comment = raw.get("comment")
    updated = raw.get("updateTime")
    # A rating-only review cannot produce a grounded textual reply draft.
    if comment is None or not isinstance(comment, str) or not comment.strip():
        return None
    if (not isinstance(rid, str) or not 1 <= len(rid) <= 200 or
        not isinstance(updated, str) or not updated or
        rating not in _STARS or len(comment) > 16000):
        raise GoogleReviewAccessError("Invalid Google review metadata")
    # Review updates revoke old approval via existing ingest() logic.
    fingerprint = sha256((updated + "\0" + rating + "\0" + comment).encode("utf-8")).hexdigest()
    return GoogleReviewSnapshot(rid, fingerprint, comment, _STARS[rating])


def _read(client, access_token, resource, max_pages):
    if not isinstance(access_token, str) or not (20 <= len(access_token) <= 8192):
        raise GoogleReviewAccessError("A valid owner OAuth token is required")
    if not isinstance(resource, str) or _REVIEW_PATH.fullmatch(resource) is None:
        raise GoogleReviewAccessError("Unverified Google location resource name")
    if not isinstance(max_pages, int) or not 1 <= max_pages <= 5:
        raise GoogleReviewAccessError("Bounded page limit required")
    endpoint = f"https://mybusiness.googleapis.com/v4/{resource}/reviews"
    token = None
    visited = set()
    snapshots = []
    seen_ids = set()
    for _ in range(max_pages):
        params = {"pageSize": 50, "orderBy": "updateTime desc"}
        if token:
            params["pageToken"] = token
        try:
            response = client.get(endpoint,
                                  headers={"Authorization": "Bearer " + access_token},
                                  params=params, timeout=15.0)
        except httpx.HTTPError as exc:
            raise GoogleReviewAccessError("Google review read transport unavailable") from None
        if response.status_code != 200:
            raise GoogleReviewAccessError(
                f"Google review read rejected (HTTP {response.status_code})")
        try:
            body = response.json()
        except ValueError:
            raise GoogleReviewAccessError("Invalid Google review JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get("reviews", []), list):
            raise GoogleReviewAccessError("Invalid Google review response shape")
        for entry in body.get("reviews", []):
            item = _parse_review(entry)
            if item is None:
                continue
            if item.external_id in seen_ids:
                raise GoogleReviewAccessError("Google returned duplicate review IDs")
            seen_ids.add(item.external_id)
            snapshots.append(item)
        token = body.get("nextPageToken")
        if not token:
            return snapshots
        if not isinstance(token, str) or len(token) > 512 or token in visited:
            raise GoogleReviewAccessError("Invalid or repeating Google page token")
        visited.add(token)
    # Do not silently claim a full sync if the server has more pages.
    raise GoogleReviewAccessError("Page limit reached; no partial sync permitted")


def read_verified_reviews(access_token, resource, *, client=None, max_pages=5):
    """Official, bounded HTTP GET only; never calls updateReply/publish."""
    if client is not None:
        return _read(client, access_token, resource, max_pages)
    with httpx.Client(follow_redirects=False, timeout=15) as session:
        return _read(session, access_token, resource, max_pages)


def prepare_review_drafts(db, org_id, location_id, access_token, *, client=None):
    """Owner-scoped read + transactional upsert; caller commits only after success.

    Requires an explicit non-demo mapping, secure OAuth exchange outside this
    module, and Google account/location access verified by the provider.
    """
    location = db.scalar(select(Location).where(
        Location.id == location_id,
        Location.organization_id == org_id,
        Location.is_demo.is_(False),
        Location.google_resource_name.is_not(None)))
    if location is None:
        raise GoogleReviewAccessError("No authorized, non-demo Google location")
    snapshots = read_verified_reviews(access_token, location.google_resource_name,
                                      client=client)
    changed = 0
    for review in snapshots:
        _, inserted = ingest(db, org_id, location.id, review.external_id,
                             review.revision, review.comment, review.stars)
        changed += int(inserted)
    return {"read": len(snapshots), "drafts_created_or_refreshed": changed,
            "google_replies_published": 0}
