# Parent / child authentication — design, security posture, and ops

Slice `auth/parent-child` (owner decision **2026-06-03**). This is the tracked
design-of-record for the parent sign-up + child-account system. It reverses the
"authentication is post-launch" line in `TECH_STACK §9` — that reversal is a
deliberate owner decision; the per-commit rationale is in the `auth:` commit log
(the planning docs are gitignored, so the commit messages + this file are the
tracked record per `CLAUDE.md §1`).

## What it is

A parent is the account holder and the COPPA consent authority. The parent creates
each child's profile and login. This is the cleanest path to COPPA **verifiable
parental consent**: the parent's own authenticated action *is* the consent event.

- **Parent auth:** Google sign-in **or** email + password. Email/password parents
  must verify their email (the consent anchor) via a link sent through AWS SES.
- **Child access (chosen model):** parent-managed profiles **+** a non-identifying
  **username + 4-digit PIN**.
  - *At home:* the signed-in parent picks a child profile (`start-session`) — no
    child secret needed.
  - *School / own device:* the child logs in with **just username + PIN**
    (`/child/login`) — **no parent email** (revised 2026-06-04: a kid does not know it).
    Usernames are therefore **globally unique**.
  - A 4-digit PIN (not a full password) is developmentally right for an 11–12-year-old.
    Because usernames are global (enumerable), the PIN is defended by a **common-PIN
    blocklist** (rejects 1234/0000/runs/popular PINs at setup), a **per-account lockout**
    (5 tries → 15-min freeze), and **per-IP rate limiting** — not by the hash alone. No
    child email is ever collected (data minimization).
  - **Why this is proportionate (threat model):** a compromised child session reaches
    only *that child's own lessons* — a child cookie gets a flat 403 on every parent
    endpoint, can't see any other family (BOLA), can't reset its own PIN or reach
    billing/email/real identity (none collected). The blast radius is one kid's math
    progress, so the controls are sized to that. If the child surface ever holds
    something sensitive, escalate to a **family code** or **QR/login-link** (designs on
    file). Mirrors Khan Academy's global-username model.

## Security controls (mapped to OWASP / NIST)

| Control | Where |
| --- | --- |
| Argon2id password + PIN hashing, no side-channel verify | `app/auth/passwords.py` |
| Password policy (length floor/ceiling, common-password blocklist; no composition rules — NIST 800-63B) | `app/auth/passwords.py` |
| PIN brute-force lockout (5 tries → 15-min lock, per-account) | `app/auth/pin_lockout.py` |
| Common-PIN blocklist at setup (anti-spraying; usernames are global) | `app/auth/passwords.py` `_common_pins` |
| Session JWT (HS256), short-lived, deterministic verify | `app/auth/tokens.py` |
| **Revocable** sessions → real logout + parent "sign out everywhere" kill-switch | `AuthSession` table + repo |
| HttpOnly + Secure + SameSite session cookie (token unreadable by JS) | `app/api/parent_session.py` |
| Double-submit CSRF on state-changing routes | `app/auth/csrf.py`, `parent_session.require_csrf` |
| **BOLA** (OWASP API #1): per-child ownership enforced *in-query*, one chokepoint | `repo.get_child_for_parent`, `child_account_service._require_owned_child` |
| IDOR defense-in-depth: opaque UUID `public_id` in URLs, never the sequential id | `Learner.public_id` |
| Mass-assignment / BOPLA: `extra="forbid"` request models; role/parent_id/consent server-set only | `*_schemas.py` |
| No user enumeration: one generic 401 + constant-time dummy-hash on the not-found path | `parent_auth_service`, `child_account_service` |
| Rate limiting on signup / login / child-login (app-layer; WAF is the authoritative cap) | `app/api/rate_limit.py` |

## COPPA posture

- **Verifiable parental consent** = the authenticated parent creating the child; a
  `ConsentRecord` (who, policy version, method, IP, timestamp) is stamped in the
  **same commit** as the child row, so a child never exists without its proof of consent.
- **Data minimization:** child data is a nickname (not real name — UI instructs this),
  grade, locale, a username + PIN hash, and learning progress. **No child email.**
- **Parental rights:** review/export (`GET /parent/children/{id}/export`) and delete
  (`DELETE /parent/children/{id}` → cascades the child's rows) — the COPPA review +
  deletion rights. *(2025 COPPA amendment, compliance deadline 2026-04-22.)*
- **No third-party sharing** of child data (avoids the 2025 separate-consent rule). The
  LLM never sees child PII (identity is off the turn loop — `ARCHITECTURE.md §14 inv 8`).

If a **school** ever becomes the customer, add a separate FERPA "school-official"
tenancy mode with a DPA and no commercial repurposing — do not blur it with this
direct-to-consumer parent flow.

## Configuration (see `.env.example`)

`SESSION_SIGNING_KEY` (required — fail-closed if unset), `SESSION_COOKIE_SECURE`
(false only for local http), `PUBLIC_API_BASE_URL` (builds the verify link),
`SES_SENDER` + `AWS_REGION` (real email; logging fallback when unset),
`GOOGLE_CLIENT_ID` (shared with the frontend).

## Ops runbook — AWS SES (the remaining infra step)

Email/password verification needs a verified SES sender. This is the one piece not
codifiable purely in app code:

1. In SES (region = `AWS_REGION`), **verify the sender identity** — ideally the
   domain `whollymath.app` (add the SES DKIM CNAME records to DNS), or at minimum a
   single `no-reply@whollymath.app` address.
2. If the SES account is in the **sandbox**, request production access (sandbox can
   only send to pre-verified recipients).
3. Grant the Fargate task role `ses:SendEmail` (scoped to the verified identity).
   Add this to the `AppStack` task role in `infrastructure/` (CDK).
4. Set `SES_SENDER=no-reply@whollymath.app` (and `PUBLIC_API_BASE_URL=https://whollymath.app`)
   in the task's environment / Secrets Manager.

Until step 4 is done the app runs with the **logging fallback**: the verification
link is written to the server log instead of emailed, so the flow is testable in dev
without SES. Also configure an **AWS WAF rate-based rule** on the auth paths — that
edge limiter (keyed on the true client IP) is the authoritative cap; the in-process
`rate_limit.py` is defense-in-depth.
