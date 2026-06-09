# WhollyMath — Roadmap & Status

> The single, current "what's built / what's left" map for WhollyMath. Tracked and
> reviewer-facing (the detailed internal planning docs are local-only — see the end). For
> *how* the system works, read [`ARCHITECTURE.md`](./ARCHITECTURE.md); for setup, the
> [`README.md`](./README.md); for the auth design, [`AUTH.md`](./AUTH.md).
>
> Last updated 2026-06-08.

WhollyMath began as a fractions tutor and **has grown into a full Grade-6 math application**:
the whole 6-week curriculum, an English **and** Spanish help surface, a parent dashboard **and**
a teacher dashboard, a homework scanner, and a voiced avatar guide — with a conversational,
interactive tutor and richer avatars on the roadmap. This document reflects that expanded scope
honestly: what is genuinely shipped, what is partial, and what is not started.

---

## 1. What's built and live

**The adaptive turn loop (the core).** SymPy verify → BKT mastery → policy/refuse-rules →
observe-only HelpNeed, with no LLM on the graded path. Five surface states (S1–S5) with labeled,
rule-driven transitions and an S5 transfer-probe confirm gate.

**Curriculum — the full Grade-6 standard.** 9 units / 54 catalog lessons / **44 engine-served
KCs** (each with a problem generator, SymPy verifier path, misconceptions, validated hints, and a
lesson spec). Dual CCSS + TEKS coverage where both apply; integer arithmetic and personal
financial literacy are TEKS-only. The original five fraction KCs remain the deeply-tested core and
double as the remediation tier.

**Mastery model.** Per-KC BKT plus the anti-gaming guardrails (BKT threshold τ=0.90, ≥5 *engaged*
attempts, ≥2 representations, ≥1 unscaffolded correct, interleaving, engagement floor) — validated
by five adversarial synthetic personas as the integration suite.

**HelpNeed predictor.** XGBoost trained on EDM Cup 2023, **holdout AUC 0.900**, observe-only, with
a **33-KC trustworthy guard** (the harder ratio/expression KCs stay reactive-only).

**Dashboards (live data).** Teacher dashboard (ranked roster, per-child mastery/HelpNeed signals,
reminders) and parent dashboard (per-child progress drill-in). Parent/child auth: parent sign-up
(Google or email+password, Argon2id), child username+PIN, COPPA consent record + export/delete.

**Homework scan.** assign → QR → photo OCR (Mathpix, MockScanner fallback) → read-back →
SymPy-graded ★★ (OCR proposes; SymPy decides).

**V2 AI layer (shipped slices).** A talking 2D mascot guide with phoneme lip-sync; ElevenLabs
voice (pre-rendered bank + content-hash-cached live synth, off the turn loop); an es-MX Spanish
**help-mode** (176 reviewed help strings, captions-only); per-unit camera "snap your work" beat.

**Eval & infra.** Three-arm baseline comparison + proactive-intervention A/B harness; AWS CDK
(CloudFront → ALB → Fargate → RDS), live at whollymath.app.

---

## 2. What's left to build

### 2.1 Near-term (the real gaps)
- **Hyperreactive generalization** — make 6 hardcoded KC→representation bindings table-driven
  `LessonSpec` reads (verifier classification, worked-example, nudge bank, transfer-probe, the
  `Tutor.tsx` widget choice, error→state routing). Unlocks the full ~54-lesson "the interface is
  the tutoring" contract.
- **Geometry figure-drawing (6.G.4 net)** — wire the backend figure-scene type/deriver and connect
  the already-built `FigureStimulus` widget into the tutor.
- **Inequality solution-graph (6.EE.8)** — a number-line-ray render on the frontend.
- **Multimodal beats** — a post-answer manipulable object (~2d); worked-step reveal / "magic
  moment" on the animated diagram (number line is partial).
- **Smaller** — a dedicated `/parent/household`-with-progress endpoint (remove the per-child N+1);
  a backend notes model for the parent NOTES card (currently fixtures); re-tag the stats
  "describe shape" lesson rather than build a weak widget.

### 2.2 Conversational / interactive tutor (planned)
A more conversational TTS so the guide can interact with the student in real time. This is the
V2 "Wave 5" arc and is **gated on a kids-safety guardrail layer (Wave 1.1)** that must front all
child-facing LLM output first. Pieces: tutor-brain chat, open-ended explanation interpretation,
adaptive worked-example/hint chains, handwriting/photo OCR in-conversation. None started.

### 2.3 Avatars (planned, gated)
3D avatar path is built as an isolated, default-off spike. It ships only after a **30 fps low-end
Chromebook acceptance test**; if that fails, stay 2D. Optional Rhubarb acoustic lip-sync upgrade.

### 2.4 Full Spanish (partial → planned)
Today: help text only (~16% of user-facing strings, captions-only). Remaining: i18n UI chrome
(react-i18next), problem-statement translation, Spanish audio for dynamic text, Spanish teacher
dashboard.

### 2.5 Adaptive deepening (not started)
FSRS spaced review · DKT/AKT learner model · misconception-aware bandit · engagement-signal
capture · HelpNeed v2 on real-student data (blocked on a data license).

---

## 3. Known issues / fix backlog

A whole-application code review (2026-06-08) found the following. **The eight load-bearing ones are
fixed** (each test-first; HelpNeed AUC held at 0.900):

| Status | Issue |
|---|---|
| ✅ Fixed | Mastery floor could be padded by disengaged clicks → now counts only engaged attempts |
| ✅ Fixed | Live transfer probe rendered "1/4 + 1/4 = 1/4" → now the unreduced "= 2/8" |
| ✅ Fixed | Hint counter not reset after a probe → reset at the single serve chokepoint |
| ✅ Fixed | Hint during a probe hinted the paused problem → no scaffold on the unaided gate |
| ✅ Fixed | Corrupt TTS timings sidecar could raise into a turn → guarded (re-render) |
| ✅ Fixed | Camera confirm could double-submit → routed through the guarded submit path |
| ✅ Fixed | HelpNeed `recent_hint_rate` train/serve skew → binary on both sides, model re-fit |
| ✅ Fixed | COPPA consent gate not enforced → child can't go live (login or start-session) until the parent's email is verified |

**Open (lower severity / awaiting a decision):**
- Mastery rep-diversity rule 2 can be satisfied by a *hinted* correct (S5 probe is the backstop) —
  design judgment call.
- `verify()` crashes on three common-denominator *bank* items (latent — the bank isn't wired to
  serving yet).
- Cross-role Google-`sub` reuse can leave a parent row stuck `email_verified=False`.
- In-memory session store has no eviction (slow growth) and concurrent same-session submits aren't
  locked — *fine for a single-instance demo; production-harden?*
- `parse_edmcup` can emit a negative latency on a duplicate `problem_started` (training-data only).
- A few stale docstrings (`InequalityInput`/`CoordinatePlane` "not yet routed"; a `repositories.py`
  index name).

---

## 4. Owner decisions / external blockers

These need **you** (or an ops/legal step), not code:
- **AWS SES sender verification** (auth emails are currently logged, not sent — and the COPPA gate
  now blocks a child from going live until the parent clicks that email, so verifying the SES
  sender is what makes email/password signups usable in production).
- **Conversational tutor** — STT + stored chat transcripts are biometric-adjacent (COPPA);
  approve before building (gates Wave 5).
- **30 fps Chromebook test** for the 3D avatar; **ElevenLabs live-synth cost** sign-off.
- **EDM Cup / ASSISTments commercial-license** sign-off (HelpNeed training data).
- **AWS WAF** rate rule on auth paths; codify the **$50/mo CDK BudgetStack** (currently CLI-only).
- Record the 2D→3D avatar switch in the internal decision log.

---

## 5. Where the detail lives

Deep design rationale, the decision log, research citations, and the slice-by-slice trackers are
**internal planning docs kept local to the team** (`mdfile/`, gitignored — see `CLAUDE.md §1`).
This roadmap and the tracked docs (`README`, `ARCHITECTURE`, `AUTH`, `CLAUDE`) are the
reviewer-visible surface and are kept in sync with the code.
