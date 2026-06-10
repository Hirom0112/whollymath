# app/auth/ — identity & credential primitives

The security-sensitive auth layer. It produces, at most, a `learner_id`; the
verified identity NEVER reaches the mastery model, policy, or LLM — ARCHITECTURE.md
§14 invariant 8, enforced by `tests/auth/test_invariant8_imports.py`.

Two things were built here, in order:

1. **Google OIDC identity** (Slice PL.3) — verify a Google ID token, map it to a learner.
2. **Parent/child accounts** (Slice `auth/parent-child`, owner decision 2026-06-03) — a
   self-managed parent sign-up + child-login system layered on top. This **reversed** the
   "authentication is post-launch / Google-only, no passwords stored" posture; the tracked
   design-of-record is **AUTH.md** at the repo root.

We do not hand-roll crypto anywhere in this directory (PROJECT.md §3.12 "don't build your
own auth", CLAUDE.md §8.7). Every primitive delegates to an audited library: Google's
verifier, `argon2-cffi`, and `PyJWT`.

## What lives here

- `google.py` — verifies a Google ID token with Google's **official** library
  (`google.oauth2.id_token.verify_oauth2_token` — fetches Google's JWKS, checks the RS256
  signature, issuer, audience, and expiry) and returns a frozen `GoogleIdentity(sub, email)`.
  Collapses every failure into a single `InvalidIdTokenError`, never leaking the underlying
  reason (no side-channel via error text). Exposes `google_client_id()` — the configured
  `GOOGLE_CLIENT_ID` (or `None` when unset, so the anonymous flow is unaffected).
- `passwords.py` — Argon2id (`argon2-cffi` `PasswordHasher`) hashing + policy for **parent
  passwords and child PINs**. Fixed documented parameters, per-hash random salt,
  `needs_rehash` for future bumps; verify returns `False` (never raises) on a wrong or
  malformed secret. Also holds the password policy (NIST 800-63B: length floor/ceiling +
  common-password blocklist, no composition rules) and the common-PIN blocklist (`_common_pins`).
- `pin_lockout.py` — **pure** child-PIN brute-force lockout policy: a deterministic function
  of `LockoutState` + an explicit `now` (no DB, no wall clock, no identity). A 4-digit PIN
  has only 10,000 values, so its real defense is online rate-limiting —
  `LOCKOUT_THRESHOLD` (5) consecutive wrong PINs → locked for `LOCKOUT_DURATION` (15 min).
  The endpoint maps `Learner.failed_pin_attempts` / `pin_locked_until` to/from `LockoutState`.
- `tokens.py` — mint + verify **our own** short-lived session JWTs (`PyJWT`, HS256, signing
  key from Secrets Manager in prod). `google.py` only verifies *Google's* tokens; a
  parent/child session needs a token we issue. The JWT carries only `sub`, `kind`
  (`"parent"`/`"child"`), a unique `jti`, `iat`, `exp` — no PII. The `jti` links to a
  **revocable** `AuthSession` row, so "sign out everywhere" / kill-switch actually works.
- `csrf.py` — double-submit CSRF protection for the cookie-borne session: a separate readable
  `wm_csrf` cookie the SPA echoes in an `X-CSRF-Token` header; the server requires cookie ==
  header (OWASP CSRF Cheat Sheet). Used by `app/api/parent_session.py` (`require_csrf`).

A fuller control map (BOLA, IDOR, mass-assignment, enumeration, rate limiting) lives in
**AUTH.md**.

## The account model (summary — full design in AUTH.md)

- **Parent** = account holder + COPPA consent authority. Signs in with **Google OIDC _or_
  email + password**. Email/password parents verify their email (the consent anchor) via an
  AWS SES link; Google parents are pre-verified. No child session may start until the parent
  is verified (403 otherwise).
- **Child** = parent-created profile + a non-identifying **username + 4-digit PIN**. At home
  the signed-in parent picks the profile; at school/own device the child logs in with
  username + PIN alone (so usernames are globally unique). We store **hashes only**
  (`password_hash`, `pin_hash`) — never a plaintext credential, and never a child email.

## What does NOT live here

- **No business logic.** This directory holds primitives. The flows that compose them
  (signup, login, child management, sessions) live in `app/api/` services/routes.
- **No DB access** in the pure primitives. `pin_lockout.py` is pure; hashing/JWT/CSRF take
  values in and out. The endpoints read/write the `Learner` / `AuthSession` columns.
- **No identity on the turn path.** None of this imports `app.mastery`, `app.policy`,
  `app.llm`, or `app.domain` — invariant 8, structurally tested. A verified identity becomes
  a `learner_id` for persistence/continuity only; `verify → mastery → policy → helpneed`
  never sees it.

## Configuration / going live

- **Google path:** env-gated by `GOOGLE_CLIENT_ID` (`.env` locally, Secrets Manager in prod).
  Unset ⇒ a presented Bearer token is rejected (401 "auth not configured") and the anonymous
  session-id flow continues unaffected.
- **Email/password path:** requires the session signing key and a **verified AWS SES sender**
  so verification emails can be sent — the one remaining operational step before
  email/password signups work in production (flagged in ROADMAP).
