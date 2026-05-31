import { useEffect, useRef, useState } from 'react';

import {
  submitTurn,
  transcribeAnswer,
  type AdaptationView,
  type InterventionView,
  type MasterySnapshot,
  type ProblemView,
  type ReadBackView,
  type StartSessionResponse,
  type SurfaceState,
  type TurnResponse,
} from '../api';
import { Mascot, PiMenu, SparkCount, WoodBanner, type PiMenuItem } from '../components';
import { useTelemetry } from '../telemetry';
import {
  ClassifySets,
  CoordinatePlane,
  ExpressionInput,
  fractionToAnswer,
  InequalityInput,
  isCompleteInequality,
  NumberEntry,
  NumberLine,
  selectWidget,
  SymbolicEditor,
  tickFraction,
  YesNo,
  yesNoToAnswer,
  type FractionValue,
} from '../workspace';
import './Tutor.css';

const EMPTY_FRACTION: FractionValue = { numerator: '', denominator: '' };

// Reads a photo File into a base64 data URL — the wire format /transcribe-answer accepts (same
// contract as the homework scan). Kept local; the only place the camera beat turns a photo into a
// string. Mirrors HomeworkUpload's helper (one obvious shape, not a shared util for a 2-line fn).
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      resolve(typeof reader.result === 'string' ? reader.result : '');
    };
    reader.onerror = () => {
      reject(new Error('Could not read the photo.'));
    };
    reader.readAsDataURL(file);
  });
}

// The pool of storybook-world backdrops a lesson can wear (frontend/public/tutor-bg-*.jpg).
// Each is pre-toned: edge-cropped (no generator watermark), softened, and faintly blue so it
// stays a calm backdrop behind the problem card (a further blur + blue wash is added in CSS).
export const TUTOR_BACKGROUNDS: readonly string[] = Array.from(
  { length: 11 },
  (_, i) => `/tutor-bg-${String(i + 1)}.jpg`,
);

// A tiny deterministic string hash (djb2) so a lesson's backdrop is STABLE for the whole lesson
// (no reshuffle between problems) yet VARIES across lessons. Seeded by the lesson's KC.
function hashString(s: string): number {
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i);
  return h >>> 0;
}

/** The backdrop for a lesson, as a CSS `url(...)` value — picked from the pool by the KC. */
export function lessonBackground(kc: string): string {
  return `url('${TUTOR_BACKGROUNDS[hashString(kc) % TUTOR_BACKGROUNDS.length]}')`;
}

/**
 * The on-screen banner for a LIVE adaptation the hyperreactive loop made (HR.B5) — the visible
 * half of "the interface IS part of the tutoring". It does NOT decide the morph (that rides on
 * next_surface_state, already applied); it says, in one calm line, WHY the screen just adjusted —
 * so the change never feels arbitrary. A stable key visual (the same "tuned" mark every time) makes
 * the moment recognizable; the banner is styled by the triggering learner state, announced politely
 * for screen readers, and dismissible so the learner keeps agency (for a fluent-ready learner the
 * dismiss reads "Keep practicing" — declining the implied skip by staying). Reduced-motion drops the
 * entrance (CSS). The reason text itself is server-authored (deterministic; the LLM only voices it).
 */
function AdaptationBanner({
  adaptation,
  onDismiss,
}: {
  adaptation: AdaptationView;
  onDismiss: () => void;
}): React.JSX.Element {
  const fluentReady = adaptation.state === 'fluent_ready';
  return (
    <aside
      className={`wm-tutor-adapt wm-tutor-adapt--${adaptation.state}`}
      role="status"
      aria-live="polite"
    >
      {/* Stable key visual: the same "tuned the screen for you" sliders mark every adaptation. */}
      <span className="wm-tutor-adapt-mark" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.1">
          <path d="M4 7h10M18 7h2M4 17h2M10 17h10" strokeLinecap="round" />
          <circle cx="16" cy="7" r="2.4" fill="currentColor" stroke="none" />
          <circle cx="8" cy="17" r="2.4" fill="currentColor" stroke="none" />
        </svg>
      </span>
      <span className="wm-tutor-adapt-text">{adaptation.reason}</span>
      <button type="button" className="wm-tutor-adapt-dismiss" onClick={onDismiss}>
        {fluentReady ? 'Keep practicing' : 'Got it'}
      </button>
    </aside>
  );
}

// The starting answer state for a problem. An equivalence "fill the top" item gives the
// denominator ("?/8"), so we seed it (locked in the editor) and the learner enters only
// the numerator; every other item starts blank.
function initialFraction(problem: ProblemView): FractionValue {
  if (problem.given_denominator != null) {
    return { numerator: '', denominator: String(problem.given_denominator) };
  }
  return EMPTY_FRACTION;
}

/**
 * The in-tutor problem surface (Turn 1 onward). Drives the real reactive loop
 * (ARCHITECTURE.md §10): present the current problem, take an answer, POST /turn,
 * show the labeled verdict, then advance to the next problem the loop chose.
 *
 * Layout (Slice CP.A.4, matching the approved "lesson world" mock): a two-tone page —
 * a CREAM header zone carrying the pie mascot + the lesson title, sitting above a ROYAL
 * BLUE stage on which a single cream PROBLEM CARD floats. The warmer "world" register the
 * onboarding opened in is carried into the lesson header here (PRODUCT.md onboarding
 * register arc), while the working card itself stays calm and uncluttered.
 *
 * Input selection: the answer widget is chosen by the problem's surface_format /
 * answer_kind, so the rendered widget always matches what the question asks — a number
 * line for placement OR an arithmetic result that lands in 0–1, yes/no buttons for a
 * relational judgment, the fraction editor otherwise. This is what lets the SAME KC be
 * answered in more than one representation (e.g. addition symbolically and on the line),
 * which the mastery model's representation-diversity rule (§3.4 rule 2) requires.
 * The interleaving + representation rotation is the backend scheduler (policy/scheduler).
 */

type Phase = 'answering' | 'submitting' | 'feedback';

// Which input the learner edited — distinguishes a number-line drag from a typed answer in
// the behavioral stream (Slice PL.2).
type TelemetryEditKind =
  | 'fraction'
  | 'numberline'
  | 'yesno'
  | 'number'
  | 'expression'
  | 'inequality'
  | 'coordinate'
  | 'number_sets';

// The one-line reason shown when the surface changes between problems (refuse-rule 4: never
// present a new state without saying why). The labeled morph is the centerpiece of the
// "adapt with restraint" promise — the change is always explained, never silent.
const TRANSITION_REASON: Record<SurfaceState, string> = {
  S1_symbolic_focus: "Let's work this one with the numbers.",
  S2_number_line_primary: "Let's see this on the number line — the size is easier to read there.",
  S3_fraction_bars_primary: "Let's picture the pieces with bars.",
  S4_worked_example: "Let's slow down and walk through one step by step.",
  S5_transfer_probe: 'Final check — let’s prove it really sticks.',
};

// Kid-friendly names for the per-KC progress strip (the mastery snapshot keys on KC id).
const KC_LABEL: Record<string, string> = {
  KC_equivalence: 'Equivalent fractions',
  KC_common_denominator: 'Common denominator',
  KC_addition_unlike: 'Adding fractions',
  KC_subtraction_unlike: 'Subtracting fractions',
  KC_number_line_placement: 'Number line',
  KC_write_expressions: 'Writing expressions',
};

// Fuller, sentence-style lesson titles for the header headline (the mock shows the human
// skill name as a big serif title, not the terse progress-strip label). Falls back to the
// strip label, then the raw KC id, so an unmapped KC still renders something readable.
const KC_TITLE: Record<string, string> = {
  KC_equivalence: 'Find an equivalent fraction',
  KC_common_denominator: 'Find a common denominator',
  KC_addition_unlike: 'Add fractions with unlike denominators',
  KC_subtraction_unlike: 'Subtract fractions with unlike denominators',
  KC_number_line_placement: 'Place a fraction on a number line',
  KC_write_expressions: 'Write an expression from words',
};

// τ — the mastery probability threshold (PROJECT.md §3.4 / mastery_model), τ=0.90. The progress
// bar fills to full as the BKT probability approaches τ; mastery needs τ AND the §3.4 rules.
const MASTERY_THRESHOLD = 0.9;

// Per-skill lesson length — the curriculum's practice-ramp target (CURRICULUM_DRAFT.md §1.1:
// "~10-ish, the deepest skill may run longer"). Number-line placement runs ~13 rungs; the
// other four are ~10. Drives the "Problem N of <length>" caption + the tracker's practice fill.
const LESSON_LENGTH: Record<string, number> = {
  KC_number_line_placement: 13,
  KC_equivalence: 10,
  KC_common_denominator: 10,
  KC_addition_unlike: 10,
  KC_subtraction_unlike: 10,
};

// The backend returns the snapshot for the KC answered THIS turn only. Merge by KC id, keeping
// the latest reading per KC, so the progress strip shows every skill the session has touched
// (and the goal KC's mastered state persists across interleaved companion turns).
function mergeMastery(prev: MasterySnapshot[], next: MasterySnapshot[]): MasterySnapshot[] {
  const byKc = new Map(prev.map((m) => [m.kc_id, m]));
  for (const m of next) byKc.set(m.kc_id, m);
  return [...byKc.values()];
}

// The four-point spark/star path — drawn (never an emoji), matching the brand sparkle in
// Landing/SparkCount. Reused for the mastery star.
const STAR_PATH = 'M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z';

export function Tutor({
  session,
  onExit,
  onHomework,
}: {
  session: StartSessionResponse;
  /** Optional "back to the course map" affordance (Slice CP.A.2 navigation). */
  onExit?: () => void;
  /** Optional "open the homework flow" affordance, surfaced via Pi's nav menu. */
  onHomework?: () => void;
}): React.JSX.Element {
  const sessionId = session.session_id;
  const [problem, setProblem] = useState<ProblemView>(session.problem);
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(session.surface_state);
  // The one-line reason the surface changed, shown as a labeled banner on the new problem
  // (refuse-rule 4). Cleared once the learner submits (it has done its job).
  const [transitionReason, setTransitionReason] = useState<string | null>(null);
  // A LIVE in-session adaptation the hyperreactive loop proposed (HR.B4 → rendered here, HR.B5):
  // present only when the live state classifier fired a sustained state and the proactive flag is
  // on (null in the observe-only default). When set, it replaces the static transition reason with
  // the loop's own labeled reason + a state-styled, dismissible banner. The morph itself rides on
  // next_surface_state (already applied); this is the on-screen "why".
  const [adaptation, setAdaptation] = useState<AdaptationView | null>(null);
  // Sparks — an honest reward count (RD.0.2): earned for correct work, more when unassisted,
  // never for a wrong answer. Frontend-derived for now; the persisted backend field is RD.5.1.
  const [sparks, setSparks] = useState(0);
  // How many problems the learner has worked this session — drives the "Problem N:" eyebrow
  // on the card (the mock's "Problem 1:"). Starts at 1 (the session's first problem).
  const [problemNumber, setProblemNumber] = useState(1);
  const [fraction, setFraction] = useState<FractionValue>(() => initialFraction(session.problem));
  const [tick, setTick] = useState<number | null>(null);
  // The yes/no selection for relational-judgment problems (true=yes, false=no, null=unset).
  const [yesNo, setYesNo] = useState<boolean | null>(null);
  // The whole-number answer for a common-denominator item (a shared piece-size, not a fraction).
  const [numberAnswer, setNumberAnswer] = useState('');
  // The typed algebra string for an expression-answer item (write/equivalent expressions). Graded
  // by SymPy equivalence on the backend (§8.2); the surface only keeps it SymPy-parseable.
  const [expression, setExpression] = useState('');
  // The composed inequality string ("x>=5"), the plotted-points string ("(2,-1)" / a polygon vertex
  // list), and the comma-joined number-set labels ("integer,rational") for the three widget-id-routed
  // answers. Each is a plain answer string the backend grades (§8.2); the surface only composes it.
  const [inequality, setInequality] = useState('');
  const [coordinate, setCoordinate] = useState('');
  const [numberSets, setNumberSets] = useState('');
  const [phase, setPhase] = useState<Phase>('answering');
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [hintUsed, setHintUsed] = useState(false);
  // S4 worked example (§3.5): the backend returns the solved steps when a transition lands
  // in S4 (after ≥2 errors). They reveal one at a time, each with its "why did this work?"
  // prompt — so the learner reads the reasoning, not just the answer. revealCount is how many
  // steps are currently shown; it resets on the next problem.
  const [revealCount, setRevealCount] = useState(1);
  // The answer the learner submitted on the CURRENT problem (captured at submit time so the
  // "previous work" panel can echo it once we advance). null until they submit.
  const [lastAnswer, setLastAnswer] = useState<string | null>(null);
  // Previous-work panel (refuse-rule 2, §3.8): when we move to a new problem we preserve a
  // compact record of the last one — its statement, the answer given, and whether it was
  // right — so a transition never silently throws away the learner's work.
  const [prevWork, setPrevWork] = useState<{
    statement: string;
    answer: string;
    correct: boolean;
  } | null>(null);
  // A proactively-offered nudge for THIS problem (Slice 4.5): the previous turn's
  // sustained HelpNeed signal tripped the §3.7 gate, so help is shown unasked, inline in
  // the workspace (§3.8 refuse-rule 6). null unless the proactive arm fired (default OFF).
  const [intervention, setIntervention] = useState<InterventionView | null>(null);
  // A MID-PROBLEM nudge the live loop offered on a telemetry flush (Beat 1) while the learner is
  // still working — sustained struggle, never one twitch; the backend gates it to at most once per
  // problem. Voiced by Pi inline, additive (never touches the workspace), cleared once they answer
  // or advance. null unless the proactive arm fired (default OFF), like `intervention`.
  const [midNudge, setMidNudge] = useState<InterventionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The camera "snap your work" beat (HR.C1/C3): the read-back the scanner returned for the photo
  // the learner just took, shown as "I read this as 3/4 — right?" before it is graded. null when no
  // snap is in flight. `scanning` is true while the image is uploading/transcribing (shows a
  // spinner, blocks a double-snap). A successful confirm submits the read answer through /turn.
  const [readBack, setReadBack] = useState<ReadBackView | null>(null);
  const [scanning, setScanning] = useState(false);
  // The per-KC mastery snapshot the backend returns each turn (BKT probability + declared
  // mastery). Merged across turns so the progress strip shows every skill touched.
  const [mastery, setMastery] = useState<MasterySnapshot[]>([]);
  // Whether Pi's nav menu is open. The menu and the help-speech bubble share the mascot, so
  // they are mutually exclusive: while the menu is open the bubble is collapsed (it returns
  // the moment the menu closes). Pi is nav OR voice at a given moment, never both at once.
  const [navOpen, setNavOpen] = useState(false);

  // The KC this session is working toward (the cold-start route's KC). When the model
  // DECLARES mastery on it, the journey's goal is reached.
  const goalKc = session.problem.kc;
  // The lesson is complete when the backend says so on this turn (the explicit
  // ``lesson_complete`` terminal signal — the goal KC just CONFIRMED via the S5 probe), OR
  // when the merged mastery snapshot reports the goal KC mastered. We trust the explicit
  // flag first: it fixed the bug where a confirmed lesson never surfaced its completion and
  // looped on forever (the snapshot-only path was unreliable across interleaved turns).
  const goalMastered =
    (result?.lesson_complete ?? false) ||
    (mastery.find((m) => m.kc_id === goalKc)?.mastered ?? false);
  // The S5 transfer probe: the surface state is S5 while the learner answers the probe items
  // (a different representation + an error-finding check). We frame it as a final check so
  // the learner knows this confirms mastery — it isn't just another practice problem.
  const isProbe = surfaceState === 'S5_transfer_probe';

  // The per-skill lesson length (CURRICULUM_DRAFT.md §1.1: number-line runs ~13, the rest ~10).
  // Drives the small "N/length" problem counter in the bottom-right of the card (owner request).
  // The old S1–S5 surface stepper + "Problem N of M" caption were removed — the wood banner now
  // carries the lesson TITLE instead — so the progress/phase the tracker consumed are gone here.
  const lessonLength = LESSON_LENGTH[goalKc] ?? 10;

  // The big header title is the human skill name for the CURRENT problem's KC (the mock's
  // serif headline), falling back gracefully so an unmapped KC still reads.
  const lessonTitle = KC_TITLE[problem.kc] ?? KC_LABEL[problem.kc] ?? problem.kc;

  // When the current problem was first shown — the elapsed time is the turn's
  // latency_ms, which feeds the engagement floor (§6) and HelpNeed (§8) server-side.
  const startedAt = useRef<number>(Date.now());

  // Behavioral telemetry (Slice PL.2): record HOW the learner works each problem, off the
  // turn loop (fire-and-forget, never blocks the surface). `firstInteractionLogged` makes
  // time-to-first-interaction a single edge per problem.
  // Surface a mid-problem nudge from a telemetry flush (Beat 1). Only meaningful while answering;
  // once a verdict shows or we advance, it is cleared, so a late flush can't pop a stale tip.
  const telemetry = useTelemetry(sessionId, (n) => {
    setMidNudge(n);
  });
  const firstInteractionLogged = useRef(false);

  // Emit problem_presented whenever a new problem mounts, and reset the first-interaction
  // edge so the NEXT input is timed against this problem's start.
  useEffect(() => {
    firstInteractionLogged.current = false;
    telemetry.track('problem_presented', {
      problem_id: problem.problem_id,
      kc: problem.kc,
      surface_format: problem.surface_format,
      surface_state: surfaceState,
    });
    // problem_id is the trigger; surfaceState is read at presentation time by design.
  }, [problem.problem_id]);

  // Record the learner's first touch on a problem (time-to-first-interaction) once, then the
  // specific edit. Called from every input's onChange.
  function noteInteraction(kind: TelemetryEditKind, detail: Record<string, unknown>): void {
    if (!firstInteractionLogged.current) {
      firstInteractionLogged.current = true;
      telemetry.track('first_interaction', {
        problem_id: problem.problem_id,
        elapsed_ms: Date.now() - startedAt.current,
        kind,
      });
    }
    telemetry.track(kind === 'numberline' ? 'numberline_move' : 'answer_edit', {
      problem_id: problem.problem_id,
      ...detail,
    });
  }

  // The answer widget is chosen by what the problem ASKS, via the one shared `selectWidget`
  // contract (workspace/WidgetContract.ts, HR.A5) — not by inline checks here — so the surface
  // always matches the question and the SAME KC can be answered in more than one representation
  // (addition symbolically AND on the line), which mastery rule 2 needs. New lessons get the right
  // widget for free from the backend WidgetId mapping (domain/lesson_spec.py, HR.A1).
  const widgetKind = selectWidget(problem);
  const isNumberLine = widgetKind === 'number_line';
  const isYesNo = widgetKind === 'yes_no';
  const isNumberEntry = widgetKind === 'number_entry';
  const isExpression = widgetKind === 'expression';
  const isInequality = widgetKind === 'inequality';
  const isCoordinate = widgetKind === 'coordinate_plane';
  const isClassifySets = widgetKind === 'classify_sets';

  // Number-line axis (CP.B / 6.NS.6): proper targets sit on 0–1, improper stretch the right
  // end (5/4 → 0–2), negatives the left (−3/4 → −1…1). `unitSegments` is ticks-per-whole (the
  // target denominator); the slider works in TOTAL ticks across the axis.
  const axisMin = problem.axis_min ?? 0;
  const axisMax = problem.axis_max ?? 1;
  const unitSegments = problem.tick_segments ?? 1;
  const totalSegments = (axisMax - axisMin) * unitSegments;

  let submittedAnswer: string;
  let canSubmit: boolean;
  if (isYesNo) {
    submittedAnswer = yesNoToAnswer(yesNo);
    canSubmit = yesNo !== null;
  } else if (isNumberLine) {
    // The placed amount is the signed fraction (axisMin·unitSegments + tick)/unitSegments —
    // so a marker past 1 reads as 5/4 and a marker left of 0 as −3/4 (SymPy judges by exact
    // equality, so the unreduced form is fine).
    const placed = tick === null ? null : tickFraction(tick, axisMin, unitSegments);
    submittedAnswer =
      placed === null ? '' : `${String(placed.numerator)}/${String(placed.denominator)}`;
    canSubmit = tick !== null;
  } else if (isNumberEntry) {
    submittedAnswer = numberAnswer;
    canSubmit = numberAnswer !== '';
  } else if (isExpression) {
    // The typed algebra string; SymPy grades it by equivalence, so we only require non-empty here.
    submittedAnswer = expression;
    canSubmit = expression.trim() !== '';
  } else if (isInequality) {
    // The composed inequality string ("x>=5"). The widget persists a relation-only partial ("x>")
    // so the picked button sticks, so we gate submit on COMPLETENESS (a relation AND a real
    // boundary), not mere non-emptiness. SymPy grades the complete inequality (§8.2).
    submittedAnswer = inequality;
    canSubmit = isCompleteInequality(inequality, 'x');
  } else if (isCoordinate) {
    // The plotted-points string; "" until at least one point is placed. The backend grades it by
    // point-set equality (order-insensitive — §8.2).
    submittedAnswer = coordinate;
    canSubmit = coordinate !== '';
  } else if (isClassifySets) {
    // The comma-joined number-set labels; "" until at least one set is selected. The backend grades
    // it by set membership (§8.2).
    submittedAnswer = numberSets;
    canSubmit = numberSets !== '';
  } else {
    submittedAnswer = fractionToAnswer(fraction);
    canSubmit = submittedAnswer !== '';
  }

  // Submit one answer string through the turn loop and fold in the verdict. Shared by the normal
  // form submit (the widget-derived answer) and the camera read-back confirm (the OCR'd answer) —
  // both land at the SAME /turn, so a snapped answer is graded by the same SymPy verifier as a typed
  // one (HR.C1/C3, §8.2). Assumes phase is already 'submitting' and the spent offers are cleared.
  async function submitAnswerValue(answer: string): Promise<void> {
    telemetry.track('submit', {
      problem_id: problem.problem_id,
      latency_ms: Date.now() - startedAt.current,
      hint_used: hintUsed,
    });
    try {
      const response = await submitTurn({
        session_id: sessionId,
        problem_id: problem.problem_id,
        action: 'submit_answer',
        submitted_answer: answer,
        surface_state: surfaceState,
        latency_ms: Date.now() - startedAt.current,
        hint_used: hintUsed,
      });
      setResult(response);
      setLastAnswer(answer);
      setMastery((prev) => mergeMastery(prev, response.mastery ?? []));
      setTransitionReason(null); // the reason for THIS problem has done its job
      setAdaptation(null); // the live adaptation banner clears once the learner answers
      if (response.correct) {
        const newlyMastered =
          !goalMastered && (response.mastery ?? []).some((m) => m.kc_id === goalKc && m.mastered);
        // unassisted correct is worth more than a hinted one; a wrong answer earns nothing
        // (never negative); declaring mastery is the honest jackpot (RD.0.2).
        setSparks((s) => s + (hintUsed ? 1 : 3) + (newlyMastered ? 10 : 0));
      }
      setPhase('feedback');
    } catch {
      setError('Something went wrong sending your answer. Give it another try.');
      setPhase('answering');
    }
  }

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (phase !== 'answering' || !canSubmit) return;
    setPhase('submitting');
    setError(null);
    setIntervention(null); // the offer pertained to this attempt; it is now spent
    setMidNudge(null); // a mid-problem nudge is spent once the learner answers
    await submitAnswerValue(submittedAnswer);
  }

  async function handleHint(): Promise<void> {
    if (phase !== 'answering') return;
    setError(null);
    telemetry.track('hint_request', {
      problem_id: problem.problem_id,
      elapsed_ms: Date.now() - startedAt.current,
    });
    try {
      const response = await submitTurn({
        session_id: sessionId,
        problem_id: problem.problem_id,
        action: 'request_hint',
        surface_state: surfaceState,
        latency_ms: Date.now() - startedAt.current,
        hint_used: hintUsed,
      });
      setHint(response.hint ?? null);
      setHintUsed(true);
    } catch {
      setError('Could not load a hint right now.');
    }
  }

  // The camera beat (HR.C1/C3) — the learner photographs the work they did on paper instead of
  // typing it. Read the file → POST /transcribe-answer → show the read-back ("I read this as 3/4 —
  // right?"). It NEVER grades off the scan directly: an unreadable image asks for a retake, and a
  // readable one waits for the learner to confirm before it goes through the normal /turn (§8.2).
  async function handleSnap(event: React.ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0];
    // Clear the input so picking the same file again still fires onChange (retake the same photo).
    event.target.value = '';
    if (!file || phase !== 'answering') return;
    setError(null);
    setScanning(true);
    setReadBack(null);
    // (No telemetry event for the snap itself: `answer_scan` isn't in TelemetryEventType / the
    // backend /events vocabulary yet. Flagged to T1; cheap to add when wanted.)
    try {
      const dataUrl = await fileToDataUrl(file);
      setReadBack(await transcribeAnswer(dataUrl));
    } catch {
      setError('We could not read that photo. You can try again or type your answer.');
    } finally {
      setScanning(false);
    }
  }

  // Confirm a readable scan ("yes, that's my answer") → submit the transcribed string through the
  // SAME /turn the typed path uses. Mirrors handleSubmit's guards.
  async function handleConfirmScan(): Promise<void> {
    if (phase !== 'answering' || readBack?.transcribed_answer == null) return;
    const answer = readBack.transcribed_answer;
    setPhase('submitting');
    setError(null);
    setReadBack(null);
    setIntervention(null);
    setMidNudge(null);
    await submitAnswerValue(answer);
  }

  function handleNext(): void {
    const next = result?.next_problem;
    if (!next) return;
    // Preserve the work we are leaving behind (refuse-rule 2): the problem just finished,
    // the answer given, and whether it was right.
    setPrevWork({
      statement: problem.statement,
      answer: lastAnswer ?? '',
      correct: result.correct,
    });
    setProblem(next);
    setProblemNumber((n) => n + 1);
    const changed = result.next_surface_state !== surfaceState;
    setSurfaceState(result.next_surface_state);
    // A live adaptation's own reason takes precedence over the static transition copy (HR.B5);
    // otherwise fall back to the per-state line when the surface changed.
    const liveAdaptation = result.adaptation ?? null;
    setAdaptation(liveAdaptation);
    setTransitionReason(
      liveAdaptation
        ? liveAdaptation.reason
        : changed
          ? TRANSITION_REASON[result.next_surface_state]
          : null,
    );
    setFraction(initialFraction(next));
    setTick(null);
    setYesNo(null);
    setNumberAnswer('');
    setExpression('');
    setInequality('');
    setCoordinate('');
    setNumberSets('');
    setHint(null);
    setHintUsed(false);
    setRevealCount(1);
    setLastAnswer(null);
    setReadBack(null); // a fresh problem starts with no scan in flight (it's per-problem)
    setScanning(false);
    // Carry any proactive offer the just-finished turn produced onto this next problem.
    setIntervention(result.intervention ?? null);
    setMidNudge(null); // a fresh problem starts with no mid-problem nudge (it's per-problem)
    setResult(null);
    setPhase('answering');
    startedAt.current = Date.now();
  }

  // Number-line verdict narration (Slice AR.1, AUDIT.md §3 cap 4): on the number-line widget the
  // mascot SPEAKS the right/wrong verdict — a deliberate, scoped exception to the old "help
  // moments only" rule (Slice 5.5.2), because making the placed magnitude felt is a core feature
  // of this surface. On CORRECT we name the placed fraction ("this is 1/4 of a whole"), derived
  // from the tick the learner placed (which, being correct, equals the target). On WRONG we keep
  // it NEUTRAL and non-shaming and never reveal the answer (the widget likewise shows no snap).
  const verdictSpeech: { text: string; kind: 'correct' | 'neutral' } | null =
    phase === 'feedback' && isNumberLine && result !== null && !goalMastered
      ? result.correct
        ? {
            text: `That's correct — this is ${submittedAnswer} of a whole.`,
            kind: 'correct',
          }
        : { text: "Not quite — let's look at this together.", kind: 'neutral' }
      : null;

  // Pi's nav menu items (the global "home button"). Dashboard → leave to the course map;
  // Homework → the homework flow; Save & exit → also leaves home (a signed-in learner's
  // progress already persists per-turn, so "exit" simply leaves — no fake save UI). Each
  // entry is shown only when its handler exists, so the demo never offers a dead choice.
  const navItems: PiMenuItem[] = [];
  if (onExit !== undefined) {
    navItems.push({ id: 'dashboard', label: 'Dashboard', icon: 'dashboard', onSelect: onExit });
  }
  if (onHomework !== undefined) {
    navItems.push({ id: 'homework', label: 'Homework', icon: 'homework', onSelect: onHomework });
  }
  if (onExit !== undefined) {
    navItems.push({ id: 'exit', label: 'Save & exit', icon: 'exit', onSelect: onExit });
  }
  // When nav handlers exist, Pi is rendered via PiMenu (which has no speech of its own), so the
  // mascot's lines surface in the wm-tutor-speech bubble beside it. With NO nav handlers the bare
  // <Mascot> renders its own speech bubble, so we route the verdict THERE to avoid showing it
  // twice. Either way the learner hears one voice in one place.
  const mascotIsPiMenu = navItems.length > 0;

  // The mascot's spoken line in the wm-tutor-speech bubble. Help moments (a requested hint or an
  // unasked proactive nudge, Slice 5.5.2) are voiced by one character so the surface keeps a
  // single voice; the gesture (offered vs. requested) is kept distinct on the bubble. AR.1 adds
  // routine number-line verdict narration in the feedback phase — but only on the PiMenu path
  // (the bare-Mascot path speaks it itself). A requested hint is the freshest, most specific
  // help, so it wins; then a carried-over offer; then the verdict line.
  const helpSpeech =
    hint !== null
      ? { text: hint, kind: 'hint' as const }
      : midNudge !== null && phase === 'answering'
        ? { text: midNudge.text, kind: 'offer' as const }
        : intervention !== null
          ? { text: intervention.text, kind: 'offer' as const }
          : verdictSpeech !== null && mascotIsPiMenu
            ? { text: verdictSpeech.text, kind: verdictSpeech.kind }
            : null;

  return (
    <main className="wm-tutor">
      {/* The ← Course-path plaque and the sparks plaque are carved-wood plaques (the "wood behind
          course path and spark"). The bar floats transparently over the top of the world so the
          lesson background runs ALL the way up behind it (owner request); the lesson title moved
          down onto the big wood banner below. */}
      <header className="wm-tutor-topbar">
        <div className="wm-tutor-topbar-left">
          {onExit !== undefined ? (
            <button type="button" className="wm-tutor-back" onClick={onExit}>
              <WoodBanner variant="wide" className="wm-tutor-chip-banner">
                ← Course path
              </WoodBanner>
            </button>
          ) : null}
        </div>
        <div className="wm-tutor-topbar-right">
          <WoodBanner variant="wide" className="wm-tutor-chip-banner">
            <SparkCount total={sparks} />
          </WoodBanner>
        </div>
      </header>

      {/* The storybook WORLD stage: the lesson plays out over the village background, which now
          runs all the way up behind the floating top bar. A carved wooden BANNER (9-slice PNG
          frame) carries the lesson TITLE at the top of the world (owner request), then the
          floating cream problem card (the calm working surface — every answer widget, the actions,
          feedback / mastered / worked-example blocks). Pi, the companion + global nav, stands at
          the bottom-right. */}
      <section
        className="wm-tutor-stage"
        style={{ '--wm-tutor-bg': lessonBackground(problem.kc) } as React.CSSProperties}
      >
        <WoodBanner variant="long" className="wm-tutor-titlebanner">
          <p className="wm-tutor-banner-eyebrow">Lesson</p>
          <h1 className="wm-tutor-banner-title">{lessonTitle}</h1>
        </WoodBanner>

        <section className="wm-tutor-card" aria-live="polite">
          {mastery.length > 0 ? (
            <div className="wm-tutor-progress" aria-label="Your progress so far">
              {mastery.map((m) => (
                <div
                  key={m.kc_id}
                  className={`wm-tutor-progress-item ${
                    m.kc_id === goalKc ? 'wm-tutor-progress-item--goal' : ''
                  }`}
                >
                  <span className="wm-tutor-progress-label">
                    {KC_LABEL[m.kc_id] ?? m.kc_id}
                    {m.mastered ? ' ✓' : ''}
                  </span>
                  <span className="wm-tutor-progress-track">
                    <span
                      className={`wm-tutor-progress-fill ${
                        m.mastered ? 'wm-tutor-progress-fill--mastered' : ''
                      }`}
                      style={{
                        width: `${String(Math.min(100, Math.round((m.probability / MASTERY_THRESHOLD) * 100)))}%`,
                      }}
                    />
                  </span>
                </div>
              ))}
            </div>
          ) : null}
          {prevWork !== null && phase !== 'feedback' ? (
            <div className="wm-tutor-prevwork" aria-label="Your previous answer">
              <span className="wm-tutor-prevwork-label">Last one</span>
              <span className="wm-tutor-prevwork-statement">{prevWork.statement}</span>
              <span
                className={`wm-tutor-prevwork-answer wm-tutor-prevwork-answer--${
                  prevWork.correct ? 'right' : 'wrong'
                }`}
              >
                you said {prevWork.answer || '—'} {prevWork.correct ? '✓' : '✗'}
              </span>
            </div>
          ) : null}
          {isProbe && phase !== 'feedback' ? (
            <p className="wm-tutor-probe-badge">Final check — prove you&rsquo;ve really got it</p>
          ) : null}
          {adaptation !== null && phase !== 'feedback' ? (
            <AdaptationBanner
              adaptation={adaptation}
              onDismiss={() => {
                setAdaptation(null);
                setTransitionReason(null);
              }}
            />
          ) : transitionReason !== null && phase !== 'feedback' ? (
            <p className="wm-tutor-reason" role="note">
              {transitionReason}
            </p>
          ) : null}
          <h2 className="wm-tutor-statement">{problem.statement}</h2>

          {phase !== 'feedback' ? (
            <form className="wm-tutor-form" onSubmit={handleSubmit}>
              {isYesNo ? (
                <YesNo
                  value={yesNo}
                  onChange={(v) => {
                    setYesNo(v);
                    noteInteraction('yesno', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Your answer"
                />
              ) : isNumberLine && problem.tick_segments != null ? (
                <NumberLine
                  segments={totalSegments}
                  unitSegments={unitSegments}
                  axisMin={axisMin}
                  axisMax={axisMax}
                  value={tick}
                  onChange={(v) => {
                    setTick(v);
                    noteInteraction('numberline', { tick: v, segments: totalSegments });
                  }}
                  disabled={phase === 'submitting'}
                />
              ) : isNumberEntry ? (
                <NumberEntry
                  value={numberAnswer}
                  onChange={(v) => {
                    setNumberAnswer(v);
                    noteInteraction('number', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Your answer"
                  unit="equal pieces"
                />
              ) : isExpression ? (
                <ExpressionInput
                  value={expression}
                  onChange={(v) => {
                    setExpression(v);
                    noteInteraction('expression', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Write the expression"
                />
              ) : isInequality ? (
                <InequalityInput
                  value={inequality}
                  onChange={(v) => {
                    setInequality(v);
                    noteInteraction('inequality', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Build the inequality"
                />
              ) : isCoordinate ? (
                <CoordinatePlane
                  value={coordinate}
                  onChange={(v) => {
                    setCoordinate(v);
                    noteInteraction('coordinate', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                />
              ) : isClassifySets ? (
                <ClassifySets
                  value={numberSets}
                  onChange={(v) => {
                    setNumberSets(v);
                    noteInteraction('number_sets', { value: v });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Which sets does it belong to?"
                />
              ) : (
                <SymbolicEditor
                  value={fraction}
                  onChange={(v) => {
                    setFraction(v);
                    noteInteraction('fraction', {
                      numerator: v.numerator,
                      denominator: v.denominator,
                    });
                  }}
                  disabled={phase === 'submitting'}
                  prompt="Your answer"
                  lockDenominator={problem.given_denominator != null}
                />
              )}
              <div className="wm-tutor-actions">
                <button
                  type="submit"
                  className="wm-tutor-submit"
                  disabled={phase === 'submitting' || !canSubmit}
                >
                  {phase === 'submitting' ? 'Checking…' : 'Check it'}
                </button>
                <button
                  type="button"
                  className="wm-tutor-hint-btn"
                  onClick={() => {
                    void handleHint();
                  }}
                  disabled={phase === 'submitting'}
                >
                  I'd like a hint
                </button>
                {/* Camera beat (HR.C1/C3): "snap your work" — a label wrapping a hidden file input
                    that opens the camera on a phone (capture="environment") or a file picker on
                    desktop. The photo is read back for confirmation before it's graded. */}
                <label
                  className={`wm-tutor-snap${scanning ? ' wm-tutor-snap--busy' : ''}`}
                  aria-disabled={phase === 'submitting' || scanning}
                >
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    className="wm-tutor-snap-input"
                    onChange={(e) => {
                      void handleSnap(e);
                    }}
                    disabled={phase === 'submitting' || scanning}
                  />
                  <span className="wm-tutor-snap-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path
                        d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2l1.2-1.8A1 1 0 0 1 9.5 5h5a1 1 0 0 1 .8.4L16.5 7h2A1.5 1.5 0 0 1 20 8.5v9A1.5 1.5 0 0 1 18.5 19h-13A1.5 1.5 0 0 1 4 17.5z"
                        strokeLinejoin="round"
                      />
                      <circle cx="12" cy="12.5" r="3.2" />
                    </svg>
                  </span>
                  {scanning ? 'Reading…' : 'Snap your work'}
                </label>
              </div>

              {/* The read-back: what the scanner read, shown for confirmation BEFORE grading. A
                  readable scan offers "Yes, use it" (→ /turn) + "Retake"; an unreadable one only
                  asks for a retake. Never grades a scan the learner hasn't confirmed (HR.C3). */}
              {readBack !== null ? (
                <div className="wm-tutor-readback" role="status" aria-live="polite">
                  <p className="wm-tutor-readback-prompt">
                    {readBack.readable && readBack.transcribed_answer != null
                      ? 'I read your work — does this look right?'
                      : "I couldn't read that one. Try a clearer photo, or just type your answer."}
                  </p>
                  {readBack.readable && readBack.transcribed_answer != null ? (
                    <>
                      <p className="wm-tutor-readback-answer">{readBack.transcribed_answer}</p>
                      <div className="wm-tutor-readback-actions">
                        <button
                          type="button"
                          className="wm-tutor-readback-confirm"
                          onClick={() => {
                            void handleConfirmScan();
                          }}
                          disabled={phase === 'submitting'}
                        >
                          Yes, use it
                        </button>
                        <label className="wm-tutor-readback-retake">
                          <input
                            type="file"
                            accept="image/*"
                            capture="environment"
                            className="wm-tutor-snap-input"
                            onChange={(e) => {
                              void handleSnap(e);
                            }}
                            disabled={phase === 'submitting' || scanning}
                          />
                          Retake
                        </label>
                      </div>
                    </>
                  ) : (
                    <label className="wm-tutor-readback-retake wm-tutor-readback-retake--solo">
                      <input
                        type="file"
                        accept="image/*"
                        capture="environment"
                        className="wm-tutor-snap-input"
                        onChange={(e) => {
                          void handleSnap(e);
                        }}
                        disabled={phase === 'submitting' || scanning}
                      />
                      Retake the photo
                    </label>
                  )}
                </div>
              ) : null}
            </form>
          ) : (
            <div className="wm-tutor-feedback-block">
              {/* Number-line feedback (Slice AR.1): keep the line visible (read-only) and pass the
                  verdict, so a CORRECT answer animates the marker 0→placed-tick and draws the
                  segment, while a WRONG answer just freezes the placement (no reveal, no snap). */}
              {isNumberLine && problem.tick_segments != null ? (
                <NumberLine
                  segments={totalSegments}
                  unitSegments={unitSegments}
                  axisMin={axisMin}
                  axisMax={axisMax}
                  value={tick}
                  onChange={() => {
                    /* read-only in feedback */
                  }}
                  disabled
                  verdict={result?.correct ? 'correct' : 'incorrect'}
                />
              ) : null}
              {goalMastered ? (
                <div className="wm-tutor-mastered" role="status">
                  <p className="wm-tutor-mastered-title">
                    <span className="wm-tutor-mastered-star" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d={STAR_PATH} />
                      </svg>
                    </span>
                    You mastered {KC_LABEL[goalKc] ?? 'this skill'}!
                  </p>
                  <p className="wm-tutor-mastered-sub">
                    You got it right across different forms — that&rsquo;s real understanding, not
                    one lucky answer.
                  </p>
                </div>
              ) : (
                <p
                  className={`wm-tutor-feedback wm-tutor-feedback--${result?.correct ? 'right' : 'wrong'}`}
                >
                  {result?.feedback}
                </p>
              )}
              {result?.worked_example && result.worked_example.length > 0 ? (
                <div className="wm-tutor-worked" aria-label="Worked example">
                  <p className="wm-tutor-worked-title">
                    Here&rsquo;s one worked out, step by step:
                  </p>
                  <ol className="wm-tutor-worked-steps">
                    {result.worked_example.slice(0, revealCount).map((step, i) => (
                      <li key={i} className="wm-tutor-worked-step">
                        <span className="wm-tutor-worked-shown">{step.shown}</span>
                        <span className="wm-tutor-worked-why">{step.why_prompt}</span>
                      </li>
                    ))}
                  </ol>
                  {revealCount < result.worked_example.length ? (
                    <button
                      type="button"
                      className="wm-tutor-worked-more"
                      onClick={() => {
                        setRevealCount((c) => c + 1);
                      }}
                    >
                      Show me the next step
                    </button>
                  ) : null}
                </div>
              ) : null}
              {/* Explain-after-correct (live loop Beat 2): on a CORRECT answer, affirm WHY it
                  worked before moving on — a celebrate-and-consolidate beat, not the stuck-path
                  rescue above. All steps shown at once (it's a quick "here's why", not a walkthrough). */}
              {(result?.correct ?? false) &&
              result?.explanation &&
              result.explanation.length > 0 ? (
                <div className="wm-tutor-explain" aria-label="Why that works">
                  <p className="wm-tutor-explain-title">Nice — here&rsquo;s why that works:</p>
                  <ol className="wm-tutor-explain-steps">
                    {result.explanation.map((step, i) => (
                      <li key={i} className="wm-tutor-explain-step">
                        <span className="wm-tutor-explain-shown">{step.shown}</span>
                        <span className="wm-tutor-explain-why">{step.why_prompt}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ) : null}
              {goalMastered && onExit !== undefined ? (
                // Mastered: the owner's flow wants the learner sent BACK HOME, told clearly they
                // mastered the skill. "Back to home" (onExit → the course map) is the visible
                // primary; a quieter "Keep practicing" stays for anyone who wants to keep going.
                <div className="wm-tutor-mastered-actions">
                  <button type="button" className="wm-tutor-next" onClick={onExit}>
                    Back to home
                  </button>
                  {result?.next_problem ? (
                    <button type="button" className="wm-tutor-keep-practicing" onClick={handleNext}>
                      Keep practicing
                    </button>
                  ) : null}
                </div>
              ) : result?.next_problem ? (
                <button type="button" className="wm-tutor-next" onClick={handleNext}>
                  {goalMastered ? 'Keep practicing' : 'Next problem'}
                </button>
              ) : null}
            </div>
          )}

          {error !== null ? (
            <p className="wm-tutor-error" role="alert">
              {error}
            </p>
          ) : null}
          {/* A small problem counter in the card's bottom-right corner (owner request) — the
              learner's position in the ramp, e.g. "1/13". Capped at the lesson length so the old
              unbounded loop can't render a nonsensical "14/13". */}
          <span className="wm-tutor-card-counter" aria-label="Problem number">
            {Math.min(problemNumber, lessonLength)}/{lessonLength}
          </span>
        </section>

        {/* Pi stands at the bottom-right of the world (the mock's placement) — the companion AND
            the global nav (tap to open Dashboard / Homework / Save & exit). The help-speech
            bubble floats to Pi's left on help moments; bubble and menu share Pi, so they never
            show at once (the bubble collapses while the menu is open, and returns on close). */}
        <div className="wm-tutor-mascot-area">
          {helpSpeech !== null && !navOpen ? (
            <p className={`wm-tutor-speech wm-tutor-speech--${helpSpeech.kind}`} role="note">
              {helpSpeech.text}
            </p>
          ) : null}
          {navItems.length > 0 ? (
            <div className="wm-tutor-pi-fig">
              <PiMenu items={navItems} label="Open the menu" onOpenChange={setNavOpen} />
            </div>
          ) : (
            // No nav handlers (e.g. an embedded preview): the bare mascot carries the verdict
            // line itself via its own `speech` bubble (Slice AR.1). With nav handlers present the
            // PiMenu owns the figure and the line shows in the wm-tutor-speech bubble above.
            <div className="wm-tutor-pi-fig">
              <Mascot speech={verdictSpeech?.text} speechKind={verdictSpeech?.kind ?? 'say'} />
            </div>
          )}
        </div>
      </section>
    </main>
  );
}
