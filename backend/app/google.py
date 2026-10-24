"""Explicit integration boundary: no undocumented scraping, no writes to Google."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PublishResult:
    status: str
    external_reference: str | None = None


class GoogleIntegrationPending(Exception):
    pass


class MockGoogleAdapter:
    def publish_reply(self, review_resource: str, text: str) -> PublishResult:
        # No external request. Simulated result is NEVER reported as a Google publication.
        return PublishResult(status='simulated_published')


class PendingGoogleAdapter:
    def publish_reply(self, review_resource: str, text: str) -> PublishResult:
        raise GoogleIntegrationPending('Official Google access and business authorization not verified')
