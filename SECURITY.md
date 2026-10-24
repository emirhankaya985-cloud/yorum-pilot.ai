# Security notes

Demo only. Do not add live Google/LLM secrets to the repository. Do not treat demo approval as Google authorization.

Current controls: argon2id password hashes, signed HTTP-only session cookie, double-submit CSRF header, origin allowlist, tenant-scoped database queries, role-based modification guards, 4096-byte reply validation, 28-day review cache expiry and idempotent simulated publications.

Unresolved production blockers: sign-up verification, rate limiting, abuse monitoring, separate permission testing for real Google OAuth, Google notification authentication, encryption at rest for Google tokens, scheduled purge deployment and failure monitoring, disaster recovery, security review, account deletion, privacy notices, provider data processing contracts, full audit coverage.

Report vulnerabilities privately to project owner. Never put secrets or real customer data in public issues.
