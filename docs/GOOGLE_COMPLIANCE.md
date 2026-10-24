# Google Business Profile policy gate (verified 2026-10-24)

Official references:

- https://developers.google.com/my-business/content/prereqs
- https://developers.google.com/my-business/content/policies
- https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews
- https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/updateReply
- https://developers.google.com/my-business/content/notification-setup

Requirements: manage verified active profile 60+ days and representative website; create Cloud project, apply for API access, await approval. Actual account owner credentials and API quota cannot be inferred from repository access.

Google content storage: limited performance-only cache, <=30 calendar days, no manipulation/aggregation of cached API content. This project defaults to a 28-day cache expiry; scheduled cleanup and policy approval must be enabled before live ingestion. Do NOT persist reviewer names unnecessarily or claim derived historical Google metrics are automatically permitted.

Reply publishing: requires current specific and express business-owner authorization, live Google permissions rechecked for account/location/review, fresh review version verification, current reply check, idempotency and read-after-timeout verification. None of those real-platform prerequisites is implemented in this offline MVP. `simulated_published` is categorically not Google publication.

Third-party requirements: business owners/end clients must sign in themselves; software providers must not expose their Google Business Profile project to third parties to circumvent project access limits. Agencies/end-clients using their own programmatic access may require their own Business Profile API project. Review multi-tenant SaaS strategy and Google approval with Google support BEFORE enabling live integration.

Pub/Sub notifications need configured topic, permissions, and managed NotificationSetting; never overwrite existing settings without user knowledge. Push callbacks must validate service account OIDC token / audience as applicable.
