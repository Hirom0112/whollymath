<div align="center">

# WhollyMath

### An adaptive Grade-6 math tutor that helps kids learn in English and Spanish — with a mastery model you can actually trust.

[![Live](https://img.shields.io/badge/live-whollymath.app-2EA043?logo=amazonaws&logoColor=white)](https://whollymath.app)
![Status](https://img.shields.io/badge/status-deployed-2EA043)
![Tests](https://img.shields.io/badge/tests-3%2C474_passing-2EA043)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![SymPy](https://img.shields.io/badge/SymPy-3B5526?logo=sympy&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-EB5E28)
![AWS](https://img.shields.io/badge/AWS_CDK-232F3E?logo=amazonaws&logoColor=white)

<a href="https://whollymath.app"><img src="docs/screenshots/landing.png" width="820" alt="WhollyMath — Math, made whole" /></a>

### ▶ [Try the live demo &nbsp;→](https://whollymath.app)

</div>

---

## Contents

[What this is](#what-this-is) · [See it in action](#see-it-in-action) · [How it fits together](#how-it-fits-together) · [The five adversarial learners](#the-five-adversarial-learners) · [Curriculum coverage](#curriculum-coverage) · [Tech stack](#tech-stack) · [Status — done · in progress · next](#status--done--in-progress--next) · [Running it](#running-it) · [Repository layout](#repository-layout) · [How this project is built](#how-this-project-is-built) · [Grounded in research](#grounded-in-research)

---

## What this is

A web tutor covering the **full Grade-6 mathematics curriculum** — ratios and rates, fractions and
decimals, rational numbers, integer arithmetic, expressions, equations, geometry, statistics, and
personal financial literacy — for 6th–7th graders, with **dual CCSS + TEKS coverage**. It's
deployed and live at **[whollymath.app](https://whollymath.app)**.

Under the hood: **44 engine-served knowledge components across 9 units**, each with a problem
generator, a SymPy verifier path, documented misconceptions, validated hints, and a lesson spec.
Five things set it apart from the tutors most students use:

| | Feature | What makes it different |
|---|---|---|
| 🎛️ | **An interface that adapts with restraint** | Five disciplined surface states (symbolic, number line, fraction bars, worked example, transfer probe) — never a chaotic morphing UI. Every transition is labeled and rule-driven. |
| 🧮 | **A mastery model that resists gaming** | "Mastered" requires correctness across ≥2 representations, at least one unassisted attempt, and *interleaved* (not blocked) practice. Guessing and hint-hunting don't get you there. |
| ✅ | **Symbolic verification, not LLM guesswork** | Every answer and step is checked by **SymPy**. A language model never decides whether your math is right. |
| 🧪 | **Five adversarial synthetic learners** | Each persona deterministically instantiates a documented misconception and tries to fool the mastery model. They are the integration test suite. |
| 📊 | **An honest evaluation** | Measured against a chat-only baseline and a static worked-example baseline, with a **transfer test** as the moment of truth — and results reported regardless of which wins. |

---

## See it in action

*Real screenshots from the live deployment at [whollymath.app](https://whollymath.app).*

<table>
<tr>
<td width="50%"><img src="docs/screenshots/hint.png" alt="The workspace mid-help: a problem-specific spoken hint with an English/Spanish toggle"/></td>
<td width="50%"><img src="docs/screenshots/units.png" alt="The Grade-6 unit map, gated unit by unit"/></td>
</tr>
<tr>
<td><b>The workspace, mid-help.</b> A <i>problem-specific</i> hint — never the answer — voiced by the mascot, with a one-tap English/Spanish help toggle. SymPy has already decided correctness; the LLM only phrases the nudge.</td>
<td><b>Nine units, gated.</b> The full Grade-6 standard (ratios → fractions → rational numbers → expressions → equations → geometry → statistics → financial literacy). Finishing a unit unlocks the next.</td>
</tr>
<tr>
<td><img src="docs/screenshots/spanish.png" alt="A unit-rate lesson with the help language flipped to Spanish: the problem stays in English while the hint is in Spanish"/></td>
<td><img src="docs/screenshots/teacher.png" alt="The teacher class dashboard with student triage"/></td>
</tr>
<tr>
<td><b>Help in Spanish, on tap.</b> Flip the bottom-left toggle and the hints, nudges, and the mascot's voice switch to Spanish (es-MX) — the problem stays English while the help meets the learner in their language. <i>(Problem-statement translation is on the roadmap.)</i></td>
<td><b>Teacher triage.</b> The roster ranks into <i>Struggling / Needs attention / On track</i>, surfaces the highest-priority student to check in with, and rolls up an aggregate skill-gap view. <i>(Shown on the synthetic demo class — no real student data.)</i></td>
</tr>
</table>

---

## How it fits together

```mermaid
flowchart TB
    Learner((Learner))

    subgraph FE["Frontend · React + TypeScript"]
        WS["Math Workspace<br/>FractionArea · NumberLine · SymbolicEditor · …"]
        SM["Surface State Machine · S1–S5"]
    end

    subgraph BE["Backend · Python + FastAPI"]
        VER["SymPy Verifier<br/><i>all math correctness</i>"]
        MAS["Mastery Model<br/>BKT + anti-gaming rules"]
        POL["Adaptation Policy<br/>transitions + refuse-rules"]
        HN["HelpNeed Predictor<br/>XGBoost · sub-100 ms"]
        LLMS["LLM Surface<br/><i>hints / explanations only</i>"]
    end

    DB[("PostgreSQL")]

    Learner --> WS --> VER --> MAS --> POL --> SM --> Learner
    WS --> HN --> POL
    POL -. "after the math is settled" .-> LLMS --> WS
    MAS --> DB
```

> **The core invariant:** *rules decide what happened; the LLM only describes what it looks
> like.* Correctness, mastery, and state transitions are all deterministic. The LLM is additive
> — disable it and the system still works, it just talks less naturally.

📐 **Full technical map:** [`ARCHITECTURE.md`](./ARCHITECTURE.md) — every layer, the turn loop,
the state machine, the personas, and the evaluation design, with diagrams.

---

## The five adversarial learners

The mastery model is only as trustworthy as the attacks it survives. Each persona forces a
specific design rule:

| Persona | Tries to pass by… | Forces the rule… |
|---|---|---|
| **Natural-number Nate** | Surface symbolic matching, while believing ⅙ > ½ | Mastery needs ≥2 representations |
| **Procedure Priya** | Running the algorithm without understanding it | Every KC needs an "explain / find-the-error" item |
| **Hint-hunter Hugo** | Treating hints as the instruction | Mastery needs an unassisted correct attempt |
| **Surface Sam** | Looking fluent inside one problem format | Mastery is computed on interleaved practice |
| **Click-through Cleo** | Clicking fast without engaging | Engagement-floor signals flag low-effort answers |

---

## Curriculum coverage

Nine units, **44 playable knowledge components**, with **dual CCSS + TEKS coverage where both
apply** — integer arithmetic (U-INT) and personal financial literacy (U8) are **TEKS-only**, with
no CCSS Grade-6 home:

| Unit | Focus | Standards |
|---|---|---|
| **U1** | Ratios, rates, percent, unit conversion | 6.RP · TEKS 6.4/6.5 |
| **U2** | Fractions & decimals (incl. ×, ÷, GCF/LCM) | 6.NS.1–4 · TEKS 6.3 |
| **U3** | Rational numbers, number line, coordinate plane, number-set classification | 6.NS.5–8 · TEKS 6.2 |
| **U-INT** | Integer arithmetic (TEKS-driven; CCSS Grade 7) | TEKS 6.3C/6.3D |
| **U4** | Expressions — write, evaluate, parts, exponents, dependent variables | 6.EE.1–4/9 |
| **U5** | One-step equations & inequalities | 6.EE.5–9 |
| **U6** | Geometry — area, triangles, nets/surface area, volume, coordinate polygons | 6.G · TEKS 6.8 |
| **U7** | Statistics — questions, summary stats, spread/shape, displays, MAD, categorical data | 6.SP · TEKS 6.12 |
| **U8** | Personal financial literacy (check register, lifetime income) | TEKS 6.14 |

> Four U8 financial-literacy lessons (three concept KCs — banking, credit, paying for college;
> banking spans two lessons) ship as honest **concept lessons** — no SymPy generator, since
> they're conceptual rather than computational.

---

## Tech stack

- **Frontend:** React + TypeScript + Vite, with custom SVG components for the math workspace.
- **Backend:** Python + FastAPI, with SymPy for all symbolic math verification.
- **Database:** PostgreSQL via SQLAlchemy (Alembic migrations).
- **ML:** scikit-learn / XGBoost for the HelpNeed predictor (interpretable via SHAP, fast CPU
  inference, no GPU).
- **Auth:** parent/child accounts — Argon2id hashing, revocable HS256 session JWTs, Google OIDC
  verify (see [`AUTH.md`](./AUTH.md)).
- **LLM & voice:** Claude behind a provider abstraction (surface text only); ElevenLabs for V2
  voice — both off the graded turn loop.
- **Infra:** AWS via CDK (TypeScript) — CloudFront, ECS Fargate, RDS Postgres; live at
  [whollymath.app](https://whollymath.app).

Full rationale for each choice lives in the team's internal tech-stack doc.

---

## Status — done · in progress · next

Deployed and running at **[whollymath.app](https://whollymath.app)**. This is an honest snapshot;
the full map with the fix backlog and owner sign-offs lives in [`ROADMAP.md`](./ROADMAP.md).

### ✅ Built and live

- **Adaptive turn loop** — SymPy verify → BKT mastery → policy/refuse-rules → observe-only
  HelpNeed, with **no LLM on the graded path**. Five surface states (S1–S5), labeled transitions,
  an S5 transfer-probe confirm gate.
- **Full Grade-6 curriculum** — 9 units, **44 engine-served KCs**, each with a problem generator,
  SymPy verifier, documented misconceptions, validated hints, and a lesson spec. Dual CCSS + TEKS.
- **Mastery model** — per-KC BKT plus the anti-gaming guardrails (τ=0.90, ≥5 *engaged* attempts,
  ≥2 representations, ≥1 unscaffolded correct, interleaving, engagement floor) — validated by the
  five adversarial personas as the integration suite.
- **HelpNeed predictor** — XGBoost on EDM Cup 2023, **holdout AUC 0.900**, observe-only, with a
  33-KC trustworthy guard.
- **Teacher & parent dashboards** — live data: ranked roster + per-child mastery/HelpNeed signals,
  and a parent progress drill-in.
- **Parent/child auth** — COPPA-aware: parent sign-up (Google or email+password, Argon2id), child
  username+PIN, consent record + data export/delete ([`AUTH.md`](./AUTH.md)).
- **Homework scan** — assign → QR → photo OCR (Mathpix, mock fallback) → read-back → SymPy-graded.
- **Voiced 2D mascot** — ElevenLabs "Hope" voice (pre-rendered bank + content-hash-cached live
  synth, off the turn loop) with phoneme lip-sync, and problem-specific spoken hints.
- **Spanish help-mode** — 176 reviewed help strings, captions-localized (problems stay English for now).
- **Evaluation harness** — three-arm comparison (adaptive vs. chat-only vs. static) + a
  proactive-intervention A/B.
- **AWS deployment** — CloudFront → ALB → Fargate → RDS, via CDK.

### 🚧 In progress

- **Hyperreactive generalization** — making 6 hardcoded KC→representation bindings table-driven
  `LessonSpec` reads, to unlock the full ~54-lesson "the interface is the tutoring" contract.
- **Richer multimodal beats** — geometry net figure-drawing (6.G.4), inequality solution-graph
  (6.EE.8), post-answer manipulables.
- **Fuller Spanish** — i18n UI chrome, problem-statement translation, and Spanish audio (help text
  ships today).

### 🔭 Next / planned

- **Conversational tutor** — real-time spoken dialogue, gated behind a kids-safety guardrail layer
  that must front all child-facing LLM output first (not started).
- **HelpNeed v2** on real-student telemetry (blocked on a data license); FSRS spaced review;
  DKT/AKT learner model.
- **3D avatar** — built as a default-off spike; ships only after a 30 fps low-end-Chromebook test.

> **Needs a human, not code:** AWS SES sender verification (so email/password signups can send the
> COPPA consent email), plus the sign-offs tracked in [`ROADMAP.md`](./ROADMAP.md) §4.

**Quality bar (verified on `main`, 2026-06-09):** backend **3,168 tests passing** (9 skipped),
frontend **306 passing** (52 files); `ruff`, `mypy --strict` (361 files), `tsc`, and the production
`vite build` all clean.

---

## Running it

The fastest way to see it is the live deployment: **[whollymath.app](https://whollymath.app)**.

To run locally:

```bash
# 1. Local Postgres (parity with prod) — teacher features need a real DB
docker compose up -d
export DATABASE_URL=postgresql://whollymath:whollymath@localhost:5432/whollymath

# 2. Backend (Python + FastAPI)
cd backend && uv sync && uv run pytest        # tests-first; see CLAUDE.md §2
uv run uvicorn app.api.app:app --reload       # serves on :8000

# 3. Frontend (React + Vite)
cd frontend && pnpm install && pnpm dev        # serves on :5173, proxies /api → :8000
```

Copy `.env.example` → `.env` and fill in keys as needed. The app runs with sensible fallbacks:
without `ANTHROPIC_API_KEY` the LLM surface is disabled (the deterministic engine still works),
without `MATHPIX_APP_KEY` the homework scanner uses a deterministic mock, without
`ELEVENLABS_API_KEY` voice falls back to captions, and without `GOOGLE_CLIENT_ID` Google sign-in is
off (email/password + child PIN still work). **One key is required for accounts:**
`SESSION_SIGNING_KEY` — the parent/child auth endpoints **fail closed (503)** if it is unset.

**macOS prerequisite for the HelpNeed predictor:** XGBoost needs the OpenMP runtime.
Install it once with `brew install libomp` (Linux/CI wheels bundle it). To retrain the
HelpNeed v1 model on local EDM Cup data (gitignored under `backend/data/`):

```bash
cd backend && uv run python -m app.helpneed.train_pipeline
# optional fast pass: WHOLLYMATH_EDMCUP_ROW_LIMIT=5000000 uv run python -m app.helpneed.train_pipeline
```

<details>
<summary><b>The committed HelpNeed model artifact</b> — how the trained predictor ships in-repo (click to expand)</summary>

<br>

The deployed turn loop needs a *fitted* predictor at boot, but the 1.44 GB EDM Cup
training data is gitignored (too large for git, re-downloadable from source). The
trained XGBoost model, by contrast, serializes to ~280 KB — its size is set by the tree
count/depth, not the row count — so **the one blessed artifact is checked in** at
`backend/app/helpneed/artifacts/helpneed_v1.joblib` and loaded once at boot by
`app.helpneed.artifact.load_predictor` (no network fetch on the boot path; the turn loop
stays sub-100 ms). This overrides the default `*.joblib` ignore via a single negation in
`.gitignore` (decision 2026-05-28). S3/model-registry hosting is the upgrade path if the
model ever grows or needs independent versioning — premature at this size.

Because the data is gitignored, the binary's provenance can't show in a diff, so it lives
in the decision log instead. **Reproduce the committed artifact** (XGBoost, fit on all
~322k examples from the first 5M action rows; holdout AUC 0.900). The earlier 0.893/~95.8k
figure was the fraction-only predecessor — the skill filter was since widened to the full
cross-topic Grade-6 KC set, a "quiet mis-reasoning" feature (wrong without seeking a hint)
was added, and `recent_hint_rate` was corrected to the binary hinted-rate the live path can
compute (fixing a train/serve skew) — the artifact holds **AUC 0.900 with 33 proactive-eligible
(per-KC AUC ≥ 0.85) KCs**:

```bash
cd backend && WHOLLYMATH_EDMCUP_ROW_LIMIT=5000000 \
  WHOLLYMATH_HELPNEED_OUT=app/helpneed/artifacts/helpneed_v1.joblib \
  uv run python -m app.helpneed.train_pipeline
```

The predictor scores each answered turn **observe-only** — the API returns it as
`help_need`, but interventions are gated on the A/B result rather than assumed.

</details>

---

## Repository layout

```
whollymath/
├── backend/         # Python + FastAPI: domain model, mastery, policy, helpneed, personas, tutor, eval, teacher, llm
├── frontend/        # React + TypeScript: workspace, surface state machine, pages
├── shared-types/    # TypeScript types generated from Pydantic
├── infrastructure/  # AWS CDK (CloudFront / ALB / Fargate / RDS)
├── ARCHITECTURE.md  # ← the in-depth technical reference (start here after this file)
├── ROADMAP.md       # what's built / what's left + the fix backlog
├── AUTH.md          # parent/child auth design + security posture
├── CLAUDE.md        # contribution guidelines, commit conventions, source hierarchy
└── README.md        # you are here
```

> Detailed planning, the decision log, and research citations live in internal docs kept local
> to the team (not in version control). `ARCHITECTURE.md` is the public technical reference.

---

## How this project is built

- **The domain model and mastery model are developed test-first** — they are load-bearing, so a
  test asserting the behavior comes before the implementation.
- **Commit messages are the decision log.** Each one cites the source (PRD, design doc, or
  research finding) behind a change.
- **Workflow is trunk-based:** small commits straight to `main`, pushed to both remotes.

See [`CLAUDE.md`](./CLAUDE.md) for the full guidelines.

---

## Grounded in research

Every major design choice traces to a finding, not a hunch. A few that shaped the system:

- **Fractions predict algebra readiness** more than whole-number knowledge (Bailey et al. 2012;
  Booth & Newton 2012) → chose the spine.
- **Interleaved practice beats blocked practice** for transfer in 7th-grade fraction arithmetic
  (Rohrer et al. 2014, 2015) → the mastery model scores interleaved practice, not blocks.
- **LLM step-level math verification is an open problem** (Daheim et al. 2024) → SymPy owns all
  correctness checking.
- **Students who most need help are least likely to ask** (Maniktala et al. 2020) → inline,
  proactive help instead of hidden hint buttons.
- **Proactive help can underperform reactive help** (Razzaq & Heffernan 2010) → we A/B test it
  rather than assume it wins.
</content>
</invoke>
