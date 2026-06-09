# CLEANUP_AUDIT.md — Full-Codebase Cleanup Audit (Phase 1)

> Read-only audit. **Nothing has been changed.** This is the map and plan for the
> cleanup branch `cleanup/full-pass`. Findings carry a risk level
> (**safe** / **needs-review** / **risky**) and, where I re-ran the check myself,
> a ✅ **Verified** stamp. Baseline (Phase 0) is green: backend 3158 passed / 9
> skipped; frontend 306 passed (52 files); all lint/format/type/build clean.

---

## 1. Directory map (top-level + significant folders)

```
whollymath/
├── README.md            Public entry doc (tracked)
├── ARCHITECTURE.md      Public architecture doc (tracked) — STALE, see §3
├── AUTH.md              Public auth-design doc (tracked) — accurate
├── CLAUDE.md            AI/human dev guidelines (tracked, governs the repo)
├── HANDOFF.md           Session handoff (gitignored, local)
├── package.json         pnpm workspace root (frontend, shared-types, infrastructure)
├── pnpm-workspace.yaml  Workspace member list (backend intentionally excluded)
├── docker-compose.yml   Local Postgres for dev
├── .githooks/pre-push   Enforced gate mirroring CI (ruff·mypy·pytest / prettier·eslint·tsc·vitest)
├── .github/workflows/   CI (backend job + frontend job)
├── .pre-commit-config.yaml   Orphaned third gate — see F1
├── backend/             Python (uv): FastAPI + SymPy + SQLAlchemy + XGBoost
│   ├── app/
│   │   ├── domain/        Layer 1: KCs, misconceptions, problem generators, SymPy verifiers
│   │   ├── mastery/       BKT mastery model + augmentation rules
│   │   ├── personas/      Layer 2+3: persona configs + behavioral simulator
│   │   ├── persona_surface/  Layer 4: LLM-mediated natural language
│   │   ├── policy/        State transitions, refuse-rules, interleaving
│   │   ├── helpneed/      HelpNeed ML predictor (train + inference)
│   │   ├── tutor/         Session loop, problem presentation, transfer probe
│   │   ├── api/           FastAPI routes + services (service.py is the big one)
│   │   ├── db/            SQLAlchemy models + repositories
│   │   ├── llm/           LLM provider abstraction (only place LLM is called)
│   │   ├── auth/          Parent/child auth (Argon2id, JWT, Google verify)
│   │   ├── teacher/       Teacher dashboard services
│   │   ├── homework/      Homework scan (Mathpix)
│   │   ├── events/        Turn/event ingest
│   │   ├── notifications/ SES parental-consent email
│   │   ├── tts/           Voice synthesis (ElevenLabs) — V2
│   │   └── eval/          Three-arm baseline comparison (eval runs, not unit tests)
│   ├── tests/            Mirrors app/
│   ├── scripts/          One-off data/report scripts
│   └── migrations/       Alembic (generated, lint-excluded)
├── frontend/            React + TS + Vite
│   └── src/
│       ├── pages/          Top-level routes (Tutor, Teacher*, Parent*, SignIn, Units…)
│       ├── components/     Shared components + avatar/ subtree
│       ├── workspace/      Custom SVG widgets + selectWidget dispatch (WidgetContract.ts)
│       ├── state/          Surface state machines (index.ts is an empty stub — F-FE-1f)
│       ├── api/            Generated API client + demo fixtures
│       ├── auth/           Auth context/hooks
│       ├── styles/         Global CSS (wm- namespaced)
│       └── telemetry/      Client telemetry
├── shared-types/        Generated TS types from backend Pydantic (generated.ts)
├── infrastructure/      AWS CDK (NetworkStack, DatabaseStack, AppStack, MlStack)
└── mdfile/              Internal planning docs (gitignored): PROJECT, TECH_STACK,
                         RESEARCH, Nerdy, TODO, AUDIT, DECISION_LOG, CURRICULUM_*, …
```

**Overall health:** strong. Layer boundaries (SymPy→domain, LLM→llm, repo pattern)
are genuinely respected. No junk-drawer files, no committed secrets/caches, no
commented-out code blocks. The findings concentrate in (a) stale public docs,
(b) a handful of dead frontend exports/assets, (c) one orphaned config, and
(d) a few long functions for Phase 4.

---

## 2. Documentation drift (Phase 2 work)

The headline: **`ARCHITECTURE.md` is a full version behind reality** and now
contradicts both `README.md` and `AUTH.md` on scope and the auth model.

| ID | Doc · location | Claim | Reality | Risk |
|----|----------------|-------|---------|------|
| D1 ✅ | ARCHITECTURE §1/§4 | "fractions only", "five KCs (KC1–KC5)", "no mult/division" | Full Grade-6: **44 live KCs across 9 units** (`LIVE_KCS`=44 verified). Owner reversed the no-mult/div lock. | needs-review |
| D2 ✅ | ARCHITECTURE §12/§15.1 | "Google Sign-In only", "we **never store passwords**" | Parent/child auth stores **Argon2id password+PIN hashes**, mints own JWTs (`app/auth/`), parent-as-COPPA-consent. The "never store passwords" line is now false. | needs-review (security-relevant) |
| D3 ✅ | ARCHITECTURE §16 (Spanish) | `ES_MX_REVIEWED=False`, "gated until educator sign-off" | `ES_MX_REVIEWED: Final[bool] = True` (`hints_es.py:132`) — a module constant, already flipped. | safe |
| D4 ✅ | ARCHITECTURE §13 repo tree | Backend tree omits dirs | Missing **`homework/`, `tts/`, `teacher/`, `notifications/`**. | safe |
| D5 | ARCHITECTURE §1/§5/§11 | personas = "fraction misconception" | Domain generalized; reword to "documented misconception". | safe |
| D6 ✅ | README L50/L116/L168 | "**43** content-complete KCs" (×3) | `LIVE_KCS`=**44**. | safe |
| D7 | README L131 | "**Three** U8 financial-literacy lessons" | 4 `concept_only` U8 lessons / 3 KCs (banking spans two). | safe |
| D8 ✅ | README L206 env list | lists ANTHROPIC/MATHPIX/GOOGLE fallbacks | Omits **`SESSION_SIGNING_KEY`** (parent/child fails closed 503 if unset) and **`ELEVENLABS_API_KEY`**. | needs-review |
| D9 | README L168 "What's built" | lists domain/mastery/personas/helpneed/UI/eval/teacher/AWS | Silent on shipped **auth (parent/child+COPPA)**, **homework scan**, **V2 voice/avatar/Spanish**. | needs-review |
| D10 | README L183 | "backend 2,789 passing / frontend 187 passing" | Actual today: **3158 / 306**. Numbers stale. | safe (re-count) |
| D11 ✅ | `.env.example` | — | **`ELEVENLABS_API_KEY`** read by `tts/` but absent from `.env.example`. `OPENAI_API_KEY` documented but never read (aspirational). | needs-review / safe |

`AUTH.md`, `backend/README.md`, `infrastructure/README.md` are **accurate** — no
drift found. No broken internal links (references to gitignored `PROJECT.md`
etc. are intentional "internal/local-only" mentions, not clickable dead links).

**Additional drift from HANDOFF §11** (the team's own pre-built integrity list — fold into Phase 2):
| ID | Doc · location | Claim | Reality (HANDOFF §) | Risk |
|----|----------------|-------|---------------------|------|
| D12 | README | "aligned to both CCSS and TEKS" | Overstated: **2 whole units (U-INT integers, U8 financial literacy) are TEKS-only**; 20 lessons single-framework. True line: "dual-coverage where applicable; integers + financial literacy are TEKS-only." (§11.2) | needs-review |
| D13 ✅ | **CLAUDE.md §10** + README §7 | CLAUDE.md says "push to main → GitHub Actions runs CDK deploy"; README says manual `cdk deploy --all`, CI only lints/tests | Deploys are **manual**; CI does not deploy. The two tracked docs contradict each other. (§11.6) | needs-review |
| D14 | README | "$50/month budget guardrail" | **Not codified** — CLI-only, no CDK BudgetStack. (§11.7) | safe (phrase as "configured via CLI, not yet codified") |
| D15 | README | "Spanish toggle / bilingual" | Real but **captions-only, help-text-only (~16%, 176 strings)**; problems stay English, no Spanish audio for dynamic text. Don't imply a full Spanish app. (§11.8, §10) | needs-review |
| D16 | README HelpNeed | "AUC 0.893" | Re-fit to **0.899**; note it's a training-time metric, not stored in the committed artifact. (§5.6, §11.4) | safe |
| D17 | `mdfile/curriculum.py`-adjacent + README | "~52 lessons" | **54** catalog lessons. KC nuance: 47 enum / 44 engine-served / 45 lesson-referenced. (§3, §11.5) | safe |

> KC-count canonical phrasing (HANDOFF §3): **"44 playable KCs the tutor serves"** (47 enum
> members, 44 engine-served with working SymPy generators, 45 referenced by lessons). Use 44.

---

## 3. Dead / stale artifacts

### Frontend (all ✅ verified by grep)
| ID | Path | Finding | Risk |
|----|------|---------|------|
| F-FE-1 | `components/LessonTracker.tsx` + `.css` | Only refs = self + barrel line. Never rendered, no test. **Dead.** | **safe** to delete |
| F-FE-2 | `state/index.ts` | Just `export {};` — empty stub barrel; contexts imported directly. | **safe** to delete |
| F-FE-3 | `public/welcome/*` (10 PNGs) | `abacus_gold_transparent, bakground (typo), compass_transparent, family_icon_transparent, frame_teacher_gold, parent_portal_frame_transparent, prop-abacus, teacher_frame_silver_transparent, wood_table_transparent, wooden_abacus_transparent` — zero code refs (tracked in git). The correctly-spelled `backdrop.png` IS used. | **safe** to delete |
| F-FE-4 | `public/class-dashboard.html`, `public/dashboard-prototype.html` | Leftover static prototypes, no code refs (tracked). | **safe** to delete |
| F-FE-5 | `workspace/FractionBar.tsx` (+`barToAnswer`,`BarValue`,`.css`) | Exported in barrel + named "canonical" in comment, but `selectWidget`/`WidgetContract.ts` **never returns it** and no page imports it. Superseded by `FractionArea`/`SymbolicEditor`. Well-tested. **Not** mentioned in HANDOFF open work. | **needs-review** — flag, don't delete without owner confirm |
| F-FE-6 | `workspace/FigureStimulus.tsx` (+`describeFigure`,`FigureSpec`) | **NOT dead — tracked, blocked, built-ahead work.** HANDOFF §5.3: geometry figure-drawing is staged cross-lane (T1 wire type → T2 figure-scene deriver → T1 wires `FigureStimulus` into `SceneStimulus`/`Tutor.tsx`); 6.G.4 net is a stated priority. Deleting it would descope in-progress work. | **KEEP** (do not touch) |
| F-FE-7 | `components/avatar/Avatar3D*`, `avatar3dFlag.ts`, `facialExpression.stub.ts`, `AvatarGuide.tsx` | **Owner-gated, intentionally retained.** HANDOFF §6 (Owner Decisions): 3D ships only after a **30fps low-end-Chromebook acceptance test**; §9 Wave 2.2 "3D spike isolated/OFF." Sole reason the 4 heavy 3D deps exist. The **non-3D** avatar files (`visemes`, `audioUnlock`, `useGuideSpeech`, `emotionToGuide`, `capabilityProbe`) ARE live — do not touch. | **KEEP** (owner decision pending) |

### Backend
| ID | Path | Finding | Risk |
|----|------|---------|------|
| F-BE-1 | `helpneed/parse_assistments.py` | INERT stub (every fn raises `NotImplementedError`), blocked on a licensing decision (V2_TODO 0.1). A documented decision-gated seam — **not** dead. | safe to **keep** |
| F-BE-2 | `eval/live_loop_metrics.py` | App-orphan but test-covered; eval modules are expected to be un-imported by the live app (CLAUDE.md §9). | keep (low needs-review) |
| F-BE-3 | TODO markers (~50) | All sourced slice-IDs / labelled placeholders — none are rot. Minor: they use `TODO <slice-id>` not CLAUDE.md §6's `TODO(initials, date)`. | safe |

**Backend has no unused dependencies** (all 16 runtime + 5 dev verified against
imports — uvicorn/psycopg2/alembic correctly have no source import), **no
junk-drawer files, no commented-out code, no truly dead modules.**

---

## 4. Structural problems

| ID | Where | Finding | Risk |
|----|-------|---------|------|
| S1 | `backend/app/{api,db,domain,eval,helpneed,homework,llm,mastery,persona_surface,personas,policy,teacher,tts,tutor}` | CLAUDE.md §7 mandates a one-line README per top-level dir; only **3 of 15** have one (`auth`, `events`, `notifications`). 12 missing. (Module docstrings partly compensate.) | safe |
| S2 ✅ | SymPy outside `domain/` | `from sympy import Rational` appears in `personas/`, `tutor/` as a **value type** (carries fraction values), not verification — §8.2 spirit intact. Documented carve-out in `session.py:10`. Decide: bless in §7/§8.2 or wrap in a domain value type. | needs-review (taste) |
| S3 | `frontend/src/pages/` vs `pages/parent/` | Parent pages split across two homes (some in `pages/`, some in `pages/parent/`). Consolidate for navigability. | needs-review (low) |
| S4 ✅ | `workspace/SetModelStimulus.css` + `pages/Tutor.css:477` | `.wm-setmodel` base defined in widget CSS *and* re-targeted in Tutor.css. Intentional override (not the `.wm-numberline` accidental-collision class), but puts a 2nd bare rule outside the widget's canonical home. Scope the override to the descendant selector. | needs-review (low) |
| S5 | `workspace/index.ts:1` | Barrel comment advertises `FractionBar` as a canonical manipulative though it's dead (F-FE-5). Fix when resolving that. | safe |
| F1 ✅ | `.pre-commit-config.yaml` | Orphaned **third** gate: referenced in **no** README, duplicates ruff/eslint/prettier already in pre-push+CI, pins `ruff v0.15.14` independently (drift surface). CLAUDE.md §4 only documents pre-push+CI. | needs-review (likely delete) |
| F4 | `infrastructure/`, `shared-types/` | No ESLint config/`lint` script — only `frontend` is linted by the gates. Hand-written CDK in `infrastructure/lib/*.ts` escapes lint (typecheck does cover it). | needs-review |
| F9 | TS version split | `infrastructure` uses `typescript@^5.6.3`→5.9.3; `frontend`/`shared-types` use `6.0.3` (exact). Infra typechecks under an older major. | needs-review (bump can surface errors) |
| F7 | `.gitignore` "KEPT TRACKED" comment | Lists README/CLAUDE/ARCHITECTURE but not `AUTH.md` (which IS tracked). | safe |
| F12 | `.gitignore` root doc entries | Belt-and-suspenders rules for docs that now live under `mdfile/`; harmless dead rules. | safe (internal) |

**Not problems (checked, cleared):** DB queries are not leaking out of repos
(`service.py` makes 0 raw queries, 27 repo calls — the flagged `.add(`/`sessionmaker`
hits were set ops + type annotations); LLM calls are confined to `llm/`; route→
service→repository layering holds; the 11 `*_stimulus.py` files are a clean family,
not sprawl; `transfer_probe.py` vs `live_transfer_probe.py` are distinct concerns.

---

## 5. Complexity hot-spots (Phase 4 candidates, ranked)

### Backend (by length × branch-count)
| # | Location | ~Len | Why | Test-risk |
|---|----------|------|-----|-----------|
| 1 | `helpneed/parse_edmcup.py:374` `parse_action_logs` | 228 L / 28 br | Worst by far; nested log parser. **Top decomposition target.** | eval/training infra (lower risk) |
| 2 | `domain/verifier.py:593` `_across_value` | ~140 L | Misconception-value derivation, many wrong-answer cases. | mandatory-TDD (§2) — refactor with verifier suite green |
| 3 | `api/service.py:910` `_answer_response` | 117 L / 11 br | Mixed concerns: verify→mastery→feedback→next. Split verify/score/respond. | persona suite is the integration guard |
| 4 | `api/service.py:1292` `_persist_turn` | ~120 L | DB-write fan-out; split per-entity. | — |
| 5 | `tts/live_synth.py:82` `synthesize_live` | 57 L / 15 br | **Worst branch density** — easiest readability win. | safe |
| 6–10 | `domain/problem_generators.py` `_generate_check_register`(105) / `_generate_exponents`(104) / `_generate_area_polygons`(91); `api/service.py:1044` `_hint_response`(92); `helpneed/events_features.py:370` `_v2_features_at`(58/14) | — | Long generators + hint orchestration + feature extraction. | mixed |

> **Note:** the biggest *files* — `problem_generators.py` (3936 L), `hints.py`
> (1039 L), `knowledge_components.py` (1033 L) — are mostly **declarative data
> tables**, not tangled logic. Their length is fine; do **not** "simplify" by
> splitting data.

### Frontend (by length + nesting + hook density)
| # | Location | ~Len | Why |
|---|----------|------|-----|
| 1 | `pages/Tutor.tsx` | **1125 L** | Outlier on every axis: 27 `useState`, 12-level indentation, session loop + widget dispatch + speech + readback all in one component. **Top target.** |
| 2 | `pages/parent/ParentSignupWizard.tsx` | 605 L | 15 `useState`, deepest nesting (28-space); multi-step wizard in one component. |
| 3 | `pages/TeacherDashboard.tsx` | 560 L | 10 `useState`, 4 `useEffect`; roster + trends + reminders + render combined. |
| 4 | `api/teacherDemo.ts` / `api/parentDemo.ts` | 528 / 351 L | Hand-built demo fixtures — dense but **flat data**; low urgency. |
| 5–8 | `pages/ParentChildView.tsx`(474), `pages/BenchmarkTheater.tsx`(432), `App.tsx`(401), `pages/SignIn.tsx`(371) | — | Heavy JSX / routing wiring / form+animation state. |

---

## 6. Proposed phase plan (for your approval)

**Phase 2 — docs (mostly safe):** fix D1–D11 so `ARCHITECTURE.md` matches reality
(scope, auth, repo tree, Spanish flag), correct README counts (43→44, 3→4 lessons,
test numbers) and the missing env vars (`SESSION_SIGNING_KEY`, `ELEVENLABS_API_KEY`),
add the homework/auth/V2 "what's built" bullets, rebuild README for readability.
**The scope/auth rewrites (D1, D2) I'll draft and show you before committing** —
they're load-bearing and security-relevant.

**Phase 3 — structure (after your approval of a target tree):** consolidate parent
pages (S3), add the 12 backend dir READMEs (S1), fix the `.gitignore`/barrel comments
(F7, S5). Moves via `git mv`.

**Phase 4 — code simplification (small, reviewable, behavior-preserving):** start
with the safe wins — `tts/live_synth.py` branch density, then `service.py`
`_answer_response`/`_hint_response`, then `Tutor.tsx`. The mandatory-TDD files
(`verifier.py`, persona sim) only with their suites green; I'll flag thin coverage
before touching anything.

**Deletions I'd queue once you confirm (small commits, full verification after each):**
- **Safe now:** `LessonTracker` (F-FE-1), `state/index.ts` (F-FE-2), 10 orphan
  welcome PNGs (F-FE-3), 2 prototype HTMLs (F-FE-4), `.pre-commit-config.yaml` (F1).
- **Owner decision required (I will NOT touch without your yes):** `FractionBar`
  (F-FE-5), `FigureStimulus` (F-FE-6, may be a missing feature), the 3D-avatar
  spike + its 4 deps (F-FE-7). These are well-tested and decision-gated.

**Left untouched (intentional, not dead):** `parse_assistments.py` inert stub
(F-BE-1), `eval/live_loop_metrics.py` (F-BE-2), the live non-3D avatar files,
the SymPy `Rational` value-type carve-out (S2 — needs an owner ruling, not a
silent change).

---

*End of Phase 1 audit. No files changed. Awaiting go-ahead before Phase 2.*
