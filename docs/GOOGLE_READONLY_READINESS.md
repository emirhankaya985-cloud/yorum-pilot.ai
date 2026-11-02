# YorumPilot Google Business Profile — OAuth / live read-only cutover

**Current status: PR-only, not deployed.** İşletmePilot `site-nobet-ai` remains on
the previously accepted `04cda228`; its SMTP producer stays retired.
`yorum-pilot.ai` is an independent Render/Neon application. This PR makes
the *YorumPilot* application the sole owner for any real Google review
ingestion and draft revision. No cross-service automatic bridge is deployed.

## Implemented boundaries

- OAuth start is a **CSRF-protected owner-only POST**; state binds
  user + organization + random nonce and is signed, time-limited, hashed
  in database, consumed atomically before code exchange (single use).
  PKCE S256 verifier is encrypted at rest; `client_secret` never goes to
  browser. The Google code callback requires the original owner session
  and exact registered `https` redirect URI, and redirects with no code/token.
- The encrypted server-side **refresh** token is the only persistent bearer
  grant; access tokens live exclusively inside backend requests. The key is
  a separately provisioned Fernet key in `GOOGLE_TOKEN_ENCRYPTION_KEY`,
  **never** put in Git, public CI logs or frontend. Connection revocation
  immediately removes the local encrypted grant; remote Google revocation
  is best-effort and owner should also revoke third-party access at Google.
  Changing the Fernet key without re-encrypting grants invalidates them.
- Non-owner access is hidden by organization membership checks. Only
  Google-returned authorized accounts/locations can be selected, and
  demo locations **cannot** be converted to real locations.
- Manual `/sync/{location_id}` rechecks Google ownership on every read.
  Stable `(org,location,reviewId)` de-duplication creates one YorumPilot
  draft. Google review revision change revokes old human approval.
  No `updateReply`, no Google write scopes beyond the provider's mandated
  `business.manage` scope, no scheduled ingestion and no auto-publish.
- Approval gate is **fail-closed** unless
  `GOOGLE_BUSINESS_API_APPROVED=true` AND all client, redirect, encryption
  secrets are configured. No secret is visible in status API.
- Tokens expire/revoke: failed refresh revokes local grant on `invalid_grant`.
  API rate/quota/network errors never produce a published result. Failures
  in pagination/permission are rejected, with no partial DB commit.

## Deployment prerequisites — NOT verified

1. A verified Google Business Profile owner and actual accessible account
   and location; Google must approve the API project and its quota.
2. Dedicated OAuth Web application (do **not** reuse CareerHunter Gmail or
   YouTube OAuth clients), Google Cloud consent screen and
   `business.manage` scope approved.
3. Runtime secrets on the **existing** YorumPilot backend only:
   `GOOGLE_BUSINESS_API_APPROVED=true`,
   `GOOGLE_OAUTH_CLIENT_ID`,
   `GOOGLE_OAUTH_CLIENT_SECRET`,
   `GOOGLE_OAUTH_REDIRECT_URI=https://yorumpilot-web.onrender.com/api/organizations/<actual-owner-org-id>/google/callback`,
   `GOOGLE_TOKEN_ENCRYPTION_KEY` (Fernet). No example real values are
   included in this PR. A fixed redirect URI **per organization** is
   currently required: multi-tenant rollout must choose an OAuth redirect
   design that supports all registered organization URLs before production.
4. Apply additive Alembic revision `0003_google_oauth` **before** starting
   upgraded API. Existing demo organizations/reviews/drafts must remain.
5. Real consent and a live read-only pilot are mandatory before any claim
   of live Google synchronization. This PR's 48+ tests use synthetic
   provider fixtures and cannot demonstrate Google entitlement.

## Single source of truth / smallest safe bridge

- **Google review ownership:** YorumPilot Neon
  `reviews_cache` and `ai_drafts`. Unique
  `(organization_id, location_id, external_id)` ensures 1 draft per review.
  Google resource `accounts/N/locations/M` is bound only after provider
  verification and never inferred from business names.
- **BusinessPilot:** separate organization IDs, separate database,
  `review_drafts` used only for its own manually imported reviews.
  A Google review MUST NOT also be sent to BusinessPilot
  `/business/reviews/import`: that would create a second independent draft.
- Future integration must require an explicit tenant mapping maintained by
  owners in both services, and an immutable external composite key, plus a
  single writer. Until mappings and authorization exist, do not copy review
  content or count BusinessPilot drafts as Google production replies.
- Old Müşteri Avcısı email CRM history is unrelated and must not be touched.

## Safe rollback (requires explicit user production approval)

Leave `yorum-pilot.ai` production at the prior successful commit until
approved. If the upgraded release fails after permission to deploy:
roll the YorumPilot API/Web code back to its prior commit and keep
`google_oauth_attempts` / `google_connections` intact.
**Never downgrade nonempty OAuth tables**; the migration deliberately
refuses a data-losing downgrade. Disable approval gate; preserve encrypted
grants until owner authorizes revocation, then erase. Do not change
`site-nobet-ai`, Gmail watcher, Telegram polling or SMTP.


## Telegram-first/headless use

Existing securely paired owner/admin Telegram chats may request `/rapor` without
opening a dashboard. The command reads **metadata counts only** for the authorized
organization and non-demo locations; it excludes synthetic data, review content,
customer identities, OAuth credentials and tokens. It does **not** fetch new Google
reviews, initiate a scheduled sync or publish replies. Unpaired chats cannot inspect
tenant data; membership revocation removes access. Delivery is only attempted when
the existing bot webhook is configured and the private chat is already bound.

The frontend/API must not be deleted blindly: initial secure Telegram pairing and
the Google OAuth callback/proxy still rely on these routes. First-time owner identity
binding and Google's explicit OAuth consent cannot be bypassed by a background job.
Existing public demo/API and Neon data remain untouched by this branch. No automatic
SMTP is enabled.
