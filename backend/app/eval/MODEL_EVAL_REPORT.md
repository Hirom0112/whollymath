# Model & Evaluation Report — WhollyMath HelpNeed Predictor + Live Loop

*Last updated 2026-05-30. Owner: model/eval lane.*

This is the honest evaluation record the PRD asks for (CLAUDE.md §9: "report what is
computed; label what is pending; never invent a number"). It covers the HelpNeed
predictor's per-KC quality, the weak-KC finding and its mitigation, the live-loop
("hyperreactive") counter-metrics, and the limitations that are real and tracked rather
than hidden.

**Provenance convention used throughout.** Every number is tagged so a reviewer knows
how to reproduce or trust it:

- **[re-fit]** — measured on the held-out split of the EDM Cup re-fit run (artifact
  `helpneed_v1.joblib`, commit `4e1f26c`). The 1.44 GB EDM Cup dataset lives only in the
  owner's environment, so these are **not** reproducible from a clean checkout — they are
  cited from the recorded run, not re-derived here. The commit message records the summary
  figures (322k examples, AUC 0.899, 33/6 split); the full per-KC table (§2) was transcribed
  from the re-fit run's `train_pipeline` output (logged in the untracked planning doc
  `T1_T2_COORDINATION.md`). Because that doc is gitignored, **this report is the tracked home
  for those per-KC numbers** — re-running `train_pipeline` on the EDM data regenerates them.
- **[computed]** — recomputed live from this checkout by the eval harness
  (`app/eval/`); reproduce with the command given. Deterministic, free, no LLM/DB/SymPy.
- **[recorded-LLM]** — a one-time live LLM run, committed as a JSON artifact so the
  number is stable without re-spending (`app/eval/artifacts/chat_baseline_run.json`).
- **[pending]** — not yet measurable; needs data or instrumentation we do not have. Named
  with what it would take, never estimated.

---

## 1. The HelpNeed predictor — what it is

A single **cross-topic** XGBoost classifier predicting P(unproductive) for the next turn,
scored observe-only in the turn loop (sub-100ms; no LLM in the loop — CLAUDE.md §8.1).

| Property | Value | Source |
|---|---|---|
| Training examples | 322,417 | [re-fit] |
| Feature width | 56 (9 behavioral + 47-KC one-hot) | [re-fit] |
| Overall holdout AUC | **0.899** | [re-fit] |
| Fractions-only predecessor AUC | 0.885 | [re-fit] |
| KCs with real EDM labels | 39 (all cleared n≥30, no thin bucket needed) | [re-fit] |
| Gate (sustained-signal) | K=3 consecutive turns at P≥0.5 | [computed] `DEFAULT_K`/`DEFAULT_THRESHOLD` |

The cross-topic pooling is the central modeling bet: **one model over many KCs, not 30
fragmented per-KC models.** It paid off — pooling *raised* overall AUC (0.885 → 0.899)
rather than diluting it, because the behavioral signal of unproductive struggle (errors,
hints, give-ups, latency, turns-since-last-correct) generalizes across topics.

---

## 2. Per-KC AUC — the honest, weakest-first picture  *(all [re-fit])*

Overall AUC hides per-topic variation. Sliced by KC on the same holdout
(`per_kc_validation.validate_per_kc`), the picture is strong almost everywhere with one
genuine weak cluster. Reported weakest-first so the limitation leads, not the headline.

### Weak (AUC < 0.83) — the finding, not a flaw to hide

Numbers below are the current shipped artifact (after the `recent_no_hint_error_rate`
mis-reasoning feature, §3). The feature gave a small, honest lift across the cluster and
promoted `write_expressions` over the 0.85 trustworthy bar, but the hardest three
(`rate_problems`, `evaluate_expressions`, `percent`) barely moved — confirming the
behavioral-signal ceiling: those need problem-*content* features, not more behavioral ones.

| KC | n (test turns) | AUC | calibration gap | code |
|---|---:|---:|---:|---|
| `rate_problems` | 2592 | **0.748** | 0.006 | 6.RP.A.3b |
| `evaluate_expressions` | 505 | **0.748** | 0.009 | 6.EE.A.2c |
| `ratio_language` | 1025 | **0.780** | 0.024 | 6.RP.A.1 |
| `equivalent_ratios` | 3680 | **0.820** | 0.007 | 6.RP.A.3a |
| `percent` | 2149 | **0.817** | 0.000 | 6.RP.A.3c |
| `write_expressions` (now trustworthy) | 3283 | **0.850** | 0.007 | 6.EE.A.2a / 6.EE.B.6 |

### Mid (0.83 ≤ AUC < 0.90)

`addition_unlike` .881 · `equivalence` .885 · `multiply_fractions` .885\* ·
`integer_multiply_divide` .881\* · `gcf_lcm` .878 · `ordering_inequalities` .873 ·
`integer_add_subtract` .868\* · `summary_statistics` .857 (n=62, cal 0.062 — weakest
calibration, thin sample)

### Strong (AUC ≥ 0.90)

`multi_digit_division` .984 · `expression_parts` .977 · `polygons_coord_plane` .971 ·
`signed_numbers` .951 · `statistical_questions` .947 · `equivalent_expressions` .939 ·
`surface_area_nets` .937 · `inequalities` .928 · `volume` .929 · `unit_rate` .931 ·
`dependent_vars` .927 · `data_displays` .921 · `rationals_on_line` .917 ·
`mean_absolute_deviation` .915 · `one_step_equations` .913 · `number_line_placement` .910 ·
`divide_fractions` .902 · `decimal_operations` .901 · `exponents` .902 ·
`area_polygons` .899 · `coordinate_plane` .898 · `unit_conversion` .898 ·
`equation_solutions` .895 · `absolute_value` .892

\* = **adjacent-grade data** (Grade-5 5.NF.B / Grade-7 7.NS). Same skill, different
grade-coded source; the shared-behavioral-signal thesis is what justifies pooling them.
Flagged here per the model-lane agreement so the table is not read as pure Grade-6.

**Calibration** is tight almost everywhere (gap < 0.03); the one exception is
`summary_statistics` (0.062 at n=62), which is a thin sample and is reported pooled/flagged
rather than as a confident per-KC number.

---

## 3. The weak-KC finding — *why* the RP/expression cluster is soft

This is a real, interesting limitation, not noise. The HelpNeed model reads **behavioral
tells** of struggle — wrong answers, hint requests, give-ups, latency,
turns-since-last-correct (the SHAP-dominant feature). Those tells fire loudly when a
learner is *visibly* stuck.

On the ratio/rate/percent cluster and expression-evaluation, struggle looks different:
a learner confidently computes the *wrong* thing (e.g., adds across a ratio, or treats a
percent as a raw count) — **quiet mis-reasoning, not a behavioral storm.** The answer is
wrong, but the per-turn behavioral trace looks like a fluent, low-latency, no-hint turn.
The model has little to read, so AUC drops to ~0.74–0.82.

**Built (2026-06-04):** `recent_no_hint_error_rate` — the rate of recent turns answered
*wrong without requesting a hint*, the literal confident-error tell. It landed as the
4th-most-important feature (SHAP 0.26), is faithfully computable on the live tutor (from
`correct` + `hinted`, no train/serve skew), and lifted the cluster modestly —
`write_expressions` crossed into the trustworthy set. The hardest three stayed put.

**Backlog (still needed for the hardest mis-reasoning-without-error topics):** problem-
*content* features — the `problem_text_bert_pca` vector already in `problem_details.csv`,
step-level dwell time, edit/backspace churn, intermediate-value capture. The BERT route is
the highest-leverage next step but needs a serve-time embedding for our *generated*
problems (an architecture decision, not just a training change). Tracked, not built in v1.

---

## 4. Mitigation — the Tier-2 trustworthy-KC guard

We do **not** silence the model on weak KCs, and we do **not** let it drive a
low-confidence proactive nudge there either. The mitigation is a precise filter:

- **Trustworthy set** = KCs whose validated per-KC AUC ≥ 0.85
  (`per_kc_validation.trustworthy_kcs`). On the current shipped artifact that is
  **34 trustworthy / 5 reactive-only** [re-fit]. The 5 reactive-only are the hard core of
  the weak cluster in §2: `rate_problems`, `evaluate_expressions`, `ratio_language`,
  `equivalent_ratios`, `percent` (`write_expressions` cleared the bar after the §3 feature).
- The **proactive arm** (`SustainedHelpNeedGate.should_intervene_for_kc`) fires only on a
  trustworthy KC. On a guarded KC it stays silent and the **deterministic reactive layer**
  (SymPy verdict → morph + misconception) handles the turn — which never depended on the
  HelpNeed model's confidence in the first place.
- The set is **never hardcoded**: it is a projection of the per-KC validation, stamped onto
  the artifact at train time and read into the gate at boot. As the model improves on a
  re-fit, the guarded set narrows automatically — no code change.

### ⚠ Limitation: the guard is wired but currently **dormant**  *(honest, tracked)*

The committed `helpneed_v1.joblib` predates the `trustworthy_kcs` stamp, so it loads with
`trustworthy_kcs = None` [computed], which the gate reads as "no KC filter" — the
default-unchanged behavior. **The guard activates on the owner's next artifact re-stamp**
(a `train_pipeline` run with `WHOLLYMATH_HELPNEED_OUT` set, which needs the EDM Cup dataset
in the owner's environment). Until then the proactive arm, *were it enabled*, would treat
every KC as proactive-eligible. This is mechanically fine because the proactive arm is also
default-OFF per session (observe-only); the guard is the second safety layer, pending
activation.

Reproduce the dormant state:
```
uv run python -c "from app.helpneed.artifact import load_predictor; \
print(load_predictor().trustworthy_kcs)"   # -> None (dormant)
```

---

## 5. Live-loop counter-metrics (HR.D1) — "branching is not enough"

The PRD demands evidence the hyperreactive loop *helps*, not just that it changes the UI.
These are the honestly-computable counter-metrics, recomputed live from this checkout.

Reproduce all of §5:
```
uv run python -c "from app.eval.live_loop_metrics import compute_live_loop_metrics, \
format_report; print(format_report(compute_live_loop_metrics()))"
```

| Metric | Value | n | Reading |
|---|---:|---:|---|
| Classifier accuracy | **100%** | 6 labeled states | the 6-state classifier names each labeled behavior [computed] |
| Reason-label coverage | **100%** | 4 fired adaptations | every UI change carries a one-line reason (refuse-rule) [computed] |
| Typed/OCR verdict agreement | **100%** | 3 answers | a second input modality never changes correctness — SymPy owns it [computed] |
| UI-change frequency | **67%** | 6 states | per-state morph/nudge rate, under the 5/6 bound [computed] |
| **Intent→UI routing accuracy** | **37%** | 38 error routes | **see §6 — the honest gap** [computed] |
| Hint-dependence delta (proactive vs reactive) | — | — | **[pending]** — needs a live proactive-arm A/B run |
| Transfer after scaffold removal | — | — | **[pending]** — needs a live proactive-arm A/B run |

Notes on the two computed-but-nuanced ones:

- **UI-change frequency** is a *per-state* rate over the labeled classifier scenarios
  (4 of 6 states fire a change; productive-struggle is a protected no-op and fluent-ready
  from S1 targets the surface already shown). It is **not** a per-turn live session
  frequency — that needs a live run, so the "morph too often?" question is answered
  structurally here and left [pending] for the live number.
- The two [pending] deltas are the only HR.D1 asks that require a live A/B; they are named,
  not estimated.

---

## 6. The 37% intent→UI routing gap — the most important honest finding

**"Did the morph fix the error?"** (HYPERREACTIVE §6, target ≥ 0.75). Measured over every
lesson spec's declared error routes:

> **14 of 38 error routes (36.8%) [computed]** morph a wrong answer to a *manipulative*
> surface (number line / area-model bars) that exposes the error. The other 24 route back
> to **symbolic** — which is no morph at all.

Reproduce:
```
uv run python -c "from app.eval.live_loop_metrics import intent_routing_accuracy; \
print(intent_routing_accuracy())"   # -> (0.368..., 38)
```

### Why it is exactly 37% and not a bug

Only the **five fraction KCs** have a manipulative widget to route into:

| Routes to a manipulative (morph ✓) | Routes to symbolic (no morph) |
|---|---|
| `equivalence`, `common_denominator`, `addition_unlike`, `subtraction_unlike`, `number_line_placement` | `ratio_language`, `unit_rate`, `equivalent_ratios`, `percent`, `multiply_fractions`, `divide_fractions`, `unit_conversion`, `gcf_lcm`, `multi_digit_division`, `decimal_operations`, `absolute_value`, `integer_add_subtract` |

The ratio/rate/percent and integer/expression KCs route errors to `symbolic` **because
their manipulative widgets do not exist yet.** A wrong answer there gets a verdict + a
misconception message, but no representation morph that *shows* the error.

### The fix is domain + widget work, not eval work  *(tracked)*

Raising routing accuracy means **building the manipulative widgets and their error routes**
for the non-fraction KCs (e.g., a double-number-line for ratios/rates, a percent bar, a
coordinate plane — the coordinate-plane widget is in progress, `InequalityInput` landed
self-contained with routing deferred). This is the single largest honest gap between the
shipped product and the "the interface acts as a tutor on every KC" vision. It is a
roadmap item, surfaced verbatim, not papered over.

---

## 7. Headline defense result — the three-arm comparison

For context, the PRD's central claim (the false-positive-mastery defense) holds:

| Arm | False-positive mastery | Source |
|---|---|---|
| **Adaptive** (ours: SymPy + §3.4 mastery rules + S5 transfer probe) | **0 / 5** | [computed] `run_false_positive_harness` |
| **Chat** (LLM self-certifies, no SymPy, no mastery model) | **2 / 5** (Hugo, Priya over-claimed) | [recorded-LLM] 2026-05-28, claude-opus-4-7 |
| **Static** (pre-rendered worked example) | **N/A** (no mastery construct) | architectural |

All five personas are mastery *adversaries*; any "MASTERED" is a false positive. Adaptive
denied all five — four blocked at provisional (Sam/Nate/Hugo/Cleo), Priya reached
provisional (genuinely fluent procedure) and was demoted by the S5 transfer probe. The chat
tutor over-claimed exactly the two right-answer-without-understanding personas — the
difference between *grading answers* and *measuring understanding*.

Note on scope (honest): the per-KC **defense coverage** check confirms all **17 / 17
LIVE_KCs** [computed] have BOTH the transfer-probe gate and reactive error routing wired —
the mechanisms chat/static lack. But the false-positive *persona attacks* cover only the
fraction KCs (the five adversaries are fraction-bound). We certify the defense *exists* per
KC; we do not claim a persona attacked each KC.

---

## 8. Limitations summary (the tracked list)

| # | Limitation | Status |
|---|---|---|
| 1 | RP/rate/percent + expression-eval KCs: HelpNeed AUC ~0.74–0.82 (quiet mis-reasoning, weak behavioral tells) | **Known finding.** Mitigated by the Tier-2 guard (§4); backlog: richer mis-reasoning features (§3). |
| 2 | Tier-2 guard is wired but **dormant** (committed artifact carries `trustworthy_kcs=None`) | **RESOLVED (2026-06-04).** Re-fit stamped **34 trustworthy KCs** onto the committed artifact; the guard is now live and width-compatible (`is_compatible_with_live_features()==True`), auto-re-enabling the live-scoring tests. |
| 3 | Intent→UI routing **37%** — 12 of 17 LIVE_KCs route errors to symbolic (no manipulative widget) | **Roadmap.** Domain+widget work; coordinate-plane in progress. (§6) |
| 4 | Hint-dependence delta (proactive vs reactive ≤10%) | **Pending live A/B** on the proactive arm. |
| 5 | Transfer-after-scaffold-removal | **Pending live A/B** on the proactive arm. |
| 6 | `summary_statistics` calibration gap 0.062 @ n=62 | Thin sample; reported pooled/flagged, not as a confident per-KC number. |
| 7 | Per-KC AUC numbers (§2) not reproducible from a clean checkout | **RESOLVED (2026-06-04).** EDM Cup 2023 is openly mirrored on OSF (`osf.io/yrwuh`, no login); pulled into the gitignored `backend/data/edmcup2023/` and the §2 numbers reproduce via the README command. Data stays gitignored (ASSISTments terms forbid redistribution; non-commercial). |

None of these gate shipping v1. They are the honest boundary of what is measured versus
what is built — which is the artifact the PRD asks for.

---

*Sources: `app/eval/` (live metrics), `app/helpneed/per_kc_validation.py` (per-KC slicing),
`app/policy/intervention_gate.py` (Tier-2 guard), `app/eval/artifacts/chat_baseline_run.json`
(recorded chat run), commit `4e1f26c` + `T1_T2_COORDINATION.md` 2026-05-30 (re-fit run),
PROJECT.md §3.7/§3.11, RESEARCH.md §1.7/§9, HYPERREACTIVE.md §6, CLAUDE.md §9.*
