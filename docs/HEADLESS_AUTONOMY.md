# YorumPilot · panelsiz zamanlanmış işler (kod hazır, canlı kabul bekliyor)

Nominal GitHub Actions UTC schedule: **every hour :17** (read-only Google
review sync) and **20:59 UTC / 23:59 TRT** (private Telegram owner digest).
GitHub may delay or skip scheduled jobs. A successful offline CI or manual
workflow dispatch is NOT proof of an actual schedule-event run or delivery.

- Cron is fail-closed until the existing YorumPilot Neon URL and secure session
  secret are configured in GitHub. This requires a successful, non-destructive
  Alembic 0003 then 0004 migration. No second database is created.
- A database-backed per-slot lease and max-three-attempt bound prevents
  overlapping and duplicate work. Last success, last error and next nominal
  schedule are persisted/derived without copying customer text to logs.
- Official Google account/location access is rechecked before each GET-only
  review import; each changed revision invalidates prior draft approval.
  Demo records are excluded; missing API approval/owner OAuth prevents real sync.
  Permanent permission rejection blocks the unchanged owner grant.
- Private daily Telegram digests use only already securely bound owner/admin
  chat IDs, and store one claim per org/day with a provider message_id receipt.
  Ambiguous sends remain unknown and are NOT blindly retried.
- The YorumPilot DB owns Google reviews and drafts. İşletmePilot's independent
  importer is not bridged and must not become another Google draft writer.
  SiteNöbet status is reported as unverified rather than invented.
- Never send Google replies, customer emails or unapproved website probes.
  No YorumPilot standalone SMTP sender is activated.

Before any live deployment verify server-side secrets without disclosing them.
GitHub Actions needs: YORUMPILOT_DATABASE_URL, YP_SESSION_SECRET,
YP_GOOGLE_OAUTH_CLIENT_ID, YP_GOOGLE_OAUTH_CLIENT_SECRET,
YP_GOOGLE_TOKEN_ENCRYPTION_KEY and YP_TELEGRAM_BOT_TOKEN securely in Actions
secrets; GOOGLE_BUSINESS_API_APPROVED and YP_GOOGLE_OAUTH_REDIRECT_URI are
configuration variables. Do NOT copy keys into source, chat or logs.
The Google-approved Business Profile API and owner consent remain mandatory.
Telegram first binding requires the verified owner through the existing secure
web/API flow; existing API, OAuth callback, webhook and frontend must not be
deleted. No real owner was paired at implementation time.

Rollback: disable the workflow or revert code; retain all Neon history and
existing encrypted credentials. Never downgrade tables with rows, discard
user data, or force push. No merge or deploy without approved HEAD and preflight.
