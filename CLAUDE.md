# CLAUDE.md — Guidelines for AI-Assisted Development on This Project

## Summary

This document tells Claude (and any other AI assistant) how to behave when working on this codebase. It also tells human developers what to expect from AI-assisted work on the team. The opinions here are deliberate. They were chosen because this is a 6-week pitch project for Nerdy where the source hierarchy matters, the mastery model must be defensible, and the decision log we owe the PRD will be assembled partly from git history.

**The five non-negotiable rules:**

1. **The PRD is the contract.** Never override a PRD requirement based on the Nerdy briefing, research literature, or "what would be cool." If you think a PRD requirement is wrong, raise it as an issue. Do not silently work around it.
2. **TDD for the mastery model and persona harness.** These two systems are load-bearing. They get tests-first development. UI components can be more flexible.
3. **Commit messages are decision-log entries.** Write them like the reviewer of our submission will read them — because they will.
4. **Cite sources for non-trivial choices.** If you change a design decision or add a new one, the commit message or doc update must reference the source (PRD section, Nerdy.md line, research citation, or design discussion).
5. **Don't introduce LLM dependency in the latency-critical turn loop.** SymPy for math verification. XGBoost for HelpNeed prediction. The LLM is for natural-language surface generation only.

Read on for the full guidelines.

---

## 1. The source hierarchy (memorize this)

Every change you make must trace to a source. The hierarchy:

1. **The PRD** (`Hyperresponsive Mastery UI` from the Gauntlet Challenger Project) — contractual requirements
2. **`PROJECT.md`** — locked design decisions with their rationale
3. **`TECH_STACK.md`** — locked technical choices
4. **`RESEARCH.md`** — the citations backing our design choices
5. **`Nerdy.md`** — supporting research that informs taste-level choices
6. **Cognitive science / ITS literature** — design grounding (cited in RESEARCH.md)
7. **Team design discussions** — captured in commit messages

**Rules for using the hierarchy:**

- Higher numbers defer to lower numbers when they conflict.
- The PRD cannot be expanded or contracted by anything else.
- The Nerdy briefing cannot add PRD requirements or remove PRD requirements.
- "Best practice from my training data" is below all sources here. Don't use it as justification.

If you're about to make a change you cannot trace to a source, stop and ask.

### Where these sources live (read this)

`PROJECT.md`, `TECH_STACK.md`, `RESEARCH.md`, and `Nerdy.md` are **internal planning documents and are gitignored** — they are intentionally NOT committed and do not push to GitHub or GitLab. They live only on disk, in the project root, for the team to read and build on top of. Being untracked does **not** lower their rank: they are still the authority described above.

`CLAUDE.md` (this file) **is** tracked, because it governs how code in the repo is written and must travel with the code.

What this means for the decision log: because the planning docs are untracked, the **commit message is the tracked decision-log entry** (rule 3 in the Summary). When a change alters a decision recorded in a planning doc, update the doc on disk *and* record the decision and its rationale in the commit message — the commit message is the part a reviewer can see in git history. Never assume a doc edit will show up in a diff; it won't.

---

## 2. TDD requirements (where and how)

### Where TDD is mandatory

**The domain model (Layer 1 of the persona harness).** Every KC, every misconception pattern, every problem generator, every SymPy verifier gets a test before the implementation. This is the single most load-bearing system in the project — if it's wrong, the mastery model is wrong, the personas are wrong, the transfer test is wrong, everything downstream is wrong.

**The mastery model.** Every rule in PROJECT.md §3.4 (representation diversity, unscaffolded attempts, interleaving weight) gets a test that asserts the rule is enforced. The five personas serve as integration tests for the mastery model — if Surface Sam can hit "mastered" status, the interleaving rule is broken.

**The persona behavioral simulator (Layer 3).** Each persona gets unit tests for its expected behaviors: Procedure Priya correctly answers symbolic addition, fails error-finding. Surface Sam correctly handles blocked practice, fails interleaved. Hint-hunter Hugo requests hints at expected rates. These tests are deterministic — same input, same output, every time.

**The HelpNeed predictor.** Inference must be tested for latency (sub-100ms requirement) and for behavior on known-edge-case inputs.

### Where TDD is recommended but not mandatory

**FastAPI endpoints.** Test the contract (request/response shape) but flexibility in implementation is fine.

**State transition logic in the frontend.** Test the policy (given event X in state Y, transition to state Z) but visual rendering can be tested visually.

### Where TDD is NOT required

**UI components.** Visual components can be developed with Storybook or similar; visual testing is sufficient.

**One-off scripts.** Pulling DataShop data, generating reports — these are scripts, not systems.

### How to do TDD here

For the systems where TDD is mandatory, the workflow is:

1. Write the test that asserts the behavior you want
2. Run it and watch it fail
3. Write the minimum implementation to make it pass
4. Refactor if needed, with the test still passing
5. Commit the test and the implementation together in one commit

When Claude (the AI) is helping with code, **ask for the test first.** "Write a test that asserts the mastery model requires correctness across at least 2 representations before declaring mastery on a KC" — that's a valid first prompt. "Implement the mastery model" without specifying the assertions is not.

---

## 3. Git commit conventions

### The format

Every commit message follows this structure:

```
<scope>: <imperative one-line summary, max 72 chars>

<optional body: what changed, why, and what source justifies it>

<optional footer: refs to PRD section, RESEARCH.md entry, or issue>
```

### Scopes (use one of these)

- `domain` — Layer 1 of harness (KCs, misconceptions, problem generators, verifiers)
- `mastery` — mastery model and BKT
- `persona` — persona configs, simulator, LLM surface layer
- `ui` — frontend components, state machine, transitions
- `policy` — UI adaptation policy, transition rules, refuse-rules
- `helpneed` — HelpNeed predictor, training pipeline, integration
- `tutor` — tutor scaffolding, problem presentation, session loop
- `transfer` — transfer probe (S5), transfer item generation
- `eval` — baseline comparisons, A/B test infrastructure
- `infra` — AWS CDK, deployment, environment config
- `docs` — PROJECT.md, RESEARCH.md, TECH_STACK.md, CLAUDE.md, READMEs
- `test` — test infrastructure (not feature tests, which go with the scope they test)
- `chore` — dependencies, lint config, formatting

### Examples of good commits

```
mastery: require correctness across 2+ representations before declaring mastery

Without this, Natural-number Nate hits mastery on symbolic equivalence
items and falsely passes the threshold, then fails number-line
placement. Locked in PROJECT.md §3.4 rule 2; persona test in
test_persona_nate.py::test_nate_should_not_master_with_symbolic_only.

Refs: PROJECT.md §3.4, §4.2 Persona 1
```

```
policy: implement interleaving before mastery declaration

Mastery threshold can now only be reached after the learner correctly
answers 3+ items interleaved across KCs, not in blocks. Directly
implements the Rohrer et al. 2015 finding that blocked practice
inflates the appearance of mastery without producing transfer.

Refs: PROJECT.md §3.6 transition rules, RESEARCH.md §1.3
```

```
helpneed: train v1 classifier on DataShop FractionAddition dataset

Pulled DataShop dataset 122 (FractionAddition-1-2plus1-3 family),
extracted features per PROJECT.md §3.7, trained XGBoost. Baseline
accuracy 0.71 on holdout; SHAP analysis confirms response_latency
and recent_error_rate are top features.

Calibration against synthetic personas is in next commit.

Refs: PROJECT.md §3.7, RESEARCH.md §1.7
```

### Examples of bad commits (do not do)

```
Updated mastery model
```
*Why bad: no scope, no rationale, no source. Tells the decision-log reader nothing.*

```
fix: stuff
```
*Why bad: no information.*

```
feat: add really cool adaptive UI that morphs based on student state
```
*Why bad: marketing language, no source, no specific change described.*

### When the change touches a documented decision

If your commit changes anything captured in PROJECT.md, TECH_STACK.md, or RESEARCH.md, **update the doc on disk as part of the same change, and put the rationale in the commit message.** Those docs are gitignored (see §1), so the doc edit will not appear in the diff — the commit message is the tracked record a reviewer reads. Don't let the on-disk docs drift from reality, and don't bury rationale in a code comment where the decision-log reader won't find it.

### Commit granularity

- One logical change per commit.
- Tests and implementation together (when both exist).
- Doc updates together with the change they document.
- DO commit work-in-progress to branches; DO NOT commit work-in-progress to main.

---

## 4. Working style (trunk-based, direct to `main`)

We work trunk-based: commits go **directly to `main`** and we push. No pull requests, no review gate, no merge ceremony. Every push targets **both remotes** — GitHub and the self-hosted GitLab (`labs.gauntletai.com`, namespace `hiromalarcon`). `main` is not branch-protected.

Because there is no PR to catch problems, the discipline moves into the commit itself.

### Before you push to `main`

- Tests pass locally — especially the mandatory-TDD systems (§2, §9).
- `ruff` / `eslint` + `prettier` clean; `mypy --strict` and `tsc` clean.
- The commit message follows §3 and carries the *why* and the *source*. In trunk-based work the commit message is the only record the reviewer of our submission will read — there is no PR description to fall back on.
- On-disk planning docs updated if the change touches a documented decision (§3, §8.4).

### What replaces the PR description

The information a PR description used to carry now lives in the **commit message body**. For any non-trivial commit, the body answers:

- **What** changed (the one-line summary).
- **Why**, with the source (PRD §, PROJECT.md §, RESEARCH.md §, or design discussion).
- **How to verify** (the test name or command), when it isn't obvious.
- **Risks / open questions**, if any.

### Branches (optional, short-lived)

Use a branch only for genuinely risky or experimental work you don't want on `main` yet. Name it `<scope>/<short-description>` (e.g. `mastery/add-interleaving-rule`). Merge it back to `main` fast — no PR required. Keep `main` working: don't push a broken commit, because there's no CI gate or reviewer to stop it.

### When Claude (the AI) commits

Same standards, no exemption. Claude's commits to `main` get the same tests, lint, type-check, commit-message conventions, and on-disk doc updates as anyone's. If Claude pushes a commit missing the source citation or the rationale, treat it the same as a human's — it's not done.

---

## 5. Working with Claude on this codebase

### Claude is the Director (orchestration, verification, drift alerts)

On this project Claude operates as the **director** of the build, not just a pair of hands. Concretely:

- **Delegate to subagents to keep the main context clean.** When working through a slice or step, Claude spawns subagents to do the bounded, parallelizable, or read-heavy work (searching, scaffolding a module, writing a test + implementation for one KC, drafting a doc) and keeps only the *conclusions* in the main thread. The main context is the director's desk — it stays uncluttered so the build stays legible across a 6-week, multi-step plan. Independent work goes to subagents in parallel where possible.
- **Claude verifies all subagent work; nothing is trusted on faith.** A subagent's output is a draft until the director has checked it. "Verified" means: tests pass (and the mandatory-TDD systems in §2 have the tests they're supposed to), `ruff`/`eslint`+`prettier` clean, `mypy --strict`/`tsc` clean, the change traces to a source in the hierarchy (§1), and it meets the standards in this document. Code an agent wrote gets the same bar as code a human wrote (§5 "LLM-generated code review") — no exemption.
- **Production-grade is the only acceptable bar.** No stubs left as if finished, no TODOs passed off as done, no "works on the happy path" hand-waving. If something is partial, it is reported as partial.
- **Drift gets escalated to you immediately — never worked around.** If subagent output (or Claude's own work) conflicts with the PRD, PROJECT.md, TECH_STACK.md, RESEARCH.md, or the agreed plan — or fills a gap that should have been a question per §5 "Don't let Claude over-confidently fill in gaps" — Claude stops and surfaces it to you the moment it's noticed, rather than silently reconciling it. This is the §1 rule ("If you're about to make a change you cannot trace to a source, stop and ask") applied to delegated work.
- **The tracker is marked only after verification.** `TODO.md` (the gitignored live tracker — see §1's "where these sources live" note and the `.gitignore` entry) is the slice-by-slice map of the build. A step or slice is marked complete (`[x]`) **only after the director has verified it to the bar above** — not when a subagent reports back, and not when code merely exists. Verified-and-complete is stated plainly; anything else stays open.

This director model does not lower any other bar in this document — it raises it. Subagents are an efficiency mechanism; the responsibility for correctness, source-traceability, and the decision log stays with the director.

### Be specific about source authority

When asking Claude to make a change, specify which source is driving it. Examples:

- "Per PROJECT.md §3.4, the mastery model needs to require correctness across 2+ representations. Add a test asserting Natural-number Nate fails to reach mastery, then implement the rule."
- "RESEARCH.md §1.3 documents the interleaving finding. Implement the interleaved-practice-before-mastery rule in the policy."
- "We have an open question in PROJECT.md §8 about cold-start design. Sketch three options with tradeoffs; we'll pick one."

Avoid: "Make the mastery model better." Without a source-grounded constraint, Claude (or any developer) will optimize the wrong thing.

### Ask Claude to challenge a decision when appropriate

If a design decision feels weak, ask Claude to argue against it before implementing it. Example: "PROJECT.md §3.7 commits to Path 2 (live proactive intervention with A/B test). Before I build it, give me three honest reasons we might regret this and one alternative."

This catches "we committed but maybe shouldn't have" before it costs us weeks.

### Don't let Claude over-confidently fill in gaps

If Claude is about to make a design choice that isn't grounded in a source, it should stop and ask. Example: "The cold-start design is an open question (PROJECT.md §8). I don't have authority to decide this; here are three options, which do you want?"

This rule exists because earlier in the project, Claude (this same instance, actually) made up specific Mathnasium price points and "demo-first culture" claims and presented them as fact. Don't repeat that. If you don't have a source, say so.

### LLM-generated code review

Code written by an AI gets the same review as code written by a human. Same tests required. Same lint. Same type-check. Same doc updates. Don't lower the bar because "Claude wrote it."

---

## 6. Code style

### Python (backend)

- **Formatter:** `ruff format` (replaces black). Configured in `pyproject.toml`.
- **Linter:** `ruff check`. Strict mode for new files.
- **Type hints:** required on all public functions. `mypy --strict` in CI.
- **Naming:** snake_case for variables/functions, PascalCase for classes.
- **Imports:** sorted (ruff handles this).
- **Tests:** pytest. Test files in `tests/` mirroring the source tree. Test function names start with `test_`.

### TypeScript (frontend, infrastructure, shared types)

- **Formatter:** Prettier. Configured in `.prettierrc`.
- **Linter:** ESLint with the `@typescript-eslint/recommended` config.
- **Type strictness:** `strict: true` in tsconfig. No `any` without an explicit comment justifying it.
- **Naming:** camelCase for variables/functions, PascalCase for components/types/interfaces, SCREAMING_SNAKE_CASE for constants.
- **Imports:** sorted by `eslint-plugin-import`.
- **Tests:** Vitest. Component tests with React Testing Library.

### General

- **Function length:** if a function is over ~50 lines, justify it. Usually it should be decomposed.
- **Comments:** explain *why*, not *what*. The code shows what. The comment explains the reason.
- **TODO comments:** include your initials and a date. `# TODO(jh, 2026-05-15): handle the case where ...`
- **Dead code:** delete it. Don't leave commented-out blocks "in case we need them later." Git history has them.

---

## 7. Project structure conventions

### Navigability principle (a junior finds their way in under a minute)

Organize so a developer who has never seen this repo can locate the right file from the **name of the concern alone**, without grepping. This is not aesthetic preference — it is how we keep a 6-week, multi-person build legible. Concretely:

- **One canonical home per concern.** Each capability lives in exactly one place (see the tree below). If you can't decide where something goes, it likely belongs in a new, clearly-named module — not spread across two existing ones.
- **Predictable names.** The file name states what's inside; the directory states which layer/concern it belongs to. `mastery/mastery_model.py`, not `mastery/logic.py`.
- **Tests mirror source.** `tests/domain/test_verifier.py` tests `app/domain/verifier.py`. A reader finds the test from the source path and vice versa.
- **Layer boundaries are real and predictable.** SymPy only in `domain/`, LLM calls only in `llm/`, DB queries only in repositories, business logic out of route handlers (see "Where things DON'T live"). These boundaries are exactly what let a junior *trust* the directory names.
- **No junk-drawer files.** Avoid `utils.py`, `helpers.py`, `misc.py`, `common.ts`. Name the actual responsibility.
- **A new top-level directory gets a one-line README** stating what lives there and what does not.

### Files and modules

- One class or one cohesive set of functions per file
- File name matches the primary export (e.g., `mastery_model.py` exports `MasteryModel`)
- Tests live next to or mirror the source tree

### Where things live

```
backend/
  app/
    domain/           # Layer 1: KCs, misconceptions, problem generators, SymPy verifiers
    personas/         # Layer 2 + 3: configs and behavioral simulator
    persona_surface/  # Layer 4: LLM-mediated natural language
    mastery/          # BKT model + the augmentation rules
    policy/           # State transitions, refuse-rules, interleaving logic
    helpneed/         # Predictor training + inference
    tutor/            # Session loop, problem presentation
    api/              # FastAPI routes
    db/               # SQLAlchemy models + migrations
    llm/              # Provider abstraction
  tests/              # Mirrors app/

frontend/
  src/
    components/       # React components, Storybook stories alongside
    workspace/        # Custom SVG components (FractionBar, NumberLine, SymbolicEditor)
    state/            # State machines for surface transitions
    api/              # API client (generated from Pydantic types)
    pages/            # Top-level routes

shared-types/         # Generated TS types from Pydantic
infrastructure/       # AWS CDK
```

### Where things DON'T live

- Don't put business logic in API route handlers; routes call services
- Don't put database queries in services; services call repositories
- Don't put LLM calls anywhere except `llm/` (provider abstraction)
- Don't put SymPy calls anywhere except `domain/` (verification module)

---

## 8. Specific anti-patterns to avoid

These are mistakes we are actively guarding against, with reasons.

### 8.1 Putting an LLM in the turn loop

The HelpNeed predictor must not call an LLM. The mastery model update must not call an LLM. The SymPy verification must not call an LLM. The turn loop has a sub-100ms latency target; an LLM call breaks this.

The LLM is for natural-language surface generation only: persona Layer 4, hint text generation (from validated templates), worked-example narration. Always called *after* the deterministic logic has run.

### 8.2 Trusting an LLM to verify math

Per RESEARCH.md §1.6, step-level math verification by LLMs is an open problem. We use SymPy for all math correctness. The LLM never decides "is this answer correct."

If you find yourself writing a prompt like "is this fraction equivalent to that fraction?" — stop. That's SymPy's job.

### 8.3 Personas that "know" things via LLM emergence

Each persona's knowledge state is defined in their config (Layer 2) and enforced by the behavioral simulator (Layer 3). The LLM (Layer 4) never sees the persona's knowledge state. If the LLM renders text that betrays understanding the persona shouldn't have, that's a bug in the prompt or in the rendering logic. Fix the architecture, not the prompt.

### 8.4 Decision creep without doc update

If you change a transition rule, a mastery criterion, a refuse-rule, or anything else captured in PROJECT.md, update PROJECT.md on disk and capture the change in the commit message of the same commit. (PROJECT.md is gitignored per §1, so the commit message — not a doc diff — is the tracked decision-log entry.) Drift between the on-disk docs and the code makes the decision log we owe the PRD impossible to assemble.

### 8.5 Cleverness over clarity

The codebase will be read by a Nerdy reviewer at some point. A clever one-liner that takes 10 minutes to understand is worse than a 5-line function that's obvious. Write for the reader, not for the writer.

### 8.6 Premature optimization

Six weeks. No microservices. No caching layer. No Kubernetes. No abstraction that doesn't have at least two concrete uses. Simplicity is a feature; complexity is debt.

### 8.7 Adding dependencies without justification

Every dependency adds maintenance burden and a potential security surface. When adding a dependency:

- Justify it in the commit message
- Check the license
- Check the maintenance status (last commit, open issues)
- Add it to `package.json` / `pyproject.toml` with an explicit version

---

## 9. Testing standards

### Test categories

- **Unit tests:** test one function or one class in isolation. No DB, no LLM, no network.
- **Integration tests:** test multiple components together. May use a test DB.
- **Persona tests:** run a persona through the tutor end-to-end and assert expected outcomes. These are the integration tests for the mastery model.
- **A/B tests:** the three-arm baseline comparison. These are evaluation runs, not unit tests; they go in `eval/`.

### Coverage expectations

- Domain model (Layer 1): aim for 95%+ coverage. This is load-bearing.
- Mastery model: aim for 90%+ coverage. Every rule from §3.4 has a test.
- Persona simulator: aim for 85%+ coverage. Each persona has at least one behavioral test.
- HelpNeed predictor: training pipeline tested. Inference tested for latency and known cases.
- FastAPI endpoints: contract tested (request/response shape).
- UI components: visual testing via Storybook is sufficient; some logic tests with React Testing Library.

We don't enforce coverage as a CI gate (coverage gates produce gaming). We do require that critical paths have tests, reviewed in PRs.

### Don't test the LLM

The LLM is non-deterministic. Don't write tests that assert "the LLM returned text X." Test that the LLM was *called* with the right inputs, and test the behavior surrounding the LLM call.

### Persona tests are the integration suite

If you change the mastery model, run the persona suite. If any persona now achieves mastery when they shouldn't (false positive), the change is broken. If any persona now fails to achieve mastery when they should (false negative on Cleo, who sometimes gets things right; or false negative on a clean persona that knows the material), investigate.

---

## 10. AWS deployment specifics

### Local-to-cloud flow

- Local development: `docker-compose up` for Postgres; FastAPI runs with `uvicorn --reload`; React runs with `vite`
- Preview environments: not implemented in v1 (out of scope)
- Push to main: GitHub Actions runs CDK deploy to production (every commit on main is a potential deploy — keep main green)

### AWS CDK conventions

- One stack per logical concern: `NetworkStack`, `DatabaseStack`, `AppStack`, `MlStack`
- Environment-specific config in `cdk.json`
- Secrets never in code; always via Secrets Manager

### Cost controls

- Budget guardrails (configured day one, 2026-05-27): a **$50/month** AWS cost budget with email alerts at 50% ($25), 80% ($40), 100% ($50), and forecasted-100%; plus AWS Cost Anomaly Detection emailing (via SNS topic `whollymath-cost-alerts`) on any spike **≥ $10** (IMMEDIATE). Tightened from the original $100/$200/$500 plan per team direction. Created via CLI for immediate protection; to be codified as a CDK BudgetStack at Slice I (do not double-create).
- LLM API spending monitored separately (LLM provider's dashboard)
- RDS in single AZ, smallest instance class that works
- ECS Fargate task sized to minimum that handles demo load
- No EC2 instances always-on; nothing always-on except RDS

### What goes in `.env` vs. Secrets Manager

- Local development: `.env` (gitignored), `.env.example` checked in showing required keys
- Production: AWS Secrets Manager; ECS task pulls secrets at startup
- Never commit `.env` to git

---

## 11. Documentation requirements

### Every change that adds a feature

- Update PROJECT.md if the feature reflects a locked design decision
- Update TECH_STACK.md if the feature changes the tech stack
- Update RESEARCH.md if the feature is justified by a citation not already in RESEARCH.md
- Update README.md with any new setup steps a developer needs to know

### Every change that changes a public API

- Update the OpenAPI spec (auto-generated by FastAPI, but check the route is documented in code)
- Update the TypeScript types (regenerated; commit the regenerated file)

### Every change that adds a dependency

- Update README.md or `setup.md` with any new install steps

### Every change that touches deployment

- Update `infrastructure/README.md` with what changed

---

## 12. When in doubt

If you're not sure whether to do something one way or another:

1. Check PROJECT.md, TECH_STACK.md, RESEARCH.md, and CLAUDE.md for guidance
2. If still unsure, ask in the commit message or in chat
3. Don't make up justification. "I think this is best practice" is not a justification on this project.

---

## 13. This document is alive

If a guideline here turns out to be wrong, change it. Commit a CLAUDE.md update that explains the reason for the change. Document drift between docs and reality is a project-killer.
