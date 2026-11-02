# YorumPilot: official Google reviews read-only implementation boundary

The live repo remains `emirhankaya985-cloud/yorum-pilot.ai`, distinct from
`emirhankaya985-cloud/site-nobet-ai` (İşletmePilot). Its existing API/Web
and Neon deployment are **not** changed by this feature branch.

## Implemented, offline-tested code

- `backend/app/google_reviews.py` uses the documented
  `GET https://mybusiness.googleapis.com/v4/accounts/{account}/locations/{location}/reviews`
  API; **never** POSTs review replies.
- `backend/app/google_discovery.py` uses Google's Account Management and
  Business Information **GET-only** APIs to list accounts and locations that
  the OAuth owner can access, with a required `readMask=name,title`.
  No account or location is automatically claimed as verified.
- Only resource names matching a numeric Google account/location, a bounded
  page count, and valid `business.manage` OAuth bearer credentials are accepted.
- Rejects malformed responses, pagination loops and Google permission denials.
  Exceptions never expose tokens, review text or provider error body.
- Only a non-demo, explicitly organization-bound `Location` with mapped
  `google_resource_name` may be synchronized. This does **not** invent a
  location or bypass Google's verified-location restriction.
- Transactional draft upsert uses existing `ingest()` and its 28-day
  lifecycle. Repeat is idempotent. Changed text/rating/time invalidates prior
  approval. Rating-only comments are skipped (no invented reply).
- No OAuth credentials are stored or logged. No scheduler, API route, Google
  publication, public response, secret or new paid resource is enabled.

## Remaining real live prerequisites (not simulated)

1. Google-approved Business Profile API project and verified business
   location, with an owner who explicitly authorizes access. API quota may be
   zero until Google grants approval.
2. Secure owner-authenticated OAuth authorization + callback: exact registered
   redirect URI, session-bound state/nonce, PKCE, short-lived access token,
   encrypted refresh token at rest (if background synchronization is approved),
   token revocation/deletion and tenant isolation. Existing `google_oauth.py`
   provides helpers but **not** a deployed login/callback flow.
3. Explicit account/location selection and verification via Google, not a
   guessed resource ID. A real verified location must replace demo entries
   without deleting the existing demo records.
4. Activate a separately authorized read-only sync schedule only after quotas,
   Google content retention and privacy compliance are proven. Manual draft
   approval remains required; `updateReply` is NOT included or enabled.

If any precondition is absent, keep `GOOGLE_MODE=mock` or `pending`.
Never report `simulated_published` as a real review reply.
Do not reuse CareerHunter Gmail OAuth or YouTube client credentials.

Official Google references:
- https://developers.google.com/my-business/content/prereqs
- https://developers.google.com/my-business/content/implement-oauth
- https://developers.google.com/my-business/reference/rest/v4/accounts.locations.reviews/list
- https://developers.google.com/my-business/reference/accountmanagement/rest/v1/accounts/list
- https://developers.google.com/my-business/reference/businessinformation/rest/v1/accounts.locations/list
