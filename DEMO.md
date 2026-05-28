# DEMO — WhollyMath walkthrough

A narrated tour of the working local app. It is meant to be read aloud by a presenter
and reproduced by a reviewer: every command and every screen below matches what the app
actually does today. Where a feature only becomes visible with an API key or a database,
that is called out inline.

---

## 1. What you're about to see

WhollyMath is an adaptive fraction tutor whose **mastery model cannot be fooled by surface
fluency**. Most AI learning tools are either a chat box (no idea whether you understood) or
a static worked-example walkthrough (the same five steps for everyone). Neither can tell a
learner who *understands* from one who is guessing, pattern-matching a single problem
format, or leaning on hints. WhollyMath is built to tell the difference and to prove it:
"mastered" requires correctness across **two real representations**, at least one
**unassisted** attempt, **interleaved** (not blocked) practice, and a final **transfer
probe** in a representation the learner hasn't just been drilling. The interface adapts to
*how* the learner is thinking — but with restraint: five disciplined, labeled surface states,
never a chaotic morphing UI. Hyperresponsive, not twitchy. All correctness and mastery
decisions are deterministic (SymPy + rules); the language model only narrates.

---

## 2. Setup

Three processes: Postgres (optional), the FastAPI backend, the Vite frontend.

### Postgres (optional — skip for the basic demo)

The app boots fine with no database; it just runs in-memory (no session/mastery
persistence across restarts). To get persistence and the resume story (§5), bring up the
local Postgres that mirrors prod:

```bash
docker compose up -d            # postgres:16 on localhost:5432, db/user/pass = whollymath
```

Then point the backend at it before launching uvicorn:

```bash
export DATABASE_URL=postgresql://whollymath:whollymath@localhost:5432/whollymath
```

If `DATABASE_URL` is unset or unreachable, the backend logs a warning and continues
in-memory — the demo still works, you just lose persistence.

### Backend (FastAPI turn loop)

```bash
cd backend && uv sync
uv run uvicorn app.api.app:app --reload     # serves on http://localhost:8000
```

macOS one-time prerequisite for the HelpNeed predictor: `brew install libomp` (XGBoost
needs the OpenMP runtime; the trained model artifact is already committed, so no training
is required to run the demo).

Optional environment keys (the app works without both):

- `ANTHROPIC_API_KEY` — enables the **mascot voice**: hints and the proactive nudge are
  rephrased in the mascot's natural-language voice. Without it, the same hints still appear,
  just in their pre-written deterministic form. The LLM never decides correctness or
  mastery, so disabling it changes only the *wording*.
- `GOOGLE_CLIENT_ID` (backend) / `VITE_GOOGLE_CLIENT_ID` (frontend) — enables real Google
  sign-in. Without it, the "Sign in with Google" button is harmless and falls through to the
  anonymous guest path; sign-in never blocks the flow.

### Frontend (React + Vite)

```bash
cd frontend && pnpm install && pnpm dev      # serves on http://localhost:5173
```

The Vite dev server **proxies** the API paths (`/health`, `/routing-choices`, `/session`,
`/turn`, `/eval`) to `http://localhost:8000`, so the browser sees a single origin and there
is no CORS to manage. Open the printed `http://localhost:5173` URL.

---

## 3. The main learner flow

Walk the learner path top to bottom. The thesis-proving moments are flagged **[THESIS]**.

### Landing → sign-in

- **Landing** (`Landing.tsx`): the brand hero — "Math, made whole." A pie mascot idle-bobs;
  the brand pie turns slowly. Click **"Start learning as a student"**. The mascot crouches,
  jumps, and rolls off-screen, handing off to the welcome page.
- **Sign-in / welcome** (`SignIn.tsx`): "Welcome back, explorer!" with two ways in —
  **Sign in with Google** (real OIDC when a client id is configured; otherwise it falls
  through anonymously) or **Student Demo — Free** (the no-account guest path). Either choice
  advances. For the basic demo, click **Student Demo**.

### Cold-start routing (Turn 0)

- **Cold start** (`ColdStart.tsx`): "Where do you want to start?" Three big illustrated
  cards — each art *shows* the concept — plus a de-emphasized "Not sure yet? Just get me
  started!" default:
  - **Putting two fraction pieces together** → adding fractions (`KC_addition_unlike`)
  - **Telling when two different-looking fractions are really the same amount** → equivalence
    (`KC_equivalence`)
  - **Finding where a fraction sits on a line between 0 and 1** → number-line placement
    (`KC_number_line_placement`)
  - **"Just get me started"** → de-emphasized default, no skill claim (routes to equivalence)

  Choosing a card calls `POST /session`, which derives the route, prior, and the first
  (calibration) problem server-side. You'll see a brief "Getting your first problem ready…"
  then land in the tutor.

### The reactive turn loop

This is the core (`Tutor.tsx`). For each problem: the surface shows the current mode label
and statement, takes an answer, `POST /turn` runs the deterministic verify → mastery →
policy pipeline, shows a labeled verdict, then advances to the problem the loop chose next.

Things to demonstrate, in order:

1. **The mode is always labeled.** Every state names the frame of mind it's in
   ("Work it with the numbers", "Picture how big it is", "Picture the pieces"). A number-line
   problem says "Place it on the number line"; a yes/no judgment says "Same amount, or not?"
   or "Bigger, or not?" The surface never presents a state without telling the learner what
   it is.

2. **The answer widget matches the question.** The input is chosen by the problem's format:
   a draggable marker for number-line items, yes/no buttons for relational judgments, the
   fraction editor otherwise. **[THESIS]** This is what lets the *same* KC be answered in
   more than one representation (e.g. addition both symbolically and on the line) — the
   substrate for the representation-diversity rule.

3. **Interleaving + two representations per route.** **[THESIS]** As you work, the backend
   scheduler interleaves companion KCs rather than serving a block of identical problems, and
   it rotates representations within the goal KC. Mastery is computed on this interleaved
   stream, not on a block — blocked fluency does not get you to "mastered."

4. **The per-KC progress strip.** A strip across the top shows every skill the session has
   touched, each as a bar that fills toward the mastery threshold (τ = 0.85). The goal KC is
   emphasized; a mastered KC shows a ✓. This makes "how close am I, and on what" legible at a
   glance.

5. **Requesting a hint — escalating help.** Click **"I'd like a hint"**. Help escalates with
   each request on the same problem: first a **nudge** (a pre-written conceptual prompt, no
   answer revealed — and no LLM/SymPy, because a nudge carries no numeric claim), then a
   **partial step**, then a **full worked step** (these two are LLM slot-filled but
   SymPy-validated before display, with a pre-written fallback). With `ANTHROPIC_API_KEY` set,
   the **mascot speaks** the help in its own voice; without the key, the same deterministic
   text appears. Using a hint is recorded — it costs the learner the "unassisted attempt"
   credit toward mastery.

6. **Getting stuck → the S4 worked example.** **[THESIS]** Get two in a row wrong. The policy
   transitions to **S4 — "Let's take it step by step."** A fully solved example appears, but
   **one step at a time**: each step shows the work *and* a "why did this work?" prompt; click
   **"Show me the next step"** to reveal the next. The learner reads the reasoning, not just
   the answer.

7. **The previous-work panel.** When you advance to a new problem, a compact "Last one" panel
   preserves the problem you just left, the answer you gave, and whether it was right
   (✓ / ✗). A transition never silently throws away the learner's work.

8. **Reaching provisional mastery → the S5 transfer probe.** **[THESIS]** When the BKT
   probability crosses τ *and* the anti-gaming rules are satisfied, the goal KC is **provisionally**
   mastered — not done yet. The surface enters **S5**, badged **"Final check — prove you've
   really got it."** The probe asks the skill in a *different* representation than the recent
   work (plus an error-finding check), with scaffolds stripped. This is the transfer test.

9. **CONFIRMED mastery end-state.** Pass the probe and the goal KC flips to confirmed
   mastery: the progress bar shows the mastered fill + ✓, and the feedback block becomes
   "You mastered [skill]! You got it right across different forms — that's real
   understanding, not one lucky answer." The Next button reads "Keep practicing." **Mastered
   means CONFIRMED** — it required two representations, an unassisted attempt, interleaved
   practice, and a passed transfer probe.

---

## 4. The "you can't fool it" beat

This is the differentiator. The same persona that fools a chat tutor or a static walkthrough
gets *denied* mastery here, because mastery is a two-stage, rule-gated construct.

### On-screen: the three-arm comparison dashboard

Open the app with `?eval=1`:

```
http://localhost:5173/?eval=1
```

This renders the researcher view (`EvalComparison.tsx`, served by
`GET /eval/three-arm-comparison`) — outside the student flow. It shows the five adversarial
synthetic learners, the problems each was given, and how three tutors verdict their
mastery: **Adaptive (ours)**, **Chat baseline**, **Static baseline**.

The headline tally to point at:

- **Adaptive false positives: 0/5** — none of the five adversaries fools our mastery model.
- **Chat baseline: 2/5 (live)** — the chat-only tutor certifies mastery for two learners who
  don't have it.
- **Static: N/A — certifies nothing** — a static walkthrough has no mastery construct at all,
  so it can't even make the claim.

The five adversaries each force one rule: Natural-number Nate (needs ≥2 representations),
Procedure Priya (needs an explain/find-the-error item), Hint-hunter Hugo (needs an
unassisted correct attempt), Surface Sam (mastery computed on interleaved practice),
Click-through Cleo (engagement-floor flags low-effort answers). The dashboard also lays out
five further pre-registered metrics, one adversary each. The adaptive and static columns are
computed live and deterministically; viewing the dashboard makes **no** LLM call and spends
no money.

### On the command line: the false-positive harness

The headline metric is reproducible directly:

```bash
cd backend && uv run python -m app.eval.false_positive_harness
```

It runs all five personas through the real mastery model and prints, per persona, whether
mastery was confirmed, ending with a line like
`DEFENSE HOLDS ✓: 5/5 personas denied mastery`. This is the integration test suite for the
mastery model expressed as a demo artifact: if any adversary reached confirmed mastery, the
defense is broken.

---

## 5. Optional advanced beats

- **Proactive help arm** (`?proactive=1`): open the student flow with this flag to opt into
  the proactive HelpNeed arm. When the learner's sustained help-need signal trips the tuned
  gate (K=3 consecutive turns, threshold 0.5), a nudge is offered **unasked**, inline in the
  workspace, mascot-voiced. Default is OFF (observe-only) — the predictor scores every turn
  but nothing acts on it — because proactive help can underperform reactive help, so it's
  A/B-tested rather than assumed. This is not a learner-facing control; it's a demo/A/B
  switch.

- **The eval dashboard** (`?eval=1`): covered in §4; also the place to walk a reviewer
  through the five-persona attack matrix and the pre-registered metrics.

- **Behavioral telemetry:** as the learner works, the surface fires fine-grained events
  (problem presented, time-to-first-interaction, answer edits, number-line drags, hint
  requests, submits) to `POST /events`, completely **off the turn loop** — telemetry never
  blocks a turn, and the endpoint returns 202 (accepted, best-effort). This is the raw stream
  behind the HelpNeed v2 features. It's not a screen; show it via the browser network tab or
  by tailing the backend.

- **Persistence / resume (needs Postgres):** with `DATABASE_URL` set (§2), sessions and
  mastery are persisted. Combined with Google sign-in (a configured client id), a returning
  learner's carried-forward mastery is read on sign-in (`fetchMe`), giving cross-device
  continuity. Without a DB the app is in-memory and starts fresh each boot.

---

## 6. Talking points

- **The mastery model is defensible, not vibes.** "Mastered" requires correctness across two
  representations, an unassisted attempt, interleaved practice, and a passed transfer probe.
  We prove it: 0/5 adversaries fool it, versus 2/5 for a chat tutor.
- **SymPy owns correctness; the LLM never grades.** Every answer and every hint's numeric
  claim is checked symbolically. A language model never decides whether your math is right —
  step-level LLM math verification is a known-unreliable problem.
- **No LLM in the turn loop.** Verify, mastery, and state transitions are deterministic and
  sub-100ms. The LLM is additive surface only (hint phrasing, mascot voice) and runs *after*
  the math is settled — turn it off and the system still works, it just talks less naturally.
- **Capture richly, act conservatively.** We log fine-grained behavior off the turn loop and
  score help-need every turn, but the proactive intervention is gated (K=3, threshold 0.5)
  and A/B-tested — because proactive help can backfire. Hyperresponsive, not twitchy.
- **Adaptation with restraint.** Five labeled surface states with documented reasons to
  exist, each transition rule-driven and named — never a chaotic morphing UI.
