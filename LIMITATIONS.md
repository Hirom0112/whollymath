# Limitations Memo — WhollyMath (v1 prototype, 6-week build)

WhollyMath is a 6-week pitch prototype, and this memo is where we own — proactively
and specifically — what it does **not** do. Every limitation below was a deliberate
v1 scope decision, not an oversight: for each one we state the limitation, **why we
accepted it for v1**, and the **v2 / future path**. The honest version of "what we
built" is more useful to a reviewer than a polished version of "what we wish we'd
built," and the things we cut are exactly the things a careful evaluator should
press on — so we name them first.

The unifying theme is the architecture's governing principle: **capture richly, act
conservatively, and never fake mastery.** Several limitations below are direct
consequences of refusing to overstate a result we cannot defend (e.g. we will not
claim a proactive-help effect size we have no population to measure).

---

## 1. Validation

### 1.1 No real-student validation; personas are synthetic adversaries, not a learner population

The mastery model, transfer probe, and refuse-rules are validated against **five
deterministic synthetic personas** (Surface Sam, Natural-number Nate, Hint-hunter
Hugo, Click-through Cleo, Procedure Priya), not against real students. These personas
are documented-misconception *instances* — each is hand-built to attack one specific
mastery-gaming pathway — **not** a sampled or validated model of how real learners
behave.

**Why accepted for v1.** With no IRB, no student cohort, and a 6-week clock, a
synthetic adversarial harness is the strongest *defensible* validation available: it
lets us prove a falsifiable claim ("no adversary reaches confirmed mastery on the KC
it attacks — 5/5 denied") deterministically and reproducibly. The personas are
designed as the mastery model's red team, and the false-positive harness shows each
is blocked by the rule it targets.

**A consequence we own (instrument mismatch).** Because four of the five personas are
built to look *fluent-but-flawed*, they are the wrong instrument for some downstream
measurements. The HelpNeed live-path calibration (RESEARCH.md §7.5) is the clearest
case: its aggregate "separation" number is carried almost entirely by one persona
(Click-through Cleo); strip her out and the signal is ~0 or inverted. We relabelled
that run honestly as a **wiring smoke test, not a model-quality result** — the model's
real quality lives in its EDM Cup holdout (AUC 0.893), not in these five.

**v2 path.** A real pilot with a small student cohort (or a richer, calibrated
simulator population) to produce honest learning-outcome numbers. The behavioral
capture pipeline (§5 below) exists precisely to feed this.

### 1.2 Within-session mastery only; no longitudinal / retention modeling

The mastery declaration is a **within-session** judgment (BKT + the §3.4 anti-gaming
rules + the S5 transfer probe). There is no spaced repetition, no forgetting curve, no
re-test over days or weeks. A learner who "masters" addition today is not re-checked
tomorrow.

**Why accepted for v1.** The retention literature (Ebbinghaus, Roediger & Karpicke) is
unambiguous that durable retention requires *spaced* practice — but spaced repetition
is a multi-day product loop, untestable inside a single demo session and out of scope
for a 6-week prototype whose deliverable is a within-session learning flow. We chose
to build the within-session mastery judgment *well* rather than a shallow long-term
scheduler.

**v2 path.** A spacing layer (Leitner / SM-2 / a BKT `p_forget` term) scheduling
re-tests across sessions, preserving the current mastery model as the per-session
verdict. The persistence layer (§6.1) now carries mastery across sessions, which is the
foundation this would build on.

---

## 2. Pedagogical model

### 2.1 LLM step-explanations are not 100% verifiable

All *numeric* correctness is decided by SymPy — the LLM never decides whether an
answer or a hint's numbers are right, and a validation gate confirms an LLM-rephrased
hint carries exactly the canonical step's numbers (none dropped, altered, or
invented). But the **natural-language conceptual framing** around those verified
numbers ("why did this work?") is LLM-generated and is **not** symbolically
verifiable.

**Why accepted for v1.** Step-level math-reasoning verification by LLMs is a
documented open research problem (**Daheim et al. 2024**, arXiv:2407.09136) — which is
exactly why we use SymPy for content validation rather than trusting LLM judgment. We
constrain the LLM to the lowest-risk surface (rephrasing already-verified canonical
text, behind a numeric gate and a safety filter) so a hallucinated *number* can never
reach a child; the residual risk is in conceptual *prose*, which we bound but cannot
eliminate.

**Known sub-limitation.** The hint safety filter (`is_safe_copy`) is intentionally
minimal (non-empty + length cap) — numeric correctness is the SymPy gate's job and
faithfulness is the prompt's. A stricter content/keyword filter is flagged for
tightening if wanted; we did not add an unsourced blocklist.

**v2 path.** Track the Daheim-line research on stepwise verification; add a
faithfulness check on conceptual prose as that tooling matures.

### 2.2 Not every live route reaches *confirmed* mastery the same way; error-finding covers add/sub only

Mastery rule 2 requires correctness across **two representations**, so a route is only
masterable live once its second live representation exists. As built, all four routes
(addition, subtraction, equivalence, number-line placement) are now masterable live —
arithmetic via symbolic + number-line, equivalence via symbolic + word-problem, and
placement via the drag + a magnitude comparison.

The honest asymmetry is in the **S5 transfer probe's error-finding step**: it requires
a *modeled wrong claim* to reject, and only the two operation KCs
(`ADDITION_UNLIKE`, `SUBTRACTION_UNLIKE`) have one (`_error_finding_claim` returns
`None` for the others). So **error-finding transfer is add/sub only**; equivalence and
number-line placement are confirmed by the **representation-transfer item alone** — an
honest representation-transfer gate, but a narrower confirm than the operation KCs get.

**Why accepted for v1.** A reject-and-justify item needs a research-grounded wrong
claim; we have modeled misconceptions (add-across / subtract-across) for the operation
KCs but not for equivalence/placement in a form that yields a clean wrong-value to
reject without grading free text. Inventing one would be unsourced.

**v2 path.** Model wrong-claim instances for the equivalence and placement KCs so every
route gets the full reject-and-justify probe.

### 2.3 AREA_MODEL not served live

The FractionBar (area-model) workspace exists, but the **live turn loop never serves
AREA_MODEL items**. The area-model equivalence item is load-bearing for Natural-number
Nate's rule-2 attack in the persona harness; repurposing it for the live surface would
require re-authoring the persona and the simulator and would risk the §8 false-positive
harness.

**Why accepted for v1.** Wiring FractionBar into the live surface now would be dead UI
(no route serves it) and would put the adversarial harness at risk for no live benefit.
We chose to keep the harness intact and leave the live area-model as a documented
future slice rather than bolt it on.

**v2 path.** Author an AREA_MODEL live route (and, if needed, a separate harness item)
so the bar becomes a real third representation a learner can be assessed in.

---

## 3. ML / HelpNeed predictor

### 3.1 Cross-tutor calibration gap (trained on EDM Cup, served on our tutor via proxies)

The v1 HelpNeed predictor is an XGBoost model trained on the **EDM Cup 2023 /
ASSISTments** clickstream (holdout AUC 0.893), but served on **our** tutor. Two
signals are not present in the EDM Cup data and entered live inference as **proxies**:
`recent_attempts_mean` (held constant ≈ 1) and `recent_request_answer_rate` (proxied
by the hint rate). BKT and state-transition features — our tutor's native signals —
are absent from training entirely.

**Why accepted for v1.** We have no real-learner interaction logs of our own, so a
strong public dataset plus an honestly-reported train/serve gap is the best available
v1 path. The predictor is **observe-only** through the whole of v1 (it never fires an
unrequested intervention), so the calibration gap cannot harm a learner — it can only
mislabel an observation we are logging, not acting on.

**v2 path.** The proxy-free v2 feature pipeline below, trained on our own captured
events.

### 3.2 HelpNeed v2 pipeline exists, but no trained v2 model ships

The v2 feature-derivation pipeline (`helpneed/events_features.py`) is built and tested:
it derives the feature vector from the PL.2 behavioral event stream and **retires both
v1 proxies** (`recent_attempts_mean` becomes the real `submit` count;
`recent_request_answer_rate` becomes a real give-up signal — hint escalation to
worked-step depth), and adds two columns v1 could not express (revision count,
time-to-first-interaction). But **no trained or validated v2 model ships** — we have no
real-learner event data to train it on yet.

**Why accepted for v1.** Training a v2 model on no real events would just relearn the
synthetic personas; the responsible move is to ship the *pipeline* the captured demo /
real events will feed, and defer training + a re-validation until that data exists. v2
stays observe-only and is not imported by the turn loop (architectural invariant 9).

**Known sub-limitation carried in code.** The event stream alone has no SymPy
correctness verdict (that lives on the `Turn` row), so the v2-derived error /
unproductive rates are a **help-seeking subset** of the §3.4 label until the verified
`Turn` outcome is joined in — a clean follow-up, flagged in `events_features.py`.

**v2 path.** Capture real events → join the `Turn` correctness verdict → train v2 →
re-run the Slice 5.4-style validation.

### 3.3 Proactive A/B proves SAFETY, not effect size

The proactive-intervention layer ships with a tuned sustained-signal gate (K=3,
threshold=0.5, swept not hand-tuned) and an A/B test. The A/B's honest result: running
each persona reactive-only vs. reactive+proactive yields **identical mastery outcomes
(5/5)**. This certifies a **safety property** — the proactive arm can never corrupt the
deterministic mastery path — **not** an effect size. We do **not** claim that timely
proactive help improves learning.

**Why accepted for v1.** Measuring an effect size needs a **help-responsive learner
population**, and our five personas are the mastery model's *adversaries*, not
help-responsive learners — the help-responsive archetypes (anxious-quitter,
bored-advanced) are an explicit v1 exclusion (§4.1). We deliver the validated, safe,
well-targeted *mechanism* and report the missing effect-size measurement plainly rather
than papering over it. (Maniktala et al. 2022 caution: proactive HelpNeed gains needed
substantial *own-student* prior data, which we do not have — so "proactive did not beat
reactive" was a live, reportable outcome we were prepared to publish.)

**v2 path.** An effect-size A/B once a help-responsive population (real students or a
richer simulator) exists.

---

## 4. Scope boundaries

### 4.1 Anxious-quitter and bored-advanced personas excluded

The persona roster is five adversaries attacking mastery-gaming pathways. We
deliberately did **not** build an anxious-quitter or a bored-advanced persona.

**Why accepted for v1.** (1) Bounded scope at five personas for a 6-week build; (2)
anxiety and disengagement are *behavioral/emotional* responses that are hard to
simulate without trivializing real students' emotional experience — a bad simulation
is worse than none. Their absence is also why we can't claim a proactive-help effect
size (§3.3): they would have been the help-responsive population.

**v2 path.** Add help-responsive personas (carefully, with grounding) as the population
for the effect-size proactive A/B.

### 4.2 Multi-device sensor fusion / camera input scoped out

The architecture is designed to *support* a future camera-input modality (uploading
handwritten work) and multi-device sensor fusion, but **neither ships in v1**. Input is
touch + text only; voice was also evaluated and rejected (students don't naturally
verbalize math expressions).

**Why accepted for v1.** Camera/handwriting recognition and cross-sensor fusion are
each a project in themselves; they were named in the plan as explicit stretch goals so
their absence reads as a deliberate cut, not a miss. We chose math-native input modes
(direct manipulation on the number line / fraction bar, symbolic editor) over a
speculative second modality.

**v2 path.** Camera input for handwritten work + research into whether fusing it with
the tablet workspace actually improves outcomes vs. a single device.

---

## 5. Accessibility (partial)

Accessibility was considered **architecturally** but is **not fully implemented**. In
scope and present: mouse fallback for touch interactions, a colorblind-safe palette. In
scope but partial; and **explicitly out of scope: full screen-reader support.**

**Why accepted for v1.** The custom SVG workspaces (number line, fraction bar) are the
hardest surfaces to make screen-reader-accessible, and doing it properly is
substantial, specialized work. We chose to ship the core adaptive learning experience
and name accessibility honestly as partial rather than claim a compliance we hadn't
verified.

**v2 path.** A dedicated accessibility pass: ARIA semantics and keyboard-operable
alternatives for the SVG manipulatives, screen-reader narration of problem state, and
an audited contrast/focus pass.

---

## 6. Privacy / auth

### 6.1 Children's-data posture; COPPA consent is a sign-off item

Identity is **Google Sign-In (OIDC)** — the backend verifies Google ID tokens with
Google's official verifier and keys the learner to the Google `sub`; **we store no
passwords** (delegating to Google is materially safer than rolling our own auth). The
verified identity is **firewalled** from the decision path: it never reaches the mastery
model, policy, or LLM (architectural invariant 8). The raw behavioral stream is
**interaction telemetry only** — timings, edits, drag paths, focus/idle — **no PII, no
free text** — flushed off the turn loop to an append-only store, with data minimization
and a stated retention policy.

The **COPPA consent posture for under-13s is a flagged sign-off item, not locked**:
(a) Google Workspace for Education only (school as consent authority — the cleanest
minor-data story) vs. (b) also allowing 13+ personal accounts with a consent notice.
The current sign-off is **both** (Workspace-for-Education + 13+ personal with notice).

**Why accepted for v1.** The consent model is a product/legal decision that benefits
from explicit human sign-off rather than an engineering default; we built the technical
posture conservatively (no passwords, identity firewalled, telemetry de-identified) so
the consent choice is the only open variable.

**v2 path.** Lock the consent posture; formalize the retention policy and a
data-subject-deletion path.

### 6.2 Auth requires a real Google client id to go live

The Google OIDC code (backend + frontend) is complete and tested, but is **additive and
inert by default**: with no client id configured, the app runs the anonymous/guest path
exactly as before. **Going live requires provisioning `GOOGLE_CLIENT_ID` (backend) and
`VITE_GOOGLE_CLIENT_ID` (frontend)** — an operational step, not a code gap. Until then,
`/me` returns 401 "authentication is not configured" when a token is presented, and the
anonymous turn loop is untouched.

**Why accepted for v1.** Provisioning an OAuth client is an out-of-band operational task
that doesn't block the prototype or the demo (which run anonymous). The code is done; the
secret is a deployment step.

**Documentation gap to reconcile (found in code).** Neither `GOOGLE_CLIENT_ID` nor
`VITE_GOOGLE_CLIENT_ID` currently appears in any `.env.example`, even though the
committed env template is meant to be the contract of required keys. The go-live
requirement is recorded only in commit messages, not in the env template — worth adding
so the deployment contract is self-documenting.

---

## 7. Operational

### 7.1 Session resume is mastery-level, not exact-problem

A dropped session whose client still holds its `session_id` and whose DB row is open
**rehydrates per-KC BKT priors and the confirmed-KC set** (progress carried forward) and
serves a *fresh* problem. **Exact in-progress-problem / turn-by-turn rehydration is
deferred** — it would require replaying the observation log and the §3.6 counters into a
`TutorSession.from_persisted`.

**Why accepted for v1.** Faking exact resume would corrupt the mastery evidence (the
§3.6 counters and observation log are load-bearing for the anti-gaming rules), so a
half-built exact-resume is worse than an honest mastery-level one. Carrying mastery
forward is the property a returning learner actually cares about; re-serving a fresh
problem in the same route is a clean, non-fragile recovery.

**v2 path.** `TutorSession.from_persisted` replaying the per-turn event stream (the PL.2
capture exists) to restore the exact in-progress problem and counters.

### 7.2 Persistence and event capture require Postgres running

The app **boots in-memory when no Postgres is reachable** (verified) — the turn loop,
mastery model, and demo work fully without a database. But session/mastery
**persistence**, **cross-device continuity**, and **behavioral-event capture** only take
effect with Postgres up: with no DB, `POST /events` returns 202 with `accepted=0`
(nothing persisted) and mastery is not carried across restarts.

**Why accepted for v1.** Graceful degradation to in-memory keeps the demo and local
development frictionless (no DB required to see the product work), while persistence is a
strict superset that activates when the DB is present. Persistence runs **off** the turn
loop (architectural invariant 7) and is equivalence-tested: a turn's response is
byte-identical with or without persistence, so the DB can never block or alter a turn.

**v2 path.** Standard managed Postgres in the deployed environment (RDS, single-AZ,
smallest instance per the cost plan); the Alembic migrations are the authority for
schema.

---

## Closing note

None of the above is a surprise to us — every item was a scoping decision made out
loud, recorded in the planning docs and the git decision log as we built. The
prototype's claims are deliberately narrow and defensible: we prove the mastery model
resists gaming, that the proactive layer is *safe*, and that the architecture keeps the
LLM out of the correctness path. What we have **not** proven — real-student learning
outcomes, a proactive effect size, durable retention — we name here rather than imply.
