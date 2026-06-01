# AGENT_TEAM.md — the multi-agent build of WhollyMath (T1's view + handoff)

> Local planning doc (not pushed). Written by **T1** on 2026-05-30. Doubles as the T1 handoff:
> what we're building, what's done, what's left, the team roles, and how to coordinate.

---

## 0. What we are trying to accomplish

**WhollyMath** is the *Hyperresponsive Mastery UI* — a 6th-grade math tutor (Gauntlet/Nerdy pitch
project) whose thesis is a **defensible mastery model + a hyper-reactive UI**, driven by deterministic
code (SymPy for math, XGBoost for HelpNeed), with the LLM used only for natural-language surface text.
The contract is the PRD; the locked decisions live in the (gitignored) `PROJECT.md` / `TECH_STACK.md` /
`RESEARCH.md` / `CURRICULUM_STANDARD.md`; the rules for *how we build* live in `CLAUDE.md` (tracked).

**The current phase = the Grade-6 CONTENT BUILD.** The engine is built and proven on 5 fraction KCs;
the curriculum spans ~9 units / ~47 lessons / ~30 more KCs. Until a KC has content (generator,
verifier path, misconception, hints, worked example, lesson spec, prereqs), it can't be played,
mastered, or remediated. So the content build is the critical path to a product that does more than
the 5 fraction lessons. **Immediate driver:** a fresh student dead-ended on Unit 1 (Ratios) because it
had zero playable lessons — the owner chose to *build the content* (not re-sequence units).

---

## 1. Is an agent-team the right structure? (the lesson learned)

**Yes for the content build — with worktree isolation.** Today three terminals (T1/T2/T3) share ONE
working tree and "stage only your own files." That works when lanes edit *different* files. It BROKE
during the content build because **every new KC edits the same ~8 registry files**
(`knowledge_components`, `problem_generators`, `verifier`, `misconceptions`, `prerequisites`,
`lesson_spec`, `scheduler`, `hints`, `worked_example`) + the same shared tests. Two agents editing
those concurrently in one tree = last-write-wins clobbering (git only mediates across *branches/
clones*, not within one working tree). We hit exactly that: T1 (percent) and T2 (multiply_fractions)
interleaved and the suite went red; it had to be salvaged into one combined commit.

**Recommended structure going forward:**
- **Worktree per lane**: `git worktree add ../wm-<lane> -b <lane>-branch`. Each builder works isolated;
  an **integrator** (T1) merges branches and owns the shared-registry reconciliation (the invariants
  `LIVE_KCS == registry == KC_PREREQUISITES == SPINE_ORDER`, the bank-vs-built test sets).
- Or a true **orchestrated team / workflow**: a coordinator fans out one-KC builders (parallel,
  independent design), then serializes the registry integration through the integrator.
- Either way: **commit per-KC immediately** so the uncommitted-overlap window stays tiny.

The current shared-tree model is fine for lane-*separated* work (it served us well until the lanes
converged on the registry files).

---

## 2. The team (roles)

| Agent | Lane | Owns |
|---|---|---|
| **T1 (me)** | backend / domain | KCs, problem generators, SymPy verifiers, misconceptions, hints, worked examples, lesson specs, the prerequisite/spine graph, policy, the tutor API, the CCSS→KC map, the persona-bot data runner. **Integrator** for the shared registry files. |
| **T2** | HelpNeed model + Unit-2 content | XGBoost re-fit, per-KC validation, Tier-2 `trustworthy_kcs` gating; now building Unit-2 numeric KCs (multiply/divide fractions, gcf_lcm, decimals). |
| **T3** | frontend | `frontend/` — workspace widgets, units/lesson shell, camera/OCR beat, surface rendering. Consumes T1 wire contracts; maintains the frontend `LIVE_KCS` + `selectWidget`. |

**Coordination channel:** `T1_T2_COORDINATION.md` (repo root, gitignored, shared via the tree). Append
at the bottom, signed, via `cat >>` (race-safe; the Edit tool fights concurrent edits). Read the last
~40 lines before posting.

---

## 3. T1's role + what I've done this session

**Role:** backend/domain builder **and** the integrator who owns the shared registry invariants.

**Committed to `main` this session (local, NOT pushed — owner gates the push to GitHub+GitLab):**

| Commit | What |
|---|---|
| `c073623` | **Persona-bot data runner** — un-stubbed `student_bots.py`: drives the 5 personas through the real `SessionStore` with persistence → genuine Learner/Session/Turn/MasteryState rows, rostered to the demo teacher. Idempotent. + `SessionStore.current_problem()` accessor. |
| `632e551` | **Simulator yes/no support** — `simulate_action` answers yes/no items (number-line comparisons + the probe's error-finding step), per knowledge mode. Unblocks mastery confirmation. |
| `ff0b13a` | **Capable Cora** — the 6th persona, the positive control (BOTH mode), the only one who CONFIRMS mastery. Gives the demo a real top student. |
| `f39c6b0` | **KC_unit_rate** — first Grade-6 lesson + the content-build TEMPLATE (the 12-touchpoint pattern). |
| `c89c727` | **KC_equivalent_ratios** — additive-vs-multiplicative misconception. |
| `87ac7e8` | **KC_percent (T1) + KC_multiply_fractions (T2)** — salvaged combined commit after the shared-tree collision; also the domain fix that built grade-6 KCs stay remediation sources (only the foundation-5 are terminal). |

**Suite:** 1572 passed / 1 skipped; ruff + mypy --strict clean. **LIVE_KCS = 9** (5 foundation +
unit_rate, equivalent_ratios, percent, multiply_fractions).

**The KC build template (copy `KC_unit_rate`) — 10 source touchpoints + the test-threading:**
see `T1_T2_COORDINATION.md` (2026-05-30 "Grade-6 content build STARTED" entry) and the memory note
`project_grade6_content_build.md`. Key gotchas: error routes must target a rep WITH a surface state
(SYMBOLIC/NUMBER_LINE/AREA_MODEL; WORD_PROBLEM has none); 1 live rep = practice-only, 2 = masterable;
making a KC live reds ~6 shared tests that hardcoded the "5 KC" world — thread them.

---

## 3·T3 — T3's role + what I've done this session

**Role:** the **frontend lane**. I own all of `frontend/` — the units/lesson shell, the workspace
answer widgets, the camera/OCR beat, surface rendering — and I'm the **consumer** of T1's wire
contracts (`widget_id`, `answer_kind`, `adaptation`, `nudge`, `explanation`, `ReadBackView`,
`RemediationView`). Concretely I maintain the **frontend `LIVE_KCS` mirror + `selectWidget`** so the
backend content build actually shows up for students. I don't touch the backend registry files, so I
**don't participate in the shared-tree collision** that hit T1/T2 — my only cross-lane dependency is
contractual, not file-level.

**Done this session (picked the lane back up from `HANDOFF_T3.md`):**

| Step | What | Result |
|---|---|---|
| Orient | Read `HANDOFF_T3.md` + the full `T1_T2_COORDINATION.md` thread; mapped the cross-lane state (OCR frozen, `widget_id` required, the percent/multiply collision + freeze). | — |
| Verify | Re-ran the gate on the existing (uncommitted) T3 tree instead of trusting "green." | tsc 0 · ESLint clean · 120 tests · build OK |
| **Fix** | **Surfaced the committed Grade-6 Unit-1 KCs in the UI.** `LIVE_KCS` (`Unit.tsx`) only knew the 5 foundation fraction KCs, so `KC_unit_rate` (`f39c6b0`) + `KC_equivalent_ratios` (`c89c727`) — playable in the backend — rendered "coming soon." Added both; verified (ran the generators) their answers are whole numbers, so routed them to the one-box `number_entry` widget in `selectWidget` (same case as `KC_common_denominator`), not the two-box fraction editor. | +1 test (121 total); gate green |
| Tests | Added a `selectWidget` case (unit_rate + equivalent_ratios → number_entry); repointed the stale `Unit.test.tsx` "coming soon" fixture off the now-live `KC_unit_rate` onto unbuilt `KC_unit_conversion`. | green |
| Coordinate | Logged the change to `T1_T2_COORDINATION.md`; **held** `KC_percent` / `KC_multiply_fractions` (uncommitted + inside T1's freeze) so a clean checkout can't claim a lesson the backend can't serve. Asked T1 to ping enum ids when they land committed. | — |

**Also in the T3 tree (prior T3 sessions, uncommitted, all green):** units-first flow (sign-in →
Units → Unit → Tutor), lesson-screen polish, SignIn cleanup, and the OCR "snap your work" camera beat
(`/transcribe-answer` → read-back → confirm → same `/turn` verifier).

**What's queued for T3:** (1) keep `LIVE_KCS`/`selectWidget` in sync as T1/T2's content lands; (2) the
**units 4–8 widgets** — expression/equation/inequality first (typed + SymPy, no new visuals), then
geometry/stats SVG (area diagrams, coordinate-plane plotter, data displays) — blocked on T1's frozen
per-answer-kind contract; (3) the **P0.5 remediation panel** against `RemediationView` (waiting on the
P0.4 router). The HR.A5 cleanup (drop the kc-keyed branch in `selectWidget`) unblocks the moment T1
extends `widget_id` to carry `number_entry`.

**T3's read on "are agent teams better?"** Agree with T1's §1 — *yes, with worktree isolation* — but
the nuance from the frontend seat: **the collision risk is entirely a backend-registry phenomenon.**
T3 owns `frontend/` exclusively (only `shared-types/` is generated by T1), so a single frontend lane
is perfectly safe in the shared tree and rarely needs a worktree. An agent team would help T3 *only*
if we parallelized the units 4–8 widget build — e.g. one builder per new widget (expression editor,
inequality input, coordinate plotter, data-display reader). Those are independent React modules, so
worktree-per-widget would fan out cleanly, with T3 as the integrator wiring each into `selectWidget`.
Until then, the highest-leverage structure is: **backend KC-builders in worktrees (T1 integrates the
registry); T3 stays in the shared tree and tracks contracts via the channel.**

---

## 4. What's left

**Unit 1 (Ratios) — 2 KCs remain (T1):** `ratio_language` (6.RP.1) and `unit_conversion` (TEKS 6.4H),
both numeric. Then Unit 1 is fully playable (closes the dead-end).
- ⚠️ Catalog drift to watch: `CatalogLesson.kc_id` must be a real enum member (already fixed
  `KC_ratio_meaning` → `KC_ratio_language`).

**Unit 2 (T2, in a worktree):** divide_fractions, gcf_lcm, decimal_operations.

**Units 3–8:** most KCs are NUMERIC (reuse the editor — area, volume, mean/median, evaluate, exponents,
one-step equations). A handful need NEW T3 widgets: write-expressions (expression input), inequalities,
coordinate plane (plotter), data displays. Geometry/stats are the heavier cross-lane work.

**Other T1 backlog (from the earlier handoff):** Tier-2 proactive gating wiring (T2 emits
`trustworthy_kcs`); teacher force-unlock; the P0.4 remediation router; the `/units` server-side gating
(currently a T3 client stopgap; can't be authoritative until grade-6 units have masterable content —
which this build is now creating).

**Masterability caveat:** ratio/percent KCs are PRACTICE-ONLY (one live representation) until T3 ships
a numeric word-problem / `number_entry` widget; then adding the 2nd rep to `scheduler._LIVE_REPRESENTATIONS`
makes them masterable with no other change. T3 maintains the frontend `LIVE_KCS` mirror — ping them
with enum ids when a KC lands committed.

---

## 5. How to coordinate (the protocol that prevents the collision)

1. **Worktree per lane** for the content build (`git worktree add ../wm-<lane> -b <lane>`). T1 merges.
2. **Commit per-KC immediately** — keep the uncommitted-overlap window tiny.
3. **T1 owns the shared registry invariants** — if you touch `knowledge_components` /
   `prerequisites` / the shared test sets, coordinate through T1.
4. **Channel-first**: post intent in `T1_T2_COORDINATION.md` before editing a shared file; read the
   tail first. Push is the owner's call (both remotes via `git push origin main`).
5. **Verify before commit** (CLAUDE.md §4): `cd backend && uv run ruff check . && uv run ruff format
   --check . && uv run mypy . && uv run pytest -q`.

---

## 3·T2 — T2's role + what I've done this session

**Role:** the **HelpNeed-model + evaluation lane** — own the XGBoost predictor (training, re-fit,
per-KC validation, the proactive-gating logic), and the EDM-Cup data pipeline. This session I ALSO
took a **Unit-2 content slice** (the partition T1 proposed) to parallelize the critical-path content
build. Model work is naturally collision-free (it lives in `helpneed/` + the committed artifact, not
the shared registry); the only collision I hit was when I crossed into the **content** lane.

**Committed to `main` this session:**

| Commit | What |
|---|---|
| `87ac7e8` (with T1) | **KC_multiply_fractions** (Unit 2) — built end-to-end off T1's `unit_rate` template: registry/LIVE_KCS, generator, `multiply-as-add` misconception + verifier OPERATION row, nudge bank, worked example, lesson_spec, scheduler, prereq spine (+ removed as a remediation key) + `tests/domain/test_multiply_fractions.py` (7) + threaded the shared pins. Salvaged into one commit with T1's percent after the shared-tree collision. |

**Built + green but NOT yet committed (still in the main working tree — owner gates the push):**

| Work | Files | State |
|---|---|---|
| **Cross-topic HelpNeed re-fit** | `app/helpneed/artifacts/helpneed_v1.joblib` (re-fit), `train_pipeline.py` | Retrained on the relaxed Grade-6 pooled EDM data: **322,417 examples, overall holdout AUC 0.899, 39 KCs scored**. Artifact stamped at width-54 (8 behavioral + 46 KC one-hot), `feature_names`/`n_features_in` so T1's width-guard self-heals. |
| **Per-KC validation harness** | `app/helpneed/per_kc_validation.py`, `tests/helpneed/test_per_kc_validation.py` (14) | `validate_per_kc` → AUC + calibration-gap + positive-rate sliced per KC; thin KCs pooled into one labelled `__thin__` bucket (never silently dropped); single-class AUC → None; **label-space drift invariant** (`KC_ORDER == enum`, every `_CCSS_PREFIX_TO_KC` value ∈ enum). Wired into `train_pipeline.main`. |
| **Tier-2 `trustworthy_kcs` guard** | `per_kc_validation.py` | The honest weak-KC fix: AUC-gated set the proactive arm may fire on (≥0.85, excludes thin bucket + undefined-AUC). On the real re-fit: **33 trustworthy / 6 guarded → reactive-only** (rate_problems, evaluate_expressions, ratio_language, equivalent_ratios, percent, write_expressions — exactly the weak cluster). Gate-wiring into `SustainedHelpNeedGate` is the remaining hookup (policy lane). |
| **Finding #2 — HINT_DEPENDENT teacher alert** | `app/teacher/alerts.py`, `app/api/schemas.py` (AlertKind), `tests/teacher/test_alerts.py`, `frontend/src/components/TeacherSignals.tsx`, `shared-types/src/generated.ts` | New WARN alert: fires when a learner has ≥4 correct but ≤15% unscaffolded (the hint-hunter signature) → `classify_student` moves Hugo on_track → needs_attention. Frontend badge + regenerated types. Backend 1468 + frontend 118 green at the time it landed. |

**Analysis/decisions I drove this session (the "why" behind the model work):**
- **One model, not per-topic.** Recommended a single behavioral HelpNeed model with KC as a one-hot
  feature (not 30 fragmented models) — the signal is behavioral (latency/hints/errors), so it
  generalizes; per-topic models would starve for data. This is what made the cross-topic re-fit viable.
- **EDM-Cup data review.** Grepped the 24M-row ASSISTments corpus: all 5 Grade-6 CCSS domains present
  (12,516 grade-6 problems). Caught two silent-drop bugs in T1's CCSS→KC map (`6.EE.A.6` → real code is
  `6.EE.B.6`; the `6.NS.6` 6a+6c vs 6b split) and surfaced the **adjacent-grade recovery** (`7.NS.*`
  integers = 1,524; `5.NF.B.*` mult/div = 2,880) that moved multiply-fractions + both integer KCs from
  persona-only to data-backed.
- **The weak-KC wall (the key finding).** The owner asked to "fix the weak KCs before pushing." I
  surfaced that this is **blocked by a double wall**: EDM has no error categories, and the
  persona/misconception layer is FRACTION-ONLY — so there is no categorized-error training data for the
  weak KCs (ratios/percent/expr-eval) anywhere. The real fix is **content-gated** (you can't bot an app
  that isn't built). The honest ship-now fix is Tier-2 (gate the proactive arm by per-KC AUC). The real
  per-topic model fix rides this content build, worst-first.

**In front of me right now (queued / next):**
1. **Unit-2 KCs in an isolated worktree** — `git worktree add ../wm-unit2 -b unit2-content` (just
   created). Build `divide_fractions`, `gcf_lcm`, `decimal_operations` there off the template, commit
   per-KC, ping T1 to merge. (Held until T1 committed percent; now unblocked.)
   - ⚠️ Worktree caveat: the venv uses an editable `.pth` (`_editable_impl_whollymath_backend`) pinned
     to the MAIN tree, so the worktree needs its own `uv sync` (or run tests pointing at the worktree
     source) — otherwise it'd import the main tree's `app`, not the worktree's.
2. **Tier-2 gate wiring** — hand `trustworthy_kcs` to `SustainedHelpNeedGate` (policy lane; coordinate
   with T1). No-op on today's KCs (all trustworthy); protective the moment a weak KC becomes playable.
3. **The real weak-KC model fix** — when T1's content + misconceptions land for a weak KC: run persona
   bots over it → categorized-error data → add the error-STRUCTURE feature (`recent_dominant_error_category_share`)
   → re-fit → report the per-KC AUC lift. Built against real content, not a guess.
4. **The uncommitted model work above** is staged-ready and green; it's awaiting the owner's push call
   (and a clean commit — it was kept out of the percent/multiply collision commit on purpose).

**T2's read on "are agent teams better?"** Agree with T1 §1 and T3 — **yes for the content build, with
worktree isolation** — and the model-seat nuance: the **model/eval lane is collision-free by nature**
(it touches `helpneed/` + the artifact, never the shared registry), so a single agent in the shared
tree is fine for it; the collision is purely a *content-registry* phenomenon (same finding as T3 for
frontend). The clean structure: **content KC-builders fan out one-per-worktree with T1 as the registry
integrator; the model lane and the frontend lane each stay single agents in the shared tree.** A true
orchestrated workflow would shine specifically on the ~30-KC content build — a coordinator spawns
one-KC builders in parallel (each independent — copy the template), then **serializes the registry +
shared-test integration through the integrator** (that serialization is exactly what we did by hand,
badly, when percent + multiply collided). The lesson the collision taught: parallelize the
*independent* design work, serialize the *shared-state* merge. — T2
