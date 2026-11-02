"""Google Business Profile owner account/location discovery, HTTPS GET only.

Called after an approved owner OAuth grant. This module never stores tokens,
creates locations, changes profiles, or publishes review replies.
"""
from dataclasses import dataclass
import re

import httpx

from .google_reviews import GoogleReviewAccessError

_ACCT = re.compile(r"accounts/[0-9]+\Z")
_LOCATION = re.compile(r"locations/[0-9]+\Z")


@dataclass(frozen=True)
class AccessibleAccount:
    name: str


@dataclass(frozen=True)
class AccessibleLocation:
    name: str
    title: str
    review_parent: str


def _list(client, url, token, collection, *, max_pages, extra=None):
    if not isinstance(token, str) or not 20 <= len(token) <= 8192:
        raise GoogleReviewAccessError("Business owner OAuth grant required")
    if not 1 <= max_pages <= 4:
        raise GoogleReviewAccessError("Bounded discovery page limit required")
    results, seen, page_token = [], set(), None
    for _ in range(max_pages):
        params = dict(extra or {})
        if page_token:
            params["pageToken"] = page_token
        try:
            response = client.get(url, params=params,
                                  headers={"Authorization": "Bearer " + token},
                                  timeout=15.0)
        except httpx.HTTPError:
            raise GoogleReviewAccessError("Google discovery transport unavailable") from None
        if response.status_code != 200:
            raise GoogleReviewAccessError(
                f"Google account/location discovery rejected (HTTP {response.status_code})")
        try:
            body = response.json()
        except ValueError:
            raise GoogleReviewAccessError("Invalid Google discovery JSON") from None
        if not isinstance(body, dict) or not isinstance(body.get(collection, []), list):
            raise GoogleReviewAccessError("Invalid Google discovery response")
        results.extend(body.get(collection, []))
        page_token = body.get("nextPageToken")
        if not page_token:
            return results
        if not isinstance(page_token, str) or len(page_token) > 512 or page_token in seen:
            raise GoogleReviewAccessError("Google discovery pagination loop")
        seen.add(page_token)
    raise GoogleReviewAccessError("Google discovery exceeded page limit")


def discover_accounts(access_token, *, client=None):
    """Retrieve authorized accounts through the Account Management API."""
    if client is None:
        with httpx.Client(follow_redirects=False, timeout=15) as http:
            return discover_accounts(access_token, client=http)
    raw = _list(client, "https://mybusinessaccountmanagement.googleapis.com/v1/accounts",
                access_token, "accounts", max_pages=4, extra={"pageSize": 20})
    out = []
    for a in raw:
        name = a.get("name") if isinstance(a, dict) else None
        if not isinstance(name, str) or not _ACCT.fullmatch(name):
            raise GoogleReviewAccessError("Invalid Google account resource")
        out.append(AccessibleAccount(name))
    if len({a.name for a in out}) != len(out):
        raise GoogleReviewAccessError("Duplicate accessible Google accounts")
    return out


def discover_locations(access_token, account_name, *, client=None):
    """Return only Google-listed owner-accessible location identities.

    Google reviews GET separately determines whether a selected location
    is verified and whether this OAuth principal can read its reviews.
    """
    if not isinstance(account_name, str) or _ACCT.fullmatch(account_name) is None:
        raise GoogleReviewAccessError("Untrusted account path")
    if client is None:
        with httpx.Client(follow_redirects=False, timeout=15) as http:
            return discover_locations(access_token, account_name, client=http)
    url = ("https://mybusinessbusinessinformation.googleapis.com/v1/"
           + account_name + "/locations")
    raw = _list(client, url, access_token, "locations", max_pages=4,
                extra={"pageSize": 100, "readMask": "name,title"})
    out = []
    for loc in raw:
        name = loc.get("name") if isinstance(loc, dict) else None
        title = loc.get("title") if isinstance(loc, dict) else None
        if (not isinstance(name, str) or _LOCATION.fullmatch(name) is None or
            not isinstance(title, str) or not title.strip() or len(title) > 160):
            raise GoogleReviewAccessError("Invalid Google location metadata")
        out.append(AccessibleLocation(name, title, account_name + "/" + name))
    if len({x.name for x in out}) != len(out):
        raise GoogleReviewAccessError("Duplicate accessible Google locations")
    return out
