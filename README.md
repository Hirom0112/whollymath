<div align="center">

# WhollyMath

### An adaptive, multimodal Grade-6 math tutor — with a mastery model you can actually trust.

[![Live](https://img.shields.io/badge/live-whollymath.app-2EA043?logo=amazonaws&logoColor=white)](https://whollymath.app)
![Status](https://img.shields.io/badge/status-deployed-2EA043)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-20232A?logo=react&logoColor=61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![SymPy](https://img.shields.io/badge/SymPy-3B5526?logo=sympy&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-EB5E28)
![AWS](https://img.shields.io/badge/AWS_CDK-232F3E?logo=amazonaws&logoColor=white)

**▶ Live demo: [whollymath.app](https://whollymath.app)**

</div>

---

## Why this exists

**Fractions are the single best-replicated predictor of later algebra success — more than
whole-number knowledge.** The ability to place a fraction on a number line is tied to
understanding the equal sign, variables, and equations. It's the gateway skill — so it's the
spine WhollyMath is built around, inside a **full Grade-6 curriculum**.

And yet the AI learning tools most students touch today fall into two shapes:

- **a chat box** — "ask me anything," with no idea whether you actually understood the answer, and
- **a static worked-example walkthrough** — the same five steps for everyone, no adaptation, no
  check that step 2 landed before showing step 3.

Neither can tell the difference between a learner who *understands* and one who is guessing,
pattern-matching a single format, or leaning on hints. **WhollyMath is built to tell the
difference — and to prove it.**

---

## What this is

A web tutor covering the **full Grade-6 mathematics curriculum** — ratios and rates, fractions and
decimals, rational numbers, integer arithmetic, expressions, equations, geometry, statistics, and
personal financial literacy — for 6th–7th graders, with **dual CCSS + TEKS coverage**. It's
deployed and live at **[whollymath.app](https://whollymath.app)**.

Under the hood: **43 content-complete knowledge components across 9 units**, each with a problem
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

## How it fits together

```mermaid
flowchart TB
    Learner((Learner))

    subgraph FE["Frontend · React + TypeScript"]
        WS["Math Workspace<br/>FractionBar · NumberLine · SymbolicEditor"]
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

Nine units, **43 playable knowledge components**, aligned to both the Common Core (CCSS) and the
Texas standards (TEKS):

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

> Three U8 financial-literacy lessons (banking, credit, paying for college) ship as honest
> **concept lessons** — no SymPy generator, since they're conceptual rather than computational.

---

## Tech stack

- **Frontend:** React + TypeScript + Vite, with custom SVG components for the math workspace.
- **Backend:** Python + FastAPI, with SymPy for all symbolic math verification.
- **Database:** PostgreSQL via SQLAlchemy.
- **ML:** scikit-learn / XGBoost for the HelpNeed predictor (interpretable, sub-10 ms inference).
- **LLM:** Claude behind a provider abstraction — used only for natural-language surface text.
- **Infra:** AWS via CDK (TypeScript) — CloudFront, ECS Fargate, RDS Postgres; live at
  [whollymath.app](https://whollymath.app).

Full rationale for each choice lives in the team's internal tech-stack doc.

---

## Repository layout

```
whollymath/
├── backend/         # Python + FastAPI: domain model, mastery, policy, helpneed, personas, tutor, eval, teacher, llm
├── frontend/        # React + TypeScript: workspace, surface state machine, pages
├── shared-types/    # TypeScript types generated from Pydantic
├── infrastructure/  # AWS CDK (CloudFront / ALB / Fargate / RDS)
├── ARCHITECTURE.md  # ← the in-depth technical reference (start here after this file)
├── CLAUDE.md        # contribution guidelines, commit conventions, source hierarchy
└── README.md        # you are here
```

> Detailed planning, the decision log, and research citations live in internal docs kept local
> to the team (not in version control). `ARCHITECTURE.md` is the public technical reference.

---

## What's built

The build is **deployed and running** at [whollymath.app](https://whollymath.app). Current state:

- ✅ **Domain model** — 43 KCs across 9 units, SymPy verifiers, misconceptions, validated hints.
- ✅ **Mastery model** — BKT per KC with the anti-gaming augmentation rules (representation
  diversity, unscaffolded attempts, interleaving), gated by an S5 transfer probe.
- ✅ **Five adversarial personas** + behavioral simulator — the integration suite.
- ✅ **HelpNeed predictor** — XGBoost trained on EDM Cup data, integrated **observe-only**.
- ✅ **Adaptive UI** — five surface states with labeled, rule-driven transitions and refuse-rules.
- ✅ **Evaluation harness** — three-arm comparison (adaptive vs. chat-only vs. static) + a
  proactive-intervention A/B.
- ✅ **Teacher portal** — class roster and per-student progress views.
- ✅ **AWS deployment** — CloudFront → ALB → Fargate → RDS, via CDK.

**Tests:** backend **2,789 passing** (9 skipped); frontend **187 passing**; production build green.

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
without `MATHPIX_APP_KEY` the homework scanner uses a deterministic mock, and without
`GOOGLE_CLIENT_ID` accounts are off and the anonymous session flow is used.

**macOS prerequisite for the HelpNeed predictor:** XGBoost needs the OpenMP runtime.
Install it once with `brew install libomp` (Linux/CI wheels bundle it). To retrain the
HelpNeed v1 model on local EDM Cup data (gitignored under `backend/data/`):

```bash
cd backend && uv run python -m app.helpneed.train_pipeline
# optional fast pass: WHOLLYMATH_EDMCUP_ROW_LIMIT=5000000 uv run python -m app.helpneed.train_pipeline
```

### The committed HelpNeed model artifact

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
~322k examples from the first 5M action rows; holdout AUC 0.899). The earlier 0.893/~95.8k
figure was the fraction-only predecessor — the skill filter was since widened to the full
cross-topic Grade-6 KC set, and a "quiet mis-reasoning" feature (wrong without seeking a
hint) was added, lifting the artifact to 0.899 with 34 proactive-eligible (per-KC AUC ≥ 0.85)
KCs:

```bash
cd backend && WHOLLYMATH_EDMCUP_ROW_LIMIT=5000000 \
  WHOLLYMATH_HELPNEED_OUT=app/helpneed/artifacts/helpneed_v1.joblib \
  uv run python -m app.helpneed.train_pipeline
```

The predictor scores each answered turn **observe-only** — the API returns it as
`help_need`, but interventions are gated on the A/B result rather than assumed.

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
