# Execution roadmap

## Phase 1 - Offline vertical slice (implemented)
- Backend REST, PostgreSQL models, mock Google adapter, deterministic review processing, safe editor/approval flow
- Account-separated interactive dashboard and landing; synthetic data label throughout
- Backend unit/integration security tests

## Phase 2 - Internal beta readiness (not implemented)
- Rate limiting, email validation and reset, account deletion, tenant invite flows, subscription model
- Safe background worker + scheduled purge (daily minimum), DLQ, dedupe, monitoring, tracing
- Telegram/ntfy channels with per-user secure binding and verified deliveries
- Real LLM provider adapter with consent, schema validation, budgets and timeout/retry
- Full Alembic incremental migrations, real PostgreSQL integration testing and E2E UI browser tests

## Phase 3 - Google compliance gate (not implemented)
- 60+ day verified managed GBP and business website; eligible Cloud organization and project
- Apply and wait for official Google approval; clarify own project per client/agency usage restrictions
- OAuth2 Authorization Code + PKCE/state, encrypted refresh tokens, revoke/delete flows
- Pub/Sub NEW_REVIEW/UPDATED_REVIEW with authenticated subscription validation and existing-topic safeguard
- Read review & write approval verification with stale-version and idempotent error-safe reconcile

## Phase 4 - Commercial SaaS (not implemented)
- Recurring subscriptions, billing and compliant data disclosures, team roles, multi-business routing
- Production incident response, audit, backups, multi-tenant pentest, privacy and security review
- External pilot customers only after policy approval, successful live end-to-end verification

## Acceptance status 2026-10-24
BACKEND: 19/19 PASS for scoped offline tests; migration PASS. FRONTEND: TypeScript parser 11/11 PASS, complete npm build UNVERIFIED (dependency download timeout).
GOOGLE: PENDING. GITHUB: target repo missing. RENDER: workspace accessible, no new deployment created.
OVERALL: PARTIAL (not a finished live SaaS).
