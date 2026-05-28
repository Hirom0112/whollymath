# PRD Deliverable Checklist — WhollyMath

> **Purpose.** This is the reviewer-facing map from every PRD requirement to its
> home in the codebase. The PRD is *Hyperresponsive Mastery UI* (Gauntlet
> Challenger Project, Nerdy / Varsity Tutors). We treat the on-disk planning doc
> `PROJECT.md §2` as the faithful capture of the PRD's required deliverables and
> features (it is gitignored; see CLAUDE.md §1 — the PRD is the contract, and
> PROJECT.md is its capture). Every row below traces a PRD ask to a real file
> path you can open, and marks honestly whether it is **Met**, **Partial**, or
> **Deferred**.
>
> Status key:
> - **Met** — implemented to a working, demonstrable bar; has a home and runs.
> - **Partial** — a real home exists and works, but a named piece is scoped down
>   or simplified. The note says exactly what is missing.
> - **Deferred** — intentionally not built in v1; named here and in the
>   limitations memo so it does not look like an oversight.
>
> All paths are repo-relative to the project root unless noted.

---

## A. Required deliverables (PROJECT.md §2, "Verbatim required deliverables")

| # | PRD deliverable | Where it lives | Status & honest note |
|---|---|---|---|
| 1 | **Working prototype** | `backend/app/` (FastAPI service, turn loop in `api/service.py` + `tutor/session.py`) and `frontend/src/` (React app, `pages/Tutor.tsx`). End-to-end live session works locally. | **Met (local).** Runs via `docker-compose` (Postgres) + `uvicorn` + `vite`. Not deployed to a public URL — see deliverable 14 (Deployment) and Deferred items. |
| 2 | **Demo learning flow** | The live cold-start → tutor → mastery → S5 transfer flow: `frontend/src/pages/ColdStart.tsx` → `frontend/src/pages/Tutor.tsx`; backend `tutor/session.py`. Narrated, reproducible walkthrough: **`DEMO.md`** (Slice 6.1). | **Met.** The flow is built and demonstrable; `DEMO.md` is the screen-by-screen walkthrough (setup, the persona-defense beat, talking points). |
| 3 | **UI adaptation policy** | `backend/app/policy/transitions.py` (the §3.6 transition table), `policy/surface_states.py` (S1–S5 enum), `policy/refuse_rules.py` (§3.8 refuse-rules), `policy/scheduler.py` (interleaving), `policy/intervention_gate.py` (sustained-signal gate). Frontend mirror: `frontend/src/pages/Tutor.tsx` (`STATE_LABEL`, transition handling). | **Met.** All five states, the reactive transition table, the refuse-rules, and the proactive gate have real homes and are exercised in the live loop. |
| 4 | **Explanation of chosen subject and learner task** | `PROJECT.md §3.1` (subject: fraction equivalence & operations), `§3.2` (6th–7th grade audience); `ARCHITECTURE.md §4` (the learning domain); summarized in `README.md`. Domain encoded in `backend/app/domain/knowledge_components.py` (5 KCs). | **Met.** Subject, scope boundaries, and learner task are documented and reflected in the 5-KC domain model. |
| 5 | **Mastery model** | `backend/app/mastery/mastery_model.py` (per-KC BKT + the four §3.4 augmentation rules: ≥2 representations, ≥1 unscaffolded correct, interleaved-weighted, engagement floor) + transfer-probe confirm-gate in `tutor/transfer_probe.py` / `tutor/live_transfer_probe.py`. | **Met.** Two-stage model (§3.4 rules → S5 transfer confirm). "Mastered" means CONFIRMED, never bare provisional (see git `b343a06`). |
| 6 | **Modality and sensor rationale** | `PROJECT.md §3.3` (input: direct manipulation + text entry; output: dynamic visual workspace + text feedback; camera scoped out). Implementations: `frontend/src/workspace/` — `FractionBar.tsx`, `NumberLine.tsx`, `SymbolicEditor.tsx`, `YesNo.tsx`. | **Met.** ≥2 input modes (drag/click manipulation + typed entry) and ≥2 output modes (multi-representation SVG workspace + concise text feedback) are built. Camera input is an explicit, documented Deferred stretch (limitations). |
| 7 | **Content validation approach** | `backend/app/domain/verifier.py` (SymPy answer/step verification — the only place SymPy lives), `domain/hint_validation.py` (hint symbolic content SymPy-validated before display), `persona_surface/hint_renderer.py` (constrained template slot-fill). Rationale: `PROJECT.md §3.10`, `ARCHITECTURE.md §9`. | **Met.** All math correctness is SymPy; LLM never decides correctness (CLAUDE.md §8.2). The diagnostic-gem bank lives in `domain/problem_generators.py` alongside the procedural generator. |
| 8 | **Research notes** | `RESEARCH.md` (72 KB; the cited research backing every non-trivial design choice — interleaving, hint-avoidance, fractions-as-algebra-predictor, HelpNeed training-data provenance, A/B sweep results). | **Met.** Substantial and current. Gitignored per CLAUDE.md §1, on disk for the team/reviewer. |
| 9 | **Evaluation method** | `backend/app/eval/three_arm_comparison.py` + `eval/false_positive_harness.py` (the headline false-positive-mastery metric across 5 personas), `eval/proactive_ab.py` (reactive vs reactive+proactive sweep), `eval/helpneed_calibration.py`. Pre-registration recorded in `RESEARCH.md`. On-screen dashboard: `frontend/src/pages/EvalComparison.tsx`. | **Met.** Three-arm protocol with pre-registration and an on-screen results view (`?eval=1`). |
| 10 | **Comparison against static or chat baseline** | Both baseline arms are real: `backend/app/eval/chat_baseline.py` (GPT/LLM-in-a-chat-box arm) and `eval/static_worked_example.py` (deterministic static-walkthrough arm), compared in `eval/three_arm_comparison.py`. | **Met.** Both PRD-named baselines exist and run. Note: the static arm is N/A on some mastery metrics by design (it cannot declare mastery); this is intended, not a gap. |
| 11 | **Transfer assessment / transfer moment** | `backend/app/tutor/transfer_probe.py` (S5 probe + transfer-item generation: representation-transfer + error-finding, per §3.9), `tutor/live_transfer_probe.py` (live confirm-gate), surface state `S5_transfer_probe` in `policy/surface_states.py` + frontend (`Tutor.tsx`, `isProbe`). | **Met.** S5 is both the transfer moment in the UI and the gate that turns provisional mastery into confirmed. |
| 12 | **Decision log** | Consolidated artifact: **`DECISION_LOG.md`** (Slice 6.2), assembled from the authoritative tracked entries — the git commit history (CLAUDE.md §3) — plus the planning-doc rationale (`PROJECT.md §3`/`§8`/`§10`). | **Met.** `DECISION_LOG.md` organizes every major decision by theme with Decision / Why / Source (real commit short-hash) / revision status, including the decisions that changed. |
| 13 | **Limitations memo** | Consolidated artifact: **`LIMITATIONS.md`** (Slice 6.3), sourced from `PROJECT.md §9` + `RESEARCH.md §4/§7.5/§9.3` + the honestly-flagged build gaps. | **Met.** `LIMITATIONS.md` covers validation, pedagogical model, ML/HelpNeed, scope, accessibility, privacy/auth, and operational limits — each with what / why-accepted / v2-path. |
| 14 | **(Deployment)** AWS infra-as-code | `infrastructure/` (CDK skeleton: `bin/app.ts`, `lib/index.ts`), conventions in `infrastructure/README.md` and CLAUDE.md §10. | **Deferred.** The CDK app is a skeleton (~5 lines); there is **no live AWS deployment** and CI (`.github/workflows/ci.yml`) runs lint/type-check/test only, no `cdk deploy`. The prototype runs locally. This is a known, named cut for the 6-week build. |

---

## B. Required prototype features (PROJECT.md §2, "Verbatim required prototype features")

| # | PRD feature | Where it lives | Status & honest note |
|---|---|---|---|
| 1 | **One tightly scoped learning goal** | `backend/app/domain/knowledge_components.py` (exactly 5 KCs: identify-equivalent, common-denominator, add, subtract, number-line placement). Scope locked in `PROJECT.md §3.1`. | **Met.** Positive fractions, equivalence + add/sub + placement; no multiply/divide. |
| 2 | **≥2 input modes** | Direct manipulation: `frontend/src/workspace/FractionBar.tsx`, `NumberLine.tsx` (drag/click). Text entry: `SymbolicEditor.tsx`; relational yes/no: `YesNo.tsx`. | **Met.** Two genuine input channels (manipulation + typed/selected entry). |
| 3 | **≥2 output modes** | Dynamic visual workspace (multiple representations: symbolic, area-model bars, number line) in `frontend/src/workspace/`; concise text feedback rendered in `frontend/src/pages/Tutor.tsx`. | **Met.** |
| 4 | **Dynamic surface that changes on learner intent/state/understanding** | The 5 surface states + reactive transitions: `backend/app/policy/transitions.py`, `policy/surface_states.py`; surface chosen per problem by `surface_format` and driven live in `frontend/src/pages/Tutor.tsx` (`setSurfaceState`, `next_surface_state`). | **Met.** Surface changes are driven by error type, hint use, consecutive errors, and BKT — between problems, never mid-problem (refuse-rule 1). |
| 5 | **Direct manipulation, not passive components** | Custom interactive SVG: `frontend/src/workspace/FractionBar.tsx` (drag pieces), `NumberLine.tsx` (slide marker). | **Met.** Components are manipulable, not read-only renders. |
| 6 | **Clear policy balancing responsiveness with stability** | Refuse-rules `backend/app/policy/refuse_rules.py` (no mid-problem morph, no react-to-pause, no auto-help in first 60s, always-labeled transitions) + sustained-signal gate `policy/intervention_gate.py` (K=3 @ thr 0.5). Rationale `PROJECT.md §3.8`, `ARCHITECTURE.md §14`. | **Met.** This directly answers the PRD's "chaotic interface that constantly morphs is not a good result" caution. |
| 7 | **Mastery model defended against guessing, pattern-matching, over-scaffolding** | `backend/app/mastery/mastery_model.py` (engagement floor → guessing; ≥2 representations + interleaving → pattern-matching/format-matching; ≥1 unscaffolded correct + hint downweighting → over-scaffolding). Adversarially validated by the 5 personas in `backend/app/personas/` + `eval/false_positive_harness.py`. | **Met.** Each defense maps to a named persona (Cleo, Nate/Sam, Hugo). The false-positive harness denies mastery to all 5 adversarial personas (5/5) at τ=0.85. |
| 8 | **Transfer moment or assessment** | Same as deliverable 11 — `backend/app/tutor/transfer_probe.py` / `live_transfer_probe.py`, S5. | **Met.** |
| 9 | **Evidence adaptive UI beats a static / chat baseline** | `backend/app/eval/three_arm_comparison.py` + the two baseline arms (`chat_baseline.py`, `static_worked_example.py`); results surfaced in `frontend/src/pages/EvalComparison.tsx`. | **Met (synthetic evidence).** Evidence is generated against the 5 synthetic personas, **not real students** — explicitly scoped in the limitations memo (PROJECT.md §9). |

---

## C. Cross-cutting PRD themes (verification against PROJECT.md §2/§3/§4)

These are the load-bearing systems the PRD's themes depend on. Listed separately so a reviewer can confirm the *defensibility story*, not just feature presence.

| Theme | Where it lives | Status & honest note |
|---|---|---|
| **Hyperresponsive / adaptive mastery UI (S1–S5 + reactive policy)** | `backend/app/policy/` (states, transitions, refuse-rules, scheduler, gate); `frontend/src/pages/Tutor.tsx`. | **Met.** All 5 states reachable live; transitions labeled. |
| **Defensible two-stage mastery model** | `mastery/mastery_model.py` (§3.4 four rules) → `tutor/transfer_probe.py` (S5 confirm). | **Met.** "Mastered = CONFIRMED" enforced. |
| **Persona harness as integration tests / false-positive defense** | `backend/app/personas/` (`persona_config.py`, `nate.py`, `priya.py`, `hugo.py`, `sam.py`, `cleo.py`, `simulator.py`, `registry.py`, `run.py`) — deterministic Layers 1–3; LLM surface is additive in `persona_surface/learner_voice.py` (Layer 4, off the evidence path). | **Met.** 5 personas, deterministic simulator (CLAUDE.md §2 mandatory-TDD system); Layer 4 never sees knowledge state. |
| **Content validity (SymPy + diagnostic-gem bank)** | `domain/verifier.py` (SymPy), `domain/problem_generators.py` (procedural generator + handpicked diagnostic-gem items), `domain/misconceptions.py` (named wrong-answer patterns). | **Met.** |
| **HelpNeed prediction (XGBoost, sub-100ms)** | `backend/app/helpneed/predictor.py` (XGBoost + logistic baseline, single-row sub-100ms path), trained artifact committed at `helpneed/artifacts/helpneed_v1.joblib`, training pipeline `helpneed/train_pipeline.py`, EDM-Cup parse `helpneed/parse_edmcup.py`, labels `helpneed/labels.py`, live features `helpneed/live_features.py`. v2 feature derivation from the event stream in `helpneed/events_features.py`. | **Partial.** **v1 is trained, committed, and integrated** (holdout acc 0.837 / AUC 0.893, per RESEARCH.md §7). **v2** has its event-stream feature derivation built (`events_features.py`, Slice PL.4) but is **not a trained, deployed model** — it is the pipeline groundwork, honestly not a shipped v2. The live proactive arm ships **observe-only by default** (mechanism built; the "it works" claim is gated on the A/B, per PROJECT.md §3.7). |
| **Evaluation method (three-arm baseline comparison)** | `backend/app/eval/three_arm_comparison.py`, `chat_baseline.py`, `static_worked_example.py`, `false_positive_harness.py`, `proactive_ab.py`; dashboard `frontend/src/pages/EvalComparison.tsx`; `api/eval_view.py`. | **Met.** Pre-registered, with on-screen results. Evidence is synthetic-persona-based (see B9). |
| **Modality / sensor rationale** | `PROJECT.md §3.3`; workspace components in `frontend/src/workspace/`. | **Met** (camera deferred — see B-features and limitations). |
| **Research grounding** | `RESEARCH.md`; citations referenced inline in code/commits. | **Met.** |
| **Decision log** | `DECISION_LOG.md` + git history (tracked) + `PROJECT.md §3`/`§10`. | **Met** — consolidated `DECISION_LOG.md` written (see A12). |
| **Persistent learner (accounts, continuity, behavioral capture)** *(§3.12 — a deliberate scope expansion past the core PRD, not a PRD requirement)* | Auth: `backend/app/auth/google.py` + `api/auth_routes.py`, frontend `src/auth/`. Persistence: `db/repositories.py`, `db/models.py`, Alembic migrations. Behavioral capture: `events/ingest.py`, frontend `src/telemetry/`. LLM tracing: `llm/tracing.py`. | **Met (as built scope).** Google OIDC, session/mastery resume, off-loop event ingest, and LangSmith tracing all have real homes (Slices PL.0–PL.4). This is additive to the PRD, recorded as architectural invariant 9 (ARCHITECTURE.md §15). |

---

## D. Honest gaps and deferrals (consolidated)

These are the items above marked Partial/Deferred, gathered so nothing hides:

1. **AWS deployment — Deferred.** `infrastructure/` is a CDK skeleton; no live cloud deploy; CI does not `cdk deploy`. Prototype runs locally only. (A14)
2. **HelpNeed v2 — Partial.** Only v1 is a trained/committed/integrated model. v2 is event-stream feature-derivation groundwork, not a trained deployed model. (C: HelpNeed)
4. **Proactive arm ships observe-only by default — Partial (by design).** The gate + inline-assertion mechanism are built; the "it helps" claim is gated on the A/B per PROJECT.md §3.7. (C: HelpNeed)
5. **Evidence is synthetic, not real-student validated — Partial (by design).** All baseline-comparison and false-positive evidence is generated against the 5 synthetic personas. (B9, C: Evaluation) — explicitly in the limitations memo.
6. **Camera input modality — Deferred.** Designed-for in the architecture, not shipped in v1. (B-features 2, PROJECT.md §3.3/§9)
7. **Within-session mastery only — Deferred.** No spaced-repetition / retention-over-time modeling in v1; v2 sketch in PROJECT.md §9. (PROJECT.md §9)
8. **Cut personas — Deferred (by design).** Anxious-quitter and bored-advanced personas intentionally excluded (PROJECT.md §4.3, §9).
9. **Accessibility — Partial.** Mouse fallback + colorblind-safe palette considered; screen-reader support explicitly out of scope (PROJECT.md §9).

---

## E. Deliverables index (navigation for the reviewer)

Where to find each submission document.

| Document | Path / source | Status |
|---|---|---|
| **This checklist** | `PRD_CHECKLIST.md` (tracked) | Written |
| **Architecture reference** | `ARCHITECTURE.md` (tracked) — every layer, the turn loop, invariants | Written |
| **README / setup** | `README.md` (tracked) | Written |
| **Decision log** | `DECISION_LOG.md` (tracked) — assembled from git history (canonical) + `PROJECT.md §3`/`§8`/`§10` | Written |
| **Limitations memo** | `LIMITATIONS.md` (tracked) — from `PROJECT.md §9` + `RESEARCH.md §4/§7.5/§9.3` | Written |
| **Demo walkthrough** | `DEMO.md` (tracked) — reproducible screen-by-screen flow + talking points | Written |
| **Research notes** | `RESEARCH.md` (on disk, gitignored per CLAUDE.md §1) | Written |
| **Planning / decisions (internal)** | `PROJECT.md`, `TECH_STACK.md`, `Nerdy.md` (on disk, gitignored) | Written |

> Note on gitignored docs: `PROJECT.md`, `TECH_STACK.md`, `RESEARCH.md`, and
> `Nerdy.md` are intentionally untracked internal planning docs (CLAUDE.md §1).
> Being untracked does not lower their authority. For the *tracked* decision-log
> trail a reviewer can see in the repo, read the git commit history — every
> commit message is a decision-log entry (CLAUDE.md §3).
