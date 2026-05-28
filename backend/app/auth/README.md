# app/auth/ — Google OIDC identity (Slice PL.3)

Google OIDC identity: verifies Google ID tokens and maps them to a persistent
learner. Identity never reaches the mastery model, policy, or LLM — invariant 8.

## What lives here

- `google.py` — verifies a Google ID token with Google's **official** library
  (`google.oauth2.id_token.verify_oauth2_token`, which fetches Google's JWKS and
  checks the RS256 signature, issuer, audience, and expiry) and returns a frozen
  `GoogleIdentity(sub, email)`. On any failure it raises a single
  `InvalidIdTokenError` and never leaks the underlying error detail to callers.
  Also exposes `google_client_id()` — the configured `GOOGLE_CLIENT_ID` (or `None`
  when auth is not configured, so the anonymous session-id flow is unaffected).

## What does NOT live here

- No JWT/crypto is hand-rolled. We delegate token verification to Google's
  maintained library (PROJECT.md §3.12 "don't build your own auth").
- No passwords are stored anywhere. A learner is keyed to the Google account id
  (`sub`).
- This module imports ONLY `google-auth` + stdlib + the local `GoogleIdentity`
  type. It does NOT import `app.mastery`, `app.policy`, `app.llm`, or `app.domain`
  — ARCHITECTURE.md §14 invariant 8, enforced by a structural test
  (`tests/auth/test_invariant8_imports.py`). The verified identity is mapped to a
  `learner_id` for persistence/continuity only; the turn decision
  (verify → mastery → policy → helpneed) never sees identity.

## Going live

The code and tests are complete without a real client id. Going LIVE requires
setting a real `GOOGLE_CLIENT_ID` in the environment (`.env` locally, Secrets
Manager in prod) — an operational step. When unset, a presented Bearer token is
rejected (401, "auth not configured") and the anonymous flow continues unaffected.
