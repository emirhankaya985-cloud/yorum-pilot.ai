"""Provider discovery is read-only and scoped to the OAuth account."""
import httpx
import pytest

from app.google_discovery import discover_accounts, discover_locations
from app.google_reviews import GoogleReviewAccessError


def test_discovery_reads_only_official_account_and_location_endpoints():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert request.headers["Authorization"] == "Bearer " + "t" * 40
        if request.url.host == "mybusinessaccountmanagement.googleapis.com":
            assert request.url.path == "/v1/accounts"
            return httpx.Response(200, json={"accounts": [{"name": "accounts/1234"}]})
        assert request.url.host == "mybusinessbusinessinformation.googleapis.com"
        assert request.url.path == "/v1/accounts/1234/locations"
        assert request.url.params["readMask"] == "name,title"
        return httpx.Response(200, json={"locations": [
            {"name": "locations/5000", "title": "Actual authorized business"}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        accounts = discover_accounts("t" * 40, client=c)
        locations = discover_locations("t" * 40, accounts[0].name, client=c)
    assert len(accounts) == 1 and accounts[0].name == "accounts/1234"
    assert len(locations) == 1
    assert locations[0].review_parent == "accounts/1234/locations/5000"
    assert len(seen) == 2


def test_discovery_rejects_account_path_injection_before_request():
    seen = []
    def forbidden(request):
        seen.append(request)
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(forbidden)) as c:
        for path in ("https://evil.com", "accounts/1234/../../secrets",
                     "accounts/1234/locations/1", "accounts/fake"):
            with pytest.raises(GoogleReviewAccessError):
                discover_locations("t"*40, path, client=c)
    assert seen == []


def test_discovery_no_partial_claim_on_repeating_page():
    count = []
    def handler(request):
        count.append(request)
        return httpx.Response(200, json={
            "accounts": [{"name": "accounts/1234"}], "nextPageToken": "same"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(GoogleReviewAccessError, match="pagination loop"):
            discover_accounts("t"*40, client=c)
    assert len(count) == 2


def test_discovery_requires_token_and_valid_provider_data():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={
            "locations": [{"name": "not-a-real-location", "title": "Test"}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(GoogleReviewAccessError):
            discover_locations("", "accounts/1234", client=c)
        with pytest.raises(GoogleReviewAccessError, match="Invalid Google location"):
            discover_locations("t"*40, "accounts/1234", client=c)
    assert len(seen) == 1
