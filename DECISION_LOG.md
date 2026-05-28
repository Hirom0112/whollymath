# WhollyMath — Decision Log

This is the finalized, reviewer-facing decision log for WhollyMath (a Hyperresponsive
Mastery UI for fraction equivalence and operations), the 6-week pitch project for Nerdy.

**How to read this log.** Per `CLAUDE.md` §3, on this project *commit messages are the
authoritative tracked decision-log entries* — they were deliberately written as decision-log
prose (scope, rationale, source refs) because the internal planning docs (`PROJECT.md`,
`TECH_STACK.md`, `RESEARCH.md`, `Nerdy.md`, `TODO.md`) are intentionally gitignored and never
push to a remote. This file is **not a new source of truth**; it is an *assembly* of those
commit messages and the on-disk planning docs, organized by theme so the reasoning is legible
without walking the whole git history. Every entry cites the commit short-hash where the
decision landed (and, where applicable, the planning-doc section it traces to). Where a
decision was later revised, the revision is shown with its reason.

The short-hashes below are real commits on `main`; run `git show <hash>` to read the full
tracked entry behind any decision.

---

## Table of contents

1. [Governance: the source hierarchy and "the PRD is the contract"](#1-governance)
2. [The six locked open questions (Slice 0.D)](#2-locked-open-questions)
3. [The mastery model: two-stage, with the five §3.4 anti-gaming rules](#3-mastery-model)
4. [The reactive UI policy and the refuse-rules](#4-reactive-ui-policy-and-refuse-rules)
5. [Architectural boundaries: SymPy / XGBoost / no-LLM-in-the-turn-loop](#5-architectural-boundaries)
6. [The four-layer persona harness](#6-persona-harness)
7. [The HelpNeed predictor: data, gate, and the signed-off tuning](#7-helpneed-predictor)
8. [The proactive layer and the honest A/B finding](#8-proactive-layer-and-the-ab-finding)
9. [The three-arm baseline comparison](#9-baseline-comparison)
10. [The persistent-learner initiative (2026-05-28)](#10-persistent-learner)
11. [Cold start, content coherence, and the product surface](#11-cold-start-and-product-surface)
12. [Infrastructure and cost controls](#12-infrastructure)
13. [Index of revisions](#13-index-of-revisions)

---

<a name="1-governance"></a>
## 1. Governance: the source hierarchy and "the PRD is the contract"

**Decision.** Every change must trace to a ranked source hierarchy — PRD > `PROJECT.md` >
`TECH_STACK.md` > `RESEARCH.md` > `Nerdy.md` > cog-sci/ITS literature > team discussion —
and the PRD's requirements can be neither expanded nor contracted by anything below it.
"Best practice from training data" ranks below all of these and is not valid justification.

- **Why.** This is a pitch project whose decision log is a graded deliverable; a defensible
  log requires that every choice be sourced, and that lower sources defer to higher ones
  rather than silently overriding them.
- **Source.** `CLAUDE.md` §1; established in commit **cbbbf48** (repo init with the AI
  guidelines + gitignore).

**Decision.** The planning docs are gitignored; `CLAUDE.md` is tracked; therefore the
**commit message is the tracked decision-log entry**, and any change that touches a documented
decision must update the on-disk doc *and* record the rationale in the same commit message.

- **Why.** The planning docs do not appear in any diff or remote, so a doc edit alone leaves
  no trace a reviewer can see. The commit message is the only durable, reviewable record.
- **Source.** `CLAUDE.md` §1, §3, §8.4; commits **cbbbf48** and **8da3613** (Director
  operating model + gitignore the build tracker; the six open questions locked on disk).

**Decision.** Claude operates as build *director*: delegate bounded work to subagents, keep
only conclusions in the main thread, verify all delegated work to a production-grade bar
before marking it complete, and escalate any source/plan drift immediately rather than
working around it.

- **Why.** Trunk-based work with no PR gate moves the review discipline into the commit
  itself; the director model keeps a multi-step, multi-week build legible and keeps
  correctness/source-traceability the director's responsibility even when agents do the work.
- **Source.** `CLAUDE.md` §5; commit **8da3613**.

---

<a name="2-locked-open-questions"></a>
## 2. The six locked open questions (Slice 0.D)

Six design questions were left open at planning time and locked together on 2026-05-27
(`PROJECT.md` §8). Each is recorded here with where it was *implemented*, not just decided.

### 2.1 Problem generation — hybrid (procedural + diagnostic-gem bank)
- **Decision.** A deterministic procedural generator (bulk; surface format is a generator
  *parameter*) plus a ~50-item handpicked, research-cited "diagnostic-gem" bank, both
  conforming to one shared `Problem` type so mastery/persona/transfer code is source-agnostic.
- **Why.** The procedural generator gives volume and lets format be varied for interleaving
  (which defeats Surface Sam); the gem bank gives items engineered to trip a *documented*
  misconception or exercise a cited principle. One `Problem` type prevents the consumers from
  caring where an item came from.
- **Source.** `PROJECT.md` §8 (0.D.1), §3.1; bank decision 0.D.7. Bank landed in commit
  **15849fe** (50 items, SymPy-verified 50/50, citation spot-check); generators + shared type
  in **9c5ff59**.

### 2.2 Cold start — two-step (route, then calibrate)
- **Decision.** Turn 0 is a kid-friendly routing menu (three equal-weight KC choices plus a
  de-emphasized "I'm not sure" defaulting to equivalence, no quiz/diagnostic framing, no
  curriculum terms). Turn 1 is one calibration problem in the chosen route. The self-report
  seeds a BKT *prior, not a commitment* — turn-1 performance can override it, and the
  self-report is never echoed back to the learner.
- **Why.** Avoids the anxiety/labeling of a diagnostic quiz while still seeding the model;
  grounded in metacognitive-calibration research (García et al.) showing young learners are
  over-confident, so a self-report must be a prior, not a verdict.
- **Source.** `PROJECT.md` §8 (0.D.2); backend two-step loop in commit **d7ebe0f**; the
  Turn-0 routing screen in **43b9028**.
- **Revision (2026-05-28).** The equivalence/unsure calibration item ("Is 2/3 the same amount
  as 4/6?") is a *yes/no* relational judgment, so it must serve a Yes/No widget and a yes/no
  verifier path, not the fraction editor it was wrongly rendering (a new `Problem.answer_kind`
  drives both surface and verifier; truth is SymPy over the operands). Fixed in commit
  **a7dbcf2** (`PROJECT.md` §8 cold-start "answer-form correction").

### 2.3 Hint templates — three levels
- **Decision.** Three hint levels: **nudge** (pre-written, no LLM, no SymPy), **partial_step**
  and **worked_step** (LLM slot-fill → SymPy-validated → ≤2 retries → pre-written fallback).
  Phased: nudges in weeks 2–3, the LLM-validated levels in week 4.
- **Why.** A nudge carries no symbolic content so it needs no validation; the deeper levels
  let an LLM phrase warmly but the SymPy gate guarantees a hallucinated or altered number can
  never reach a child (the §8.2 "LLM never decides correctness" boundary applied to hints).
- **Source.** `PROJECT.md` §8 (0.D.3), §3.10. Nudge bank in commit **579c7f4**; the
  LLM-validated levels (SymPy numeric gate + safe-copy filter + fallback) in **cfcbde8**;
  live-loop escalation 0→nudge→partial→worked in **15c7d99**.

### 2.4 LLM provider — Claude, tiered
- **Decision.** Claude as primary behind an `LLMProvider` Protocol, tiered:
  `cheap` = Haiku 4.5 (persona surface), `standard` = Sonnet 4.6 (hint slot-fill),
  `premium` = Opus 4.7 (worked examples / chat-baseline arm). No LLM in the turn loop.
- **Why.** Match model cost to task difficulty; the Protocol keeps the provider swappable and
  keeps the surface layer dependent on the seam, not the SDK. Aggressive prompt caching on the
  stable system prompt cuts repeat-turn cost.
- **Source.** `PROJECT.md` §8 (0.D.4), TECH_STACK §6. Implemented in commit **15518b0**
  (tiered `complete()` + prompt caching; date-suffix-free model IDs). LangSmith tracing for
  these calls, env-gated and confined to `llm/`, added in **09e1061**.

### 2.5 Initial tunings — τ, threshold, interleave, idle, struggle window
- **Decision.** τ = 0.85 (BKT mastery threshold), HelpNeed threshold = 0.5, interleaving
  cadence = 3 items across ≥2 KCs, idle timer = 90s, productive-struggle window = 60s. All
  tunable in weeks 4–5, with changes recorded in the decision log.
- **Why.** Defensible starting points to be hardened against adversarial-persona results
  rather than guessed once and frozen.
- **Source.** `PROJECT.md` §8 (initial tunings), 0.D.5. Encoded as named constants traced to
  0.D.5 in the mastery model (commit **ea6f1bf**), the policy (**a231d42**), and the
  HelpNeed/gate work (below).
- **Revision (signed off 2026-05-28).** τ = 0.85 confirmed and the proactive gate's
  K = 3 / threshold = 0.5 promoted from provisional to *final* by the Slice 5.4 sweep — see
  §7 and §8 below (commits **0becfb2**, **b21c2f6**).

### 2.6 Retention-over-time — out of v1
- **Decision.** Spaced-repetition / retention-over-time modeling is scoped out of v1 and
  acknowledged in the limitations memo with a v2 sketch (Leitner / SM-2 / BKT p_forget).
- **Why.** A 6-week build; within-session mastery is the defensible scope, and faking
  retention would weaken the honesty of the mastery claim.
- **Source.** `PROJECT.md` §8 (retention), §9 limitations. Recorded at lock time in commit
  **8da3613**; reaffirmed as a limitation throughout.

---

<a name="3-mastery-model"></a>
## 3. The mastery model: two-stage, with the five §3.4 anti-gaming rules

**Decision (headline).** Mastery is **not** "BKT crossed τ." It is a **two-stage** construct:
*provisional* mastery (BKT > τ AND four structural rules AND an engagement floor), then
*confirmed* mastery only after the S5 transfer probe passes. A failed probe demotes the
learner back to scaffolded practice.

- **Why.** A naive threshold falsely masters the adversarial personas; each rule exists to
  defeat a specific persona, and the transfer probe catches the one persona (Priya) who clears
  every structural rule by rote.
- **Source.** `PROJECT.md` §3.4, §3.9. Provisional rules in commit **ea6f1bf** (per-KC BKT +
  the §3.4 rules, each with a test that sets BKT > τ and asserts the rule *still* blocks
  mastery); the S5 probe in **296d0db**; the live-loop confirm-gate in **b343a06** (see
  revision below).

The four structural rules + the floor, and the persona each defeats:

| Rule | Requirement | Defeats | Landed in |
|---|---|---|---|
| 1 | BKT probability > τ (= 0.85) | (baseline) | **ea6f1bf** |
| 2 | Correct across ≥ 2 representations of the KC | Natural-number Nate | **ea6f1bf** |
| 3 | ≥ 1 unscaffolded (no-hint) correct attempt | Hint-hunter Hugo | **ea6f1bf** |
| 4 | Computed on *interleaved* (≥3 items, ≥2 KCs), not blocked, practice | Surface Sam | **ea6f1bf** |
| floor | Engagement floor; sub-floor-latency corrects are down-weighted | Click-through Cleo | **ea6f1bf** |

- **Supporting detail.** The BKT update is the standard two-step Corbett-Anderson update,
  pinned by a hand-computed test. Evidence is soft-weighted: hinted-correct, blocked-correct,
  and sub-floor corrects each move the estimate strictly *less* than a clean correct; wrong
  answers count in full. `declare_mastery` returns the (mastered, reasons) pair naming every
  blocked rule — so the decision log can see *why* a learner was denied.
- **Revision (2026-05-28).** Until commit **b343a06** the *live* loop declared "mastered" on
  provisional mastery and never ran the S5 probe for a real learner, so the live claim did not
  match the headline ("we don't fake mastery"). **b343a06** wired the transfer probe into the
  live turn loop: provisional → enter S5 → pass every probe step → CONFIRMED; any wrong step →
  demote with a cooldown. After this, the snapshot's `mastered` means CONFIRMED, never bare
  provisional. The "final check" badge for S5 items was added in **71575de**.

**Decision (transfer probe shape).** Two item types per declaration: **representation
transfer** (same KC, a representation different from recent work — catches Sam) and
**error-finding transfer** ("Tim says ¼+¼=2/8 — why is he wrong?", pass = reject AND justify —
catches Priya). For a real learner, error-finding is operationalized as a two-step
"Is Tim right?" (yes/no reject) + "what does it really equal?" (supply the value), so it grades
without free-text grading.

- **Why.** Error-finding is the only gate that catches procedural-without-conceptual fluency;
  the two-step form makes it gradable by SymPy rather than by an LLM judging prose.
- **Source.** `PROJECT.md` §3.9; commits **296d0db** (probe + items), **b343a06** (live two-step
  error-finding, the 2026-05-28 decision).
- **Honest gap (flagged, then closed).** Error-finding initially covered only addition/
  subtraction (the KCs with modeled wrong-claims); equivalence and number-line placement get
  the representation-transfer item alone — an honest representation-transfer gate, not a hollow
  probe (**296d0db**, **b343a06**).

**Decision (every route is masterable, honestly).** A route can only reach declared mastery if
it has ≥2 *live-answerable* representations (rule 2). The scheduler reports `is_masterable_live`
per route rather than hiding routes that cannot yet hit mastery.

- **Why.** An honest end-to-end play-through found the live product was a hollow shell around a
  sound model: a single-KC, single-format scheduler made rules 2 and 4 unfireable, so declared
  mastery was *unreachable* live even though the model was correct.
- **Source.** `PROJECT.md` §3.4 rule 2, §3.6, 0.D.5. The interleaving scheduler + real
  number-line arithmetic made arithmetic routes masterable in commit **b4bf977**; equivalence
  got a 2nd representation (word-problem yes/no) in **fcb0cb1**; number-line placement got a
  2nd representation (magnitude comparison) in **3245d4f**, after which *all four* routes are
  masterable.

---

<a name="4-reactive-ui-policy-and-refuse-rules"></a>
## 4. The reactive UI policy and the refuse-rules

**Decision.** The UI adaptation policy is **reactive by default** (a proactive layer is layered
on top — see §8): five surface states (S1 symbolic, S2 number line, S3 fraction bars, S4 worked
example, S5 transfer probe) with a fixed transition table keyed on the *error type the verifier
already produced* — magnitude→S2, operation/format→S3, 2-correct-no-hint→S1 (fade), 2+ errors→S4
(the from-any-state catch-all), interleaved-set-passed→S5, idle>90s→nudge (never a state change).

- **Why.** Errors are surfaced to the representation that exposes them (Aleven & Koedinger
  fading scaffolds; help-avoidance research). The policy is pure signal-routing — it imports no
  SymPy/LLM/DB/mastery, so a reviewer can trust the layer boundary.
- **Source.** `PROJECT.md` §3.5, §3.6. Implemented in commit **a231d42** (the §3.6 table
  verbatim, every transition carrying a one-line label); `SurfaceState` extracted as the shared
  vocabulary in **7bab4cc**; the loop made reactive in **1a0c52f**.
- **Flagged extension.** §3.6 row 7 (transfer-fail → state) does not enumerate the target
  state, so transfer-fail reuses the table's own magnitude/operation logic (number-line→S2,
  operative KCs→S3). Documented as an extension to revisit (**a231d42**).

**Decision.** Six **refuse-rules** — what the UI will *never* do automatically: (1) never change
state mid-problem; (2) never silently discard the learner's work (a "previous work" panel
preserves it); (3) never change state because the learner paused; (4) never present a new state
without a one-line label; (5) never auto-help in the first 60s except on a wrong answer or
explicit hint request; (6) when help is shown, render it inline in the workspace, not a modal
(the Maniktala "Assertions" pattern).

- **Why.** The PRD explicitly asks the interface to declare what it refuses to change
  automatically; these protect productive struggle and reach help-avoidant learners inline.
- **Source.** `PROJECT.md` §3.8. Enforceable rules (no mid-problem change, no change on pause,
  always-labeled, 60s gate) in commit **a231d42**; the inline-assertion render (rule 6) in
  **4ca7b56** and the mascot-voiced inline form in **7815b95**; the previous-work panel (rule 2)
  in **a83b589**.

---

<a name="5-architectural-boundaries"></a>
## 5. Architectural boundaries: SymPy / XGBoost / no-LLM-in-the-turn-loop

**Decision.** Three hard ownership boundaries: **SymPy owns all math correctness** (answer
checking, step validity); **XGBoost owns HelpNeed prediction**; **the LLM never enters the
sub-100ms turn loop** and never decides whether an answer is correct. The LLM is for
natural-language surface generation only, always *after* the deterministic logic has run.

- **Why.** Step-level math verification by LLMs is a documented open problem (RESEARCH.md §1.6,
  Daheim et al. 2024), and an LLM call would blow the latency budget. These boundaries are what
  make the mastery claim defensible and the turn loop fast.
- **Source.** `CLAUDE.md` §8.1, §8.2; `PROJECT.md` §3.10. The SymPy verifier (never `eval`/
  `sympify` on learner input; exact value-equality, so 2/4 == 1/2) in commit **ad328a0**; the
  verifier's `ErrorCategory` made the one canonical routing enum the API speaks in **6c215b9**.
  The LLM entered the project only at **15518b0**, confined to `app/llm/`, with structural tests
  asserting `anthropic` imports live only there; the same boundary is re-asserted in every
  LLM-touching commit (**6212eb6**, **00d2380**, **cfcbde8**, **895f3cc**).

**Decision.** When an LLM *does* rephrase hint or worked-step text, the SymPy gate verifies the
rephrase carries *exactly* the canonical text's distinct numbers (none dropped, altered, or
invented); any failure → the pre-written/canonical text verbatim.

- **Why.** Lets the LLM add warmth without ever letting a hallucinated number reach a child;
  faithfulness is the prompt's job, numeric correctness is the gate's.
- **Source.** `PROJECT.md` §3.10 (0.D.3); commit **cfcbde8** (`domain/hint_validation.py` gate
  + `is_safe_copy` filter + fallback). `is_safe_copy` is intentionally minimal (a keyword
  blocklist would be unsourced taste, §8.6) — flagged for tightening if a stricter content
  filter is wanted.

---

<a name="6-persona-harness"></a>
## 6. The four-layer persona harness

**Decision.** The synthetic-learner harness is four strictly-separated layers:
**Layer 1** domain model (deterministic, no LLM — the single source of truth for KCs, correct
procedures, named misconceptions and the wrong answers they produce); **Layer 2** persona
configs (data, not code); **Layer 3** behavioral simulator (deterministic code, no LLM);
**Layer 4** natural-language surface (LLM, additive, *never sees the persona's knowledge
state*). The harness must run with Layer 4 disabled and lose only chat-naturalness — all
evidence intact.

- **Why.** This separation is the answer to "how do you know your synthetic learners aren't
  just LLMs in costume?" Rules decide what happened; the LLM only describes what it looks like.
- **Source.** `PROJECT.md` §4.1; `CLAUDE.md` §8.3. Layer 1 KC registry in commit **71b4ae9**;
  misconception catalog + wrong-answer generators in **27e11dd**; Layer 2 configs (Priya, Sam)
  in **3d8e016**; Layer 3 simulator (SHA-256 per-draw determinism, reads correct values from the
  domain and wrong values from the misconception generators, never recomputes math) in
  **3580525**; the full adversarial roster (Nate, Hugo, Cleo) in **a3837f8**. Layer 4 renderers
  (tutor voice, learner voice), knowledge-state-blind with verbatim fallback, in **00d2380** and
  **895f3cc**.

**Decision.** Each persona gets mandatory TDD behavioral tests (`CLAUDE.md` §2), and the five
personas serve as the *integration suite* for the mastery model: if any persona who should be
denied reaches confirmed mastery, the model is broken.

- **Why.** The personas are the mastery model's adversaries; they are the test that the §3.4
  rules and the transfer probe actually fire.
- **Source.** `PROJECT.md` §4.2, §4.4; `CLAUDE.md` §9. Behavioral tests in the persona commits
  above; the headline result (5/5 personas denied confirmed mastery, with Priya the load-bearing
  case caught only by the transfer probe) in the false-positive harness, commit **b68dc23**.

**Decision (scope, honestly stated).** The roster is five personas and does **not** include an
"anxious quitter" or a "bored advanced learner"; the harness does **not** claim its personas are
validated representations of real students.

- **Why.** Bounded 6-week scope; simulating anxiety without trivializing real emotion is hard;
  the help-responsive archetypes are an explicit v1 exclusion (which is why the proactive A/B
  reports a safety property, not an effect size — see §8).
- **Source.** `PROJECT.md` §4.3, §4.4, §9. Reaffirmed in commits **b68dc23** and **0becfb2**.

---

<a name="7-helpneed-predictor"></a>
## 7. The HelpNeed predictor: data, gate, and the signed-off tuning

**Decision (dataset switch — DataShop → EDM Cup 2023).** The HelpNeed predictor trains on
**EDM Cup 2023 / ASSISTments** action-level clickstream, not the originally-locked CMU DataShop
fraction-arithmetic traces.

- **Why.** The DataShop export proved a hard build-time blocker (large-set generation behind a
  login, no public mirror). EDM Cup 2023 is also ASSISTments fraction-tutor data, carries the
  same four required signals (correctness, response latency, hint usage, attempt count) at the
  action level, and is openly mirrored on OSF (`osf.io/yrwuh`) with no login. The cross-tutor
  calibration gap was already in the design (§7.2), so the switch introduced no new risk.
- **Source.** `PROJECT.md` §3.7, TECH_STACK §5 (both updated on disk 2026-05-27 with the
  original plan + rationale preserved). Switch logged in commit **9e4bc4d** (the EDM Cup parser).

**Decision (the v1 model).** XGBoost behind a stable `predict_proba` seam, trained on
leakage-safe per-turn features (signals from the learner's turns *strictly before* the current
one). The unproductive-state label (HelpNeed=1) = gave up / never solved / floundered (≥3 wrong)
/ hint-dependent (≥2 hints); one wrong try then self-correcting stays *productive*.

- **Why.** A trajectory classifier that learns the path, not the answer; the label matches the
  §3.4 spirit (productive struggle is not failure).
- **Source.** `PROJECT.md` §3.7 (label locked 2026-05-28). Trained in commit **ea74882** —
  holdout **AUC 0.893** (vs 0.851 logistic baseline, 0.572 majority); SHAP top feature
  `turns_since_last_correct`. The model artifact (~280 KB) is committed and loaded once at boot
  (decision in **ac397eb**: commit-the-artifact beats train-on-boot, which fails horizontal
  scaling, and beats S3-hosting, which is premature at this size — `CLAUDE.md` §8.6).

**Decision (sustained-signal gate).** The proactive intervention does **not** fire on a single
threshold-crossing turn. A `SustainedHelpNeedGate(K, threshold)` fires only after **K consecutive
turns at P ≥ threshold**, resetting on any dip.

- **Why.** The §7.5 persona calibration found the dominant feature (`turns_since_last_correct`)
  makes single per-turn readings noisy — a correct answer right after a streak can still read
  high — so acting on one reading would interrupt a learner who just recovered. Razzaq &
  Heffernan (2010) show proactive over-firing hurts.
- **Source.** `PROJECT.md` §3.7 (sustained-signal gate, added 2026-05-28); RESEARCH.md
  §1.7/§7.5. Gate built in commit **168f145** (8 TDD tests; observe-only by default).

**Decision (signed-off tuning — K=3, threshold=0.5).** K and threshold were *swept*, not
hand-tuned. The Slice 5.4 sweep (K ∈ {2,3,4} × threshold ∈ {0.4,0.5,0.6,0.7} against eight
labelled acceptance traces, each encoding one documented gate criterion) found **exactly one**
passing grid point — **K=3, threshold=0.5** — so the sweep *validated* the provisional defaults
rather than overturning them. The user **signed off 2026-05-28**; these are now final tuned
values, not placeholders. τ=0.85 confirmed in the same sign-off.

- **Why.** §3.7 commits Path 2 to honest, reported tuning rather than a guessed constant; a
  swept-and-uniquely-passing grid point is the defensible version of that commitment.
- **Source.** `PROJECT.md` §3.7; RESEARCH.md §9.3. Sweep in commit **0becfb2**; the sign-off
  locked (comment/docstring only, no behavior change — the defaults already held these values)
  in **b21c2f6**.
- **Status — provisional → final.** This is a deliberate revision of the 0.D.5 "tunable in
  weeks 4–5" status: the provisional 0.5 (and the new K param) are now signed-off finals.

**Decision (calibration findings kept, not "fixed").** The 4.3 persona calibration found
HelpNeed and the mastery defense catch *different* failure modes by design (Priya answers
correctly so HelpNeed rates her low — she is the transfer probe's catch, not a help-need
target). The +0.336 separation is carried mostly by Cleo and is honestly relabeled a *wiring
smoke test*, not a model-quality result, because the five personas are the mastery model's
adversaries, not a help-need population.

- **Why.** Reporting the calibration as a quality result would over-claim; the personas were
  never built to validate HelpNeed.
- **Source.** `PROJECT.md` §3.7; RESEARCH.md §7.5. Calibration in commit **edfff15**; live
  observe-only wiring (equivalence test: with/without predictor → identical outcomes, only
  `help_need` differs; sub-100ms inline) in **ac397eb**.

---

<a name="8-proactive-layer-and-the-ab-finding"></a>
## 8. The proactive layer and the honest A/B finding

**Decision.** Build the proactive HelpNeed layer (Path 2 — a deliberate, eyes-open scope
expansion past reactive-only) as a *mechanism*, with the live default **observe-only** (the
proactive arm OFF). The first-fire intervention is the pre-written conceptual nudge rendered as
an inline assertion (refuse-rule 6); the LLM-mediated partial worked step lands later (Slice 5.6)
— no LLM in the turn loop.

- **Why.** The mechanism can be built and demoed without claiming "it helps" until an A/B
  measures outcomes; observe-only is provable (arm ON == arm OFF on every outcome).
- **Source.** `PROJECT.md` §3.7, §3.8; RESEARCH.md §1.8. Gate + observe-only wiring in commit
  **168f145**; the inline-assertion surface + `?proactive=1` opt-in in **4ca7b56**.

**Decision (the honest A/B finding — safety, not effect size).** The Slice 5.4 A/B runs each
persona reactive-only vs reactive+proactive and finds *identical* mastery outcomes (5/5). This
certifies a **safety property** — the proactive arm can never corrupt the deterministic mastery
path — **not** an effect size. We explicitly do **not** claim a proactive benefit, because that
needs a help-responsive population, and those archetypes are an explicit v1 exclusion (reported
as a v2 item, not papered over).

- **Why.** This is exactly the "report honestly regardless of which wins" commitment §3.7 makes;
  claiming an effect we cannot measure would undermine the submission's credibility.
- **Source.** `PROJECT.md` §3.7 (A/B commitment), §9; RESEARCH.md §9.3. Commit **0becfb2**.

---

<a name="9-baseline-comparison"></a>
## 9. The three-arm baseline comparison

**Decision.** Compare three arms over the same five personas and the same problems: (1) our
adaptive UI, (2) a **chat baseline** (a generic conversational LLM tutor with none of our
machinery — the PRD's named weak-submission shape, modeled on Varsity Tutors' AI Tutor),
(3) a **static worked-example baseline** (a pre-rendered linear walkthrough, Homework-Help
style). Headline metric: false-positive mastery rate per arm. Pre-registered before any run.

- **Why.** A real comparison against two honest baselines is what turns the submission from a
  demo into evidence; pre-registration protects against post-hoc rationalization.
- **Source.** `PROJECT.md` §3.11; RESEARCH.md §1.6, §2.1, §9. Chat arm in commit **6212eb6**;
  static arm in **9beadea**; the headline harness in **20caf60**; the on-screen dashboard
  (`?eval=1`) in **75c3c1c**; the other five metrics in **7d2129d**.

**Decision (the pre-registration miss, reported).** Chat was pre-registered at 4–5/5
false-positive mastery; the live run came in at **2/5** — exactly the "chat stingier than
expected" case §9 had pre-named. The chat tutor denies the personas who give *visibly wrong*
answers (Sam, Nate, Cleo) but is fooled by the ones who produce *right answers without
understanding* (Hugo via hints, Priya by rote) — precisely the failure modes our rules and the
S5 probe are built to catch (adaptive: **0/5**). Reported as a *sharper* contrast, not a weaker
one.

- **Why.** Reporting the pre-registration-vs-actual gap is itself the evidence; hiding the miss
  would defeat the purpose of pre-registering.
- **Source.** `PROJECT.md` §3.11; RESEARCH.md §9.1. Live chat result recorded in commit
  **b30cd39**; the per-metric "No mechanism" honesty (chat denies Sam/Cleo on visibly-wrong
  answers, not via a mechanism it has) in **7d2129d**.

---

<a name="10-persistent-learner"></a>
## 10. The persistent-learner initiative (decided 2026-05-28)

**Decision (the initiative).** Make the learner *continuous* and capture the *full* picture of
how they work, under one governing principle — **"capture richly, act conservatively"**
(architectural invariant 9): all of this feeds *understanding* (HelpNeed, mastery, eval) and
does **not** widen what the UI does automatically. "Hyperresponsive" (the PRD title) means the
*model* understands deeply, not a twitchy interface. Three pillars, phased PL.1→PL.4 with
LangSmith tracing in parallel.

- **Why.** To help a student well, the tutor must understand *how* they work a problem (not just
  right/wrong) and keep that understanding continuous across devices and absences.
- **Source.** `PROJECT.md` §3.12; ARCHITECTURE.md §15, §14 (invariant 9). Initiative recorded
  (design + plan only, no code) in commit **a93d972**.

### 10.1 Persistence + resume (PL.1)
- **Decision.** A repository layer (`db/repositories.py`, the only place queries live) +
  live-loop persistence that runs strictly *after* the turn response is computed (invariant 7)
  and never blocks/breaks a turn. **Alembic** is now the migration authority (`create_all`
  stays the test/bootstrap path). Schema additions: `Session.route_key` (non-fragile goal-KC
  recovery on resume) and `MasteryState.confirmed` (durable "mastered = CONFIRMED" across
  restart). **Resume is mastery-level** — rehydrates per-KC BKT priors + the confirmed set;
  exact in-progress-problem rehydration is *deferred* (would need replaying the observation log;
  faking it would corrupt the mastery evidence).
- **Why.** Persistence must never sit on the decision path; equivalence (response identical
  with/without persistence) is the load-bearing property and is tested.
- **Source.** `PROJECT.md` §3.12; commit **5adf024**. Revises the Slice-1.8 `create_all`-only
  decision (retiring TODO 1.8.3) and the original "no auth in v1" via the additive identity path
  (see 10.3).

### 10.2 Raw behavioral capture (PL.2)
- **Decision.** An append-only `interaction_event` store (portable JSON, sqlite + Postgres) fed
  by a `/events` endpoint that is *separate* from `/turn`, returns 202 immediately, swallows all
  errors, and never touches verify/mastery/policy. A frontend `telemetry/` layer captures how a
  learner works a problem (problem-presented, time-to-first-interaction, answer edits /
  number-line moves, hint requests, submit latency, focus/blur, idle) and flushes
  fire-and-forget.
- **Why.** Telemetry must never block or break a turn (invariant 7) and only records — it never
  changes what the UI does (invariant 9). This is the stream HelpNeed v2 derives from.
- **Source.** `PROJECT.md` §3.12; ARCHITECTURE.md §15.3. Backend ingest in commit **842b3ec**;
  frontend telemetry in **940e7d2**; event set expanded in **b000cdc**.

### 10.3 Google OIDC accounts + cross-device continuity (PL.3)
- **Decision.** Optional **Google Sign-In (OIDC)** layered *on top of* — not replacing — the
  anonymous session-id flow. The backend verifies Google ID tokens with Google's official
  verifier (no hand-rolled JWT/crypto), keys the learner to the Google `sub`, and stores **no
  passwords**. **Invariant 8:** the verified identity never reaches the mastery model, policy, or
  LLM (`process_turn` stays identity-free; the turn decision cannot see who the learner is) —
  enforced by an AST-based import-guard test. Same login on any device resolves the same state.
- **Why.** Delegating to Google is materially safer than rolling our own auth (no credential
  storage; MFA/recovery/breach handled; OWASP "don't build your own auth"). Conservative auth
  posture: every verification failure collapses to one opaque error with no side channel.
- **Source.** `PROJECT.md` §3.12; ARCHITECTURE.md §14 (invariant 8); TECH_STACK §9. Backend in
  commit **be040bd**; frontend Google sign-in + app-wide bearer-token threading in **ebefa75**.
- **Revision — "no auth in v1" → Google OIDC.** The Slice-1.8 / TECH_STACK §9 "no auth in v1"
  decision is changed by PL.3; the change is additive (with no client id configured the app
  behaves exactly as before — the anonymous/guest path), so it breaks nothing. TECH_STACK §9
  updated on disk; **be040bd** is the tracked record (`CLAUDE.md` §8.4).
- **Revision — COPPA posture (flagged → signed off = BOTH).** The under-13 consent posture was
  flagged NOT-locked in §3.12 (option (a) Workspace-for-Education only vs (b) also 13+ personal
  accounts). Signed off 2026-05-28 as **BOTH** (Workspace-for-Education for under-13 + 13+
  personal accounts with a consent notice; data minimization + retention policy apply
  regardless). Recorded in commit **be040bd**.

### 10.4 HelpNeed v2 from the event stream (PL.4)
- **Decision.** Derive the HelpNeed feature vector from the PL.2 event stream, retiring v1's two
  live *proxies*: `recent_attempts_mean` becomes the real `submit` count (was constant 1.0), and
  `recent_request_answer_rate` becomes a real give-up signal (hint-escalation to worked-step
  depth, was the hint rate); plus two columns v1 could not express (revision count, time-to-first
  -interaction). Leakage-safe (features from prior episodes only).
- **Why.** The v1 proxies were documented train/serve compromises (the cross-tutor gap); the
  event stream lets them be replaced with real tutor-native signals.
- **Status — honestly partial.** **No trained/validated v2 model ships.** We have no real-learner
  event data yet (`PROJECT.md` §9 limitation), so PL.4 is the *pipeline* the captured events will
  feed; training + a 5.4-style re-validation await that data. v2 stays observe-only / gated
  (invariant 9). A carried-forward limitation: the event stream has no SymPy correctness verdict
  (that's on the Turn row), so the derived error/unproductive rates are a help-seeking *subset* of
  the §3.4 label until joined — a documented follow-up.
- **Source.** `PROJECT.md` §3.12, §9; RESEARCH.md §7.5. Commit **39e21cd**.

### 10.5 LangSmith tracing (PL.0)
- **Decision.** An opt-in, env-gated `TracedProvider` wrapping the LLM provider, confined to
  `llm/`; default-off so tests and any run without the flag are unaffected; it only *observes* —
  never changes the completion returned.
- **Source.** `PROJECT.md` §3.12; TECH_STACK §6; commit **09e1061**.

---

<a name="11-cold-start-and-product-surface"></a>
## 11. Cold start, content coherence, and the product surface

**Decision (register arc).** The landing and cold-start surfaces use a *warmer*, mascot-led
"world" register; the in-problem surfaces (S1–S5) stay calm/editorial. The warmth is a bridge,
not the working tone. Meaning is always carried by icon + label + position, not by hue alone.

- **Why.** Onboarding warmth invites a child in; the working surfaces stay calm and credible.
- **Source.** `PROJECT.md` §8 (0.D.2), §3.5; PRODUCT.md (register arc). Landing in commit
  **8ee3fe2**; the "world" cold-start in **a45729a** (and polish through **6ee67bf**…**f25af8** ).

**Decision (product-coherence audit — answer surface always matches the question).** A KC×surface
audit found and fixed several question/widget mismatches: the equivalence yes/no probe was
rendering a fraction editor (**a7dbcf2**); the equivalence fill-the-top item over-asked two boxes
when one number was wanted (**c64d116**); the answer widget is chosen by the *answer's nature*
(the KC), not the surface state, so a number-line statement never renders a fraction box
(**20835f3**, **6ccead5**); the yes/no mode label states what it asks (**f55f176**).

- **Why.** A live surface that asks a question its widget cannot answer is incoherent and traps
  the learner; write for the reader (`CLAUDE.md` §8.5).
- **Source.** `PROJECT.md` §3.1, §3.5; ARCHITECTURE.md §10. Commits as listed.
- **Flagged deferral.** Real AREA_MODEL / FractionBar live rendering is deferred — that item is
  load-bearing for Nate's rule-2 attack in the persona harness, so wiring it live now would be
  dead UI and would risk the §8 harness (**a83b589**).

**Decision (one source of truth for the wire).** TypeScript types are generated from the Pydantic
schemas, so the frontend cannot drift from the backend contract.

- **Source.** TECH_STACK §2; commit **ee94d5d** (closing the hand-written-types deferral). The
  generation immediately caught a wrong optionality on `TurnResponse.hint`.

---

<a name="12-infrastructure"></a>
## 12. Infrastructure and cost controls

**Decision (monorepo + toolchain).** pnpm workspace (frontend + shared-types + infrastructure) +
a separate uv-managed Python backend, laid out per ARCHITECTURE.md §13; ruff + `mypy --strict` +
pytest on the backend, ESLint + Prettier + Vitest + strict tsconfig on the frontend; GitHub
Actions CI; docker-compose Postgres for local parity.

- **Source.** `CLAUDE.md` §6, §7; TECH_STACK §8; commit **9d06c89**.

**Decision (cost guardrails — tightened to $50/mo).** A **$50/month** AWS budget with email
alerts at 50% / 80% / 100% / forecasted-100%, plus Cost Anomaly Detection emailing on any spike
≥ $10. Tightened from the original $100/$200/$500 plan per team direction; created via CLI for
immediate protection, to be codified as a CDK BudgetStack at Slice I (do not double-create).

- **Why.** A 6-week pitch budget; immediate protection over deferred IaC.
- **Source.** `CLAUDE.md` §10; TECH_STACK §7; commit **1685c8e**.
- **Status — partly deferred.** Full CDK stacks (Network/Database/App/Ml, the BudgetStack) are a
  later slice; `infrastructure/` is a Phase-0 placeholder (**9d06c89**, **1685c8e**). Deployment
  to AWS is not represented as complete in the tracked history at the time of this log.

---

<a name="13-index-of-revisions"></a>
## 13. Index of revisions (decisions that changed)

| Decision | Original | Revised to | Why | Commit(s) |
|---|---|---|---|---|
| HelpNeed training data | CMU DataShop fraction traces | EDM Cup 2023 / ASSISTments | DataShop export was a build-time blocker (login, no mirror); EDM Cup carries the same four signals, open on OSF | **9e4bc4d** |
| Cold-start equivalence item answer form | fraction editor (type "2/3") | yes/no widget + yes/no verifier path | the item is a relational judgment, not a fraction to type — the widget over-asked | **a7dbcf2** |
| Proactive gate params | provisional τ=0.85, threshold=0.5, no K | signed-off final **K=3, threshold=0.5**, τ=0.85 confirmed | the 5.4 sweep found these the unique passing grid point; user signed off 2026-05-28 | **0becfb2**, **b21c2f6** |
| Live "mastered" meaning | provisional (§3.4 rules only) | CONFIRMED (provisional AND S5 transfer probe passed) | the live claim must match the headline "we don't fake mastery" | **b343a06** |
| Auth | "no auth in v1" (TECH_STACK §9) | optional Google OIDC, additive + identity-firewalled | continuous cross-device learner; delegating to Google is safer than rolling our own | **be040bd** |
| COPPA consent posture | flagged, not locked (a vs b) | **BOTH** — Workspace-for-Education + 13+ personal w/ notice | signed off 2026-05-28 | **be040bd** |
| Persistence | `create_all`-only, in-memory sessions (Slice 1.8) | Alembic-authoritative migrations + DB-backed session/mastery persistence + mastery-level resume | persistent, resumable learner (PL.1) | **5adf024** |
| HelpNeed feature columns | two live proxies (attempts≡1, request≡hint) | real signals derived from the event stream (v2 pipeline) | retire the documented train/serve proxies | **39e21cd** |
| Cost budget | $100 / $200 / $500 plan | hard **$50/mo** + $10 spike alerts | team direction | **1685c8e** |

---

*End of decision log. For the full tracked rationale behind any entry, run `git show <hash>`;
the commit message is the authoritative record (`CLAUDE.md` §1, §3).*
