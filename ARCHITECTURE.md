# Architecture

> The technical reference for WhollyMath — an adaptive, multimodal tutor for fraction
> equivalence and operations. This document is the canonical, in-repo explanation of *how*
> the system is built and *why* it is built that way. Deeper design rationale, the decision
> log, and research citations live in the team's internal planning docs (local-only); this
> file is the public, follow-along technical map.

**Audience:** anyone reading the repo for the first time — a new contributor, a reviewer, or
future us. If you read this top to bottom, you will understand every major moving part and
the invariants that hold them together.

---

## Table of contents

1. [The one-paragraph version](#1-the-one-paragraph-version)
2. [Design philosophy](#2-design-philosophy)
3. [System overview](#3-system-overview)
4. [The learning domain (what we teach)](#4-the-learning-domain-what-we-teach)
5. [Layer-by-layer: the synthetic-learner harness](#5-layer-by-layer-the-synthetic-learner-harness)
6. [The mastery model](#6-the-mastery-model)
7. [The adaptive UI: surface states & policy](#7-the-adaptive-ui-surface-states--policy)
8. [The proactive HelpNeed layer](#8-the-proactive-helpneed-layer)
9. [Content validation](#9-content-validation)
10. [The turn loop (request lifecycle)](#10-the-turn-loop-request-lifecycle)
11. [Evaluation architecture](#11-evaluation-architecture)
12. [Technology choices](#12-technology-choices)
13. [Repository layout](#13-repository-layout)
14. [Architectural invariants (never break these)](#14-architectural-invariants-never-break-these)
15. [The persistent learner: identity, continuity & behavioral capture](#15-the-persistent-learner-identity-continuity--behavioral-capture)

---

## 1. The one-paragraph version

WhollyMath is a web tutor that teaches **fraction equivalence, addition, and subtraction** to
6th–7th graders. It adapts its interface to what the learner *demonstrably* understands using
a small, disciplined set of surface states, and it declares "mastery" only through a model
that is explicitly defended against guessing, pattern-matching, and over-reliance on hints.
All math correctness is decided by **symbolic computation (SymPy)** — never by a language
model. The whole system is stress-tested by **five adversarial synthetic learners**, each one
a deterministic instantiation of a documented fraction misconception, and it is measured
honestly against a chat-only baseline and a static worked-example baseline, with a **transfer
test** as the moment of truth.

---

## 2. Design philosophy

Three principles shape every decision below.

- **Rules decide what happened; the LLM only describes what it looks like.** Every correctness
  judgment, mastery update, and state transition is deterministic. The LLM is confined to
  generating natural language *after* the deterministic logic has run. The system must be able
  to run with all LLM features disabled and lose only surface fluency — never evidence.
- **Mastery must be earned, not gamed.** A learner who guesses, pattern-matches a single
  representation, or leans on scaffolding does not reach "mastered." The mastery model encodes
  this directly, and the synthetic personas exist to attack it.
- **Adapt with restraint.** A UI that constantly morphs is a worse result than one that holds
  still. There are exactly five surface states, transitions are always labeled, and a set of
  hard refuse-rules constrain what the interface will *never* do automatically.

---

## 3. System overview

WhollyMath instantiates the classic four-component intelligent-tutoring-system loop — a
**domain model** of expert knowledge, a **student model** tracking mastery, a **pedagogical
model** choosing the next move, and an **interface** delivering problems and feedback.

```mermaid
flowchart TB
    Learner((Learner))

    subgraph FE["Frontend · React + TypeScript + Vite"]
        WS["Math Workspace<br/>SVG: FractionBar · NumberLine · SymbolicEditor"]
        SM["Surface State Machine<br/>S1 – S5"]
    end

    subgraph BE["Backend · Python + FastAPI"]
        API["Turn Loop / API"]
        VER["SymPy Verifier<br/><i>all math correctness</i>"]
        MAS["Mastery Model<br/>BKT per KC + augmentation rules"]
        POL["Adaptation Policy<br/>transitions + refuse-rules"]
        HN["HelpNeed Predictor<br/>XGBoost · sub-100 ms"]
        LLMS["LLM Surface Layer<br/><i>hints / explanations — off the critical path</i>"]
    end

    DB[("PostgreSQL<br/>sessions · mastery · persona runs")]

    Learner --> WS
    WS <--> API
    SM <--> API
    API --> VER --> MAS --> POL --> SM
    API --> HN --> POL
    POL -. "after deterministic logic" .-> LLMS --> WS
    MAS --> DB
    API --> DB
```

The **synthetic-learner harness** and **evaluation pipeline** (Sections 5 and 11) sit beside
this loop: they drive personas through the same tutor to measure whether the mastery model can
be fooled, and to compare the adaptive UI against baselines.

---

## 4. The learning domain (what we teach)

A single, tightly scoped goal: *the learner can reason about whether two fractions are
equivalent, can add and subtract fractions with unlike denominators, and can resist the
natural-number-bias trap (believing ⅙ > ½ because 6 > 2).* Positive fractions only;
no multiplication or division.

The goal decomposes into **five knowledge components (KCs)** — the unit of mastery. "Mastered
fractions" is meaningless; "mastered KC3" is trackable.

| KC  | Skill |
|-----|-------|
| KC1 | Identify equivalent fractions |
| KC2 | Find a common denominator |
| KC3 | Add with a common denominator |
| KC4 | Subtract with a common denominator |
| KC5 | Place a fraction correctly on a number line |

Each KC carries its canonical correct procedure, its named misconceptions, and the
wrong-answer patterns those misconceptions produce. This is **Layer 1** of the harness and the
single source of truth that the mastery model, the personas, and the transfer test all
reference.

---

## 5. Layer-by-layer: the synthetic-learner harness

The harness is how we answer "how do you know your synthetic learners aren't just LLMs in
costume?" The answer is the architecture: four layers with strict separation.

```mermaid
flowchart LR
    L1["<b>Layer 1 · Domain Model</b><br/>deterministic, no LLM<br/>KCs · misconceptions<br/>generators · SymPy verifier"]
    L2["<b>Layer 2 · Persona Config</b><br/>data, not code<br/>which KCs, in which mode<br/>+ behavioral params"]
    L3["<b>Layer 3 · Behavioral Simulator</b><br/>deterministic code, no LLM<br/>given persona + problem ⇒ action"]
    L4["<b>Layer 4 · NL Surface</b><br/>LLM · additive · optional<br/>renders the action as text"]
    EV["Evaluation evidence<br/><i>intact even with Layer 4 off</i>"]

    L1 --> L3
    L2 --> L3
    L3 -- "computed action" --> L4
    L3 -- "answers · hints · timings" --> EV
```

- **Layer 1 — Domain Model** (deterministic): the KCs, correct procedures, and misconception
  wrong-answer patterns. No LLM.
- **Layer 2 — Persona Config** (data): each persona is a config — which KCs they hold and in
  what mode (procedure-only / concept-only / both / neither / with-named-misconception), plus
  behavioral parameters (response latency, hint-request probability, engagement floor,
  scaffold-dependence). Adding a sixth persona is editing a config, not writing code.
- **Layer 3 — Behavioral Simulator** (deterministic code): given a persona config and a problem,
  it computes the action — what answer is submitted, whether a hint is requested, how long the
  persona "thinks," what it types when asked to explain. Same input always yields the same
  output. This is what makes the harness reproducible.
- **Layer 4 — Natural-Language Surface** (LLM, additive): the *only* place an LLM enters the
  persona system. It renders the already-computed action as chat text. **It never sees the
  persona's knowledge state** — only what the persona is about to type.

**The five personas** each attack a specific weakness and force a specific mastery rule:

| Persona | Misconception / failure | Signature behavior | Forces |
|---|---|---|---|
| **Natural-number Nate** | Natural-number bias | Fast, confident; right on surface symbolic, wrong on magnitude | Mastery across ≥2 representations |
| **Procedure Priya** | "The procedure is the math" | Correct symbolic answers; can't explain why; fails error-finding | An "explain / find-the-error" item per KC |
| **Hint-hunter Hugo** | Treats hints as the instruction | Requests hints before attempting; collapses without them | ≥1 unassisted correct attempt |
| **Surface Sam** | "Operations are tied to formats" | Near-100% inside a format block; drops on format change | Mastery on **interleaved**, not blocked, practice |
| **Click-through Cleo** | Disengagement (not knowledge) | Sub-2s answers, picks first option, skips prompts | Engagement-floor signals in the mastery model |

The personas are the **integration tests** for the mastery model (Section 6). If a persona who
*should not* reach mastery does, the model is broken.

---

## 6. The mastery model

A **per-KC Bayesian Knowledge Tracing (BKT)** model: each KC has a mastery probability that
updates after each observation. But a probability over a threshold is not enough — that is
exactly how guessing and pattern-matching slip through. Mastery on a KC is declared **only when
all of the following hold**:

1. **BKT probability > τ** (initial τ = 0.85, tuned against persona results).
2. **Correctness across ≥ 2 representations** of the same KC (e.g., symbolic *and* number line).
   — defeats *Natural-number Nate*.
3. **≥ 1 correct attempt with no scaffolding** (no hint, no UI assistance). Hinted attempts are
   downweighted. — defeats *Hint-hunter Hugo*.
4. **Computed on interleaved practice, not blocked.** A run of correct answers from one KC in a
   row counts for less than correct answers interleaved across KCs. — defeats *Surface Sam*;
   grounded in the most-replicated finding in math-practice scheduling research.

Plus an **engagement floor**: responses below a time-to-answer floor are flagged, and repeated
low-engagement responses trigger a re-engagement prompt rather than counting as evidence. —
defeats *Click-through Cleo*.

Mastery is then **provisional until the transfer probe (S5) is passed**. A failed transfer
probe demotes the learner back to scaffolded practice for that KC.

---

## 7. The adaptive UI: surface states & policy

Five surface states — a small, enumerated set, each with a defensible reason to exist.

| State | What it is | When it is used |
|---|---|---|
| **S1 · Symbolic Focus** | Numerator/denominator primary; small number line for orientation | Default fluent state |
| **S2 · Number Line Primary** | Number line is the main workspace | After magnitude errors |
| **S3 · Fraction Bars Primary** | Manipulable area-model bars, with live symbolic correspondence | After operation/format errors |
| **S4 · Worked Example + Prompts** | A solved problem revealed step-by-step, each with a "why?" prompt | After the learner is stuck (used sparingly) |
| **S5 · Transfer Probe** | Stripped-down, different representation than recent work, no scaffolds | When the mastery model says ready — this *is* the transfer test |

```mermaid
stateDiagram-v2
    [*] --> S1
    state "S1 · Symbolic Focus" as S1
    state "S2 · Number Line Primary" as S2
    state "S3 · Fraction Bars Primary" as S3
    state "S4 · Worked Example + Prompts" as S4
    state "S5 · Transfer Probe" as S5

    S1 --> S2 : magnitude error
    S1 --> S3 : operation / format error
    S2 --> S3 : operation / format error
    S2 --> S1 : 2 correct, no hints
    S3 --> S1 : 2 correct, no hints
    S4 --> S1 : 2 correct, no hints
    S1 --> S4 : 2+ consecutive errors
    S2 --> S4 : 2+ consecutive errors
    S3 --> S4 : 2+ consecutive errors
    S1 --> S5 : interleaved set passed
    S5 --> S2 : transfer fail (magnitude KC)
    S5 --> S3 : transfer fail (operation KC)
    S5 --> [*] : mastery confirmed
```

> Note: a BKT threshold crossing does **not** jump straight to S5. It first triggers a mandatory
> interleaved-practice set (≥ 3 items across recent KCs); only when that set is passed does the
> learner reach S5. This is the rule that turns block-fluency into real mastery evidence.

**Refuse-rules — what the UI will never do automatically:**

1. Never change state mid-problem (transitions happen *between* problems).
2. Never silently remove the learner's own work (prior work is preserved in a panel).
3. Never change state because the learner paused.
4. Never present a new state without a one-line label explaining why.
5. Never auto-help in the first 60 seconds of a problem (except on a wrong answer or explicit
   hint request) — protects productive struggle.
6. When help *is* shown, render it **inline in the workspace**, not as a separate dialog.

---

## 8. The proactive HelpNeed layer

Beyond reactive transitions, a predictor estimates — at every turn — the probability that the
learner is in an unproductive state, so help can arrive *before* it is asked for (students who
most need help are least likely to ask).

- **Model:** XGBoost classifier (interpretable via SHAP, sub-10 ms inference, no GPU). Trained
  on CMU DataShop public fraction-tutor traces.
- **Features (all real-time available):** response latency on current and recent problems, error
  pattern on the current problem, hint requests in the last N problems, time since last correct
  answer, BKT mastery probabilities, recent state transitions.
- **Output:** a HelpNeed probability per turn, with a confidence interval.
- **Intervention escalation** when the probability crosses threshold:
  1. **Inline assertion** — a partial worked step appears in the workspace, in the same format
     as student-derived steps.
  2. **Conceptual prompt** (if no response in ~30 s) — a question that forces the learner to
     articulate a concept, without revealing the answer.
- **Calibration:** after training, the predictor is calibrated against the synthetic personas to
  adjust for the fact that the training traces come from different tutors.

The evidence on proactive vs. reactive help is genuinely mixed, so the proactive layer is **A/B
tested** against reactive-only and the result is reported honestly regardless of which wins
(Section 11).

---

## 9. Content validation

Math correctness is **never** an LLM's job. Step-level math verification by LLMs is a documented
open problem, so:

- **All answer-checking and step-validity** is done by **SymPy** (symbolic computation). It is
  the only thing that decides "is this correct?"
- **Hints and explanations** are generated by the LLM but rendered through **constrained
  templates**; any symbolic content in a hint is itself validated by SymPy before display.
- **Motivational / non-math copy** may be free-form LLM, passed through a safety filter.

If you ever find yourself writing a prompt like "is this fraction equivalent to that fraction?"
— stop. That is SymPy's job.

---

## 10. The turn loop (request lifecycle)

A single learner action flows through the system like this:

```mermaid
sequenceDiagram
    autonumber
    participant L as Learner
    participant UI as Surface (S1–S5)
    participant API as Turn Loop
    participant V as SymPy Verifier
    participant M as Mastery (BKT + rules)
    participant H as HelpNeed (XGBoost)
    participant P as Policy
    participant LLM as LLM Surface

    L->>UI: action (drag / type)
    UI->>API: submit
    API->>V: verify (symbolic)
    V-->>API: correct? + error type
    API->>M: update BKT for affected KC(s)
    API->>H: predict HelpNeed (feature vector)
    API->>P: choose next state / intervention
    P-->>API: transition + optional help
    opt natural language needed
        API->>LLM: render hint/explanation (validated template)
        LLM-->>API: text
    end
    API-->>UI: next state + labeled feedback
    Note over API,P: the deterministic path (verify → mastery → policy)<br/>stays sub-100 ms; the LLM never gates a turn
```

The latency budget is the reason the LLM, the BKT update, and the HelpNeed prediction are kept
off any blocking critical path that requires a network round-trip to a model provider.

---

## 11. Evaluation architecture

Three arms, the same five personas, the same 50 problems each:

```mermaid
flowchart LR
    P["5 personas × 50 problems"]
    A1["Arm 1 · Adaptive UI<br/>(this system)"]
    A2["Arm 2 · Chat baseline<br/>(LLM in a chat box)"]
    A3["Arm 3 · Static baseline<br/>(pre-rendered walkthrough)"]
    R["Metrics + transfer outcomes"]
    P --> A1 --> R
    P --> A2 --> R
    P --> A3 --> R
```

**Measured per persona, per arm:**

- False-positive mastery rate (the headline number)
- Hint dependence at mastery threshold
- Procedural-vs-conceptual gap
- Format-variance robustness
- Engagement-floor enforcement
- Transfer-test pass rate at the moment of mastery declaration

A separate **A/B test** runs the personas under (a) reactive-only vs. (b) reactive + proactive
HelpNeed. Before any run, expected scores are **pre-registered**; comparing predictions to
actuals is itself part of the evidence.

---

## 12. Technology choices

| Layer | Choice | Why (short version) |
|---|---|---|
| Frontend | **React + TypeScript + Vite** | Rich typed state; fast dev loop; custom SVG workspace |
| Math workspace | **Custom SVG components** | Exact control over direct-manipulation manipulatives; screen-reader-friendlier than canvas |
| Backend | **Python + FastAPI** | Native home for SymPy and the ML pipeline; async turn loop; Pydantic ↔ TS types |
| Math verification | **SymPy** | Symbolic correctness without trusting an LLM |
| Database | **PostgreSQL + SQLAlchemy** | Structured relational data (learners, sessions, turns, KCs, mastery) |
| ML | **scikit-learn / XGBoost** | Interpretable (SHAP), fast inference, no GPU |
| LLM | **Claude** (Opus for hard generation, Sonnet/Haiku for cheap surface calls) behind a provider abstraction | Strong constrained instruction-following; swappable |
| Deploy | **AWS via CDK (TypeScript)** — S3 + CloudFront, ECS Fargate, RDS | Reproducible IaC; single always-on container avoids demo cold-starts |
| Auth / identity | **Google Sign-In (OAuth 2.0 / OIDC)** — backend verifies Google ID tokens; no passwords stored | Delegating to Google is safer than rolling our own (no credential storage, MFA + recovery handled); Workspace-for-Education accounts anchor the under-13 consent story |
| Behavioral capture | **Append-only `interaction_event` (Postgres JSONB) + async `/events` ingest** | Full raw interaction stream (keystrokes, drags, dwell) off the turn loop; derived offline into HelpNeed-v2 features |
| LLM tracing | **LangSmith** (wraps the `llm/` provider) | Per-call cost/latency/prompt observability at the one provider seam; tracing-only, no LangChain adoption |

Type contracts are generated from the backend Pydantic schemas into TypeScript, so the API
shape is enforced on both sides from one source of truth.

---

## 13. Repository layout

```
backend/
  app/
    domain/           # Layer 1: KCs, misconceptions, problem generators, SymPy verifiers
    personas/         # Layers 2 + 3: configs and the behavioral simulator
    persona_surface/  # Layer 4: LLM-mediated natural language
    mastery/          # BKT model + the augmentation rules
    policy/           # State transitions, refuse-rules, interleaving logic
    helpneed/         # HelpNeed predictor: training + inference
    tutor/            # Session loop, problem presentation
    auth/             # Google OIDC token verification + current-learner resolution
    events/           # Behavioral-event schema + async ingestion service (telemetry)
    api/              # FastAPI routes (thin; call services)
    db/               # SQLAlchemy models + migrations + repositories
    llm/              # Provider abstraction (the ONLY place LLMs are called)
  tests/              # Mirrors app/

frontend/
  src/
    components/       # React components (+ Storybook stories)
    workspace/        # Custom SVG: FractionBar, NumberLine, SymbolicEditor
    state/            # State machines for surface transitions
    telemetry/        # Raw-interaction instrumentation: buffers + flushes to /events
    auth/             # Google Sign-In button + ID-token handling
    api/              # API client (generated from Pydantic types)
    pages/            # Top-level routes

shared-types/         # Generated TypeScript types from Pydantic
infrastructure/       # AWS CDK
```

The directory names are load-bearing: see the boundaries in Section 14.

---

## 14. Architectural invariants (never break these)

These are the rules that keep the system honest and fast. Breaking one is a bug, not a choice.

1. **No LLM in the latency-critical turn loop.** The HelpNeed predictor, the mastery update, and
   SymPy verification never call an LLM.
2. **The LLM never decides math correctness.** SymPy does. Always.
3. **The LLM never sees a persona's knowledge state.** If rendered text betrays understanding the
   persona shouldn't have, that's an architecture bug — fix the architecture, not the prompt.
4. **The harness runs deterministically with Layer 4 disabled** and loses only chat-naturalness;
   all evaluation evidence remains intact.
5. **SymPy lives only in `domain/`. LLM calls live only in `llm/`.** Business logic stays out of
   route handlers; DB queries stay in repositories.
6. **The UI obeys the refuse-rules** (Section 7): no mid-problem state change, no silent removal
   of learner work, always-labeled transitions, no auto-help in the first 60 seconds.
7. **Telemetry and persistence never block a turn.** Behavioral event capture and
   session/mastery writes happen alongside or after the response, never on the sub-100 ms
   decision path. The `/events` stream is fire-and-forget; a lost or slow event must never
   break, delay, or change a turn's outcome.
8. **Identity is verified at the boundary and never reaches the reasoning core.** Google ID
   tokens are verified in `auth/` and resolved to a learner in the API layer; identity does
   not flow into the mastery model, the policy, or the LLM (extends invariant 3 — the system
   reasons over *knowledge state*, not over *who* the learner is).
9. **Capture richly, act conservatively.** The full behavioral stream exists to improve
   *understanding* (HelpNeed, mastery, evaluation). It does not widen what the UI does
   automatically: interventions remain governed by the refuse-rules and the sustained-signal
   gate (Section 8). "Hyperresponsive" means the model understands deeply — not that the
   interface twitches on every signal.

---

## 15. The persistent learner: identity, continuity & behavioral capture

The sections above describe one session in isolation. This section describes how a learner
becomes *continuous* — recognized across devices and across time — and how we capture the
full picture of *how* they work, not just whether they were right. The motivating goal: to
help a student well, the system needs to understand what they need and when they need it,
across a phone, a tablet, and a return after days away. The governing constraint is invariant
9 — **capture richly, act conservatively**: everything here feeds *understanding*, never a
twitchier interface.

### 15.1 Identity — Google Sign-In (OIDC)

Authentication is delegated to Google. The frontend uses Google Identity Services to obtain an
**ID token**; the backend's `auth/` module verifies that token (signature against Google's
JWKS, audience = our client ID, issuer + expiry) and resolves it to a learner keyed by the
Google account id (the `sub` claim). **We never store passwords** — delegating to Google means
no credential storage, no reset flows, and Google handles MFA, recovery, and breach detection.
This is deliberately safer than a hand-rolled auth system (OWASP's "don't build your own auth").

The learner profile we keep is minimal: the Google `sub`, a display name, an optional email,
and `created_at`. Identity stops at the API boundary: per invariant 8, `sub` never flows into
the mastery model, the policy, or the LLM.

**Under-13 / COPPA.** Personal Google accounts require age 13+. The intended path for 6th–7th
graders is **Google Workspace for Education** (school-issued accounts), where the *school* is
the consent authority under COPPA's school-consent provision — a cleaner posture than us
collecting parental consent directly. The exact consent posture (Workspace-only vs. also
allowing 13+ personal accounts with a notice) is a flagged decision recorded in `PROJECT.md`,
not silently locked here. Data minimization and a stated retention policy apply regardless,
because this is children's data.

### 15.2 Continuity — server-side session persistence & resumption

Today the session lives in an in-memory store; for a continuous learner it must be durable.
The existing `Session` / `Turn` / `MasteryState` tables become the source of truth via a
repository in `db/`, keyed to `learner_id`:

- **Mastery persists across sessions.** `MasteryState` (BKT per KC) is per-learner, so progress
  carries over no matter which device the learner returns on or how long they were away.
- **Sessions are resumable.** An open session (`ended_at` null) can be rehydrated into a live
  `TutorSession` from its persisted turns + mastery; on login the learner can continue where
  they left off or start fresh.
- **Cross-device is automatic.** The same Google login on any device resolves to the same
  `learner_id` and therefore the same persisted state.

Persistence is a write that happens alongside or after the response, never on the sub-100 ms
decision path (invariant 7). Routes stay thin; the repository is called from services.

### 15.3 Full raw behavioral capture

We capture the **full raw interaction stream**, not just per-turn outcomes, because *how* a
learner works a problem is the signal that distinguishes confident-wrong from struggling, and
genuine understanding from lucky wandering — signals a chat box or a static walkthrough
physically cannot collect.

- **What.** Keystrokes with timing, edits/backspaces, **answer-revision count** (how many
  times the answer changed before submit), **time-to-first-interaction** (the hesitation before
  the learner first touches the problem), number-line drag paths (oscillation / overshoot around
  the target), fraction-bar interactions, focus/blur, idle, hint open + dwell, submit, and
  **navigation/page events** (sign-in method chosen, surface-state transitions, problem
  presented) — instrumented in the frontend `telemetry/` layer, each tied to its problem/KC/
  surface-state context.
- **Transport.** Events are buffered client-side and flushed asynchronously to a new `/events`
  endpoint — **off the turn loop** (invariant 7). Fire-and-forget with retry; never blocking an
  answer.
- **Storage.** An append-only `interaction_event` table (`learner_id`, `session_id`,
  `turn_index`, `event_type`, `payload` JSONB, `client_ts`, `server_ts`), write-optimized for
  volume. Payloads are interaction telemetry only — no free-text or PII.
- **Use.** Features are derived from the stream **offline / async** into a tutor-native
  **HelpNeed v2** (retiring the proxied columns the EDM-Cup-trained v1 leans on). Derived signal
  feeds the *gated, observe-then-act* HelpNeed path (Section 8) — it never drives a live turn
  decision directly.

### 15.4 Where this sits in the loop (and where it must not)

```mermaid
flowchart LR
    L((Learner)) -->|Google ID token| AUTH["auth/ · verify OIDC"]
    AUTH -->|learner_id| API["Turn Loop / API"]
    API <-->|persist / rehydrate| REPO["db/ repositories<br/>Session · Turn · MasteryState"]
    L -. "raw interactions (async, off-path)" .-> EV["/events ingest · events/"]
    EV --> IE[("interaction_event")]
    IE -. "offline derivation" .-> HN["HelpNeed v2 features"]
    HN -. "observe → gated" .-> POL["Policy (refuse-rules + sustained gate)"]
```

The solid path (auth → turn loop → persistence) is request-time but kept off the sub-100 ms
decision critical path; the dotted paths (event capture, offline feature derivation) are
explicitly asynchronous. Nothing in this section may move what the UI does *automatically*
mid-problem — that remains the refuse-rules' and the sustained-signal gate's job.

---

*For contribution guidelines, commit conventions, and the source hierarchy, see
[`CLAUDE.md`](./CLAUDE.md).*
