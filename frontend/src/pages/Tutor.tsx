import { useEffect, useRef, useState } from 'react';

import {
  submitTurn,
  type AdaptationView,
  type Emotion,
  type InterventionView,
  type MasterySnapshot,
  type ProblemView,
  type SpokenAudio,
  type StartSessionResponse,
  type SurfaceState,
  type TurnResponse,
} from '../api';
import {
  HelpLanguageToggle,
  Mascot,
  PiMenu,
  SparkCount,
  WoodBanner,
  type PiMenuItem,
} from '../components';
import { useGuideSpeech } from '../components/avatar/useGuideSpeech';
import { WorkCamera } from '../components/WorkCamera';
import { useHelpLocale } from '../state/LocaleContext';
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
  SceneStimulus,
  selectWidget,
  SetModelStimulus,
  StatsStimulus,
  SymbolicEditor,
  tickFraction,
  YesNo,
  yesNoToAnswer,
  type FractionValue,
} from '../workspace';
import './Tutor.css';

const EMPTY_FRACTION: FractionValue = { numerator: '', denominator: '' };

// The pool of storybook-world backdrops a lesson can wear (frontend/public/tutor-bg-*.jpg).
// Each is pre-toned: edge-cropped (no generator watermark), softened, and faintly blue so it
// stays a calm backdrop behind the problem card (a further blur + blue wash is added in CSS).
// Listed explicitly (not 1..N) so the pool only ever names files that actually exist on disk —
// removing a backdrop file means removing its entry here, and no lesson can pick a missing image.
export const TUTOR_BACKGROUNDS: readonly string[] = [
  '/tutor-bg-1.jpg',
  '/tutor-bg-4.jpg',
  '/tutor-bg-5.jpg',
  '/tutor-bg-6.jpg',
  '/tutor-bg-7.jpg',
  '/tutor-bg-8.jpg',
  '/tutor-bg-9.jpg',
  '/tutor-bg-10.jpg',
  '/tutor-bg-11.jpg',
];

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

// Human names for the per-KC progress strip (the mastery snapshot keys on KC id) AND the header
// title fallback. Covers EVERY live KC (the backend registry's 39 KCs), so no surface ever renders
// a raw `KC_foo` id — the strip can show any KC the session touches (the goal KC plus interleaved
// companions), and the header falls back here when `KC_TITLE` has no fuller phrasing. The first
// five fraction KCs keep their terse kid-friendly strip labels; the rest use the registry's
// `skill_name` (knowledge_components.py) verbatim, the one source of truth for a KC's human name —
// keep this list in sync when a new KC enters `LIVE_KCS`.
const KC_LABEL: Record<string, string> = {
  // The five foundation fraction KCs — terse, kid-friendly strip labels.
  KC_equivalence: 'Equivalent fractions',
  KC_common_denominator: 'Common denominator',
  KC_addition_unlike: 'Adding fractions',
  KC_subtraction_unlike: 'Subtracting fractions',
  KC_number_line_placement: 'Number line',
  // The Grade-6 KCs — the registry `skill_name` for each (knowledge_components.py).
  KC_ratio_language: 'Read ratio language',
  KC_unit_rate: 'Find a unit rate',
  KC_equivalent_ratios: 'Find an equivalent ratio',
  KC_percent: 'Find a percent of a number',
  KC_multiply_fractions: 'Multiply two fractions',
  KC_divide_fractions: 'Divide two fractions',
  KC_unit_conversion: 'Convert units via proportions',
  KC_gcf_lcm: 'Find the GCF or LCM',
  KC_multi_digit_division: 'Divide multi-digit whole numbers',
  KC_decimal_operations: 'Operate on decimals',
  KC_absolute_value: 'Find an absolute value',
  KC_integer_add_subtract: 'Add and subtract integers',
  KC_signed_numbers: 'Find the opposite of a number',
  KC_summary_statistics: 'Summarize a data set with one number',
  KC_data_displays: 'Read a data display',
  KC_write_expressions: 'Writing expressions',
  KC_evaluate_expressions: 'Evaluate an expression',
  KC_exponents: 'Evaluate an exponent',
  KC_one_step_equations: 'Solve a one-step equation',
  KC_equivalent_expressions: 'Write an equivalent expression',
  KC_inequalities: 'Write an inequality',
  KC_coordinate_plane: 'Plot points in the coordinate plane',
  KC_classify_number_sets: 'Classify number sets',
  KC_expression_parts: 'Identify parts of an expression',
  KC_integer_multiply_divide: 'Multiply and divide integers',
  KC_triangle_properties: 'Apply triangle properties',
  KC_area_polygons: 'Find the area of polygons',
  KC_volume_fractional_edges: 'Find the volume of a prism with fractional edges',
  KC_polygons_coordinate_plane: 'Draw polygons in the coordinate plane',
  KC_surface_area_nets: 'Find the surface area of a prism from its net',
  KC_mean_absolute_deviation: 'Find the mean absolute deviation of a data set',
  KC_center_spread_shape: 'Describe a distribution by center and spread',
  KC_categorical_data: 'Summarize categorical data',
  KC_statistical_questions: 'Recognize statistical questions',
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
  // The live help-language (Slice 3.6). Threaded into every /turn so hints/nudges come back
  // localized as soon as the learner flips the toggle — no page reload, no session restart. It
  // localizes the HELP surface ONLY; the served problem stays English (Rung-0 deferred, see below).
  const { locale } = useHelpLocale();
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
      const response = await submitTurn(
        {
          session_id: sessionId,
          problem_id: problem.problem_id,
          action: 'submit_answer',
          submitted_answer: answer,
          surface_state: surfaceState,
          latency_ms: Date.now() - startedAt.current,
          hint_used: hintUsed,
        },
        locale,
      );
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
      const response = await submitTurn(
        {
          session_id: sessionId,
          problem_id: problem.problem_id,
          action: 'request_hint',
          surface_state: surfaceState,
          latency_ms: Date.now() - startedAt.current,
          hint_used: hintUsed,
        },
        locale,
      );
      // Carry the FULL hint response into `result`, not just the caption text. helpAudio reads
      // `result.hint_audio` and guideEmotion reads `result.hint_emotion` (both gated on
      // `hint !== null`), so without this the bubble showed the hint but the mascot never voiced it
      // and never emoted — the audio/emotion were silently dropped. Safe in the answering phase: the
      // verdict/feedback panel is gated on `phase === 'feedback'` (the form/feedback ternary), which
      // a hint never enters, so this only feeds the voice + emotion, never a verdict.
      setResult(response);
      setHint(response.hint ?? null);
      setHintUsed(true);
    } catch {
      setError('Could not load a hint right now.');
    }
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

  // The live emotion the mascot PLAYS, kept in lock-step with the line it is speaking (helpSpeech).
  // The backend already chooses the emotion deterministically in policy (slice 1.3, §8.3 — never
  // the LLM): a requested hint carries `hint_emotion`/`hint_intensity` on the turn result; a
  // proactive nudge/offer carries `emotion`/`intensity` on its InterventionView. The number-line
  // verdict line has no backend emotion, so we map it tastefully (correct → celebrate, otherwise →
  // reassure). When nothing is being said the figure rests at no emotion (undefined).
  const guideEmotion: { emotion: Emotion; intensity: number } | null =
    hint !== null
      ? result?.hint_emotion != null
        ? { emotion: result.hint_emotion, intensity: result.hint_intensity ?? 0 }
        : null
      : midNudge !== null && phase === 'answering'
        ? midNudge.emotion != null
          ? { emotion: midNudge.emotion, intensity: midNudge.intensity ?? 0 }
          : null
        : intervention !== null
          ? intervention.emotion != null
            ? { emotion: intervention.emotion, intensity: intervention.intensity ?? 0 }
            : null
          : verdictSpeech !== null && mascotIsPiMenu
            ? verdictSpeech.kind === 'correct'
              ? { emotion: 'celebrate', intensity: 0.8 }
              : { emotion: 'reassure', intensity: 0.5 }
            : null;

  // The cached audio for the line currently being spoken (Slice AR.3), in LOCK-STEP with helpSpeech:
  // a requested hint carries `hint_audio`; a mid-problem nudge / proactive offer carries `audio` on
  // its InterventionView. Present ONLY for a banked line with pre-rendered audio — every other line
  // (a rephrased hint, the verdict narration, an unrendered nudge) is null, so the mascot stays
  // silent + captions-only (today's behavior). The hook honors the persisted mute and reduced-motion.
  const helpAudio: SpokenAudio | null =
    hint !== null
      ? (result?.hint_audio ?? null)
      : midNudge !== null && phase === 'answering'
        ? (midNudge.audio ?? null)
        : intervention !== null
          ? (intervention.audio ?? null)
          : null;
  const { speaking, viseme } = useGuideSpeech(helpAudio);

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
          {/* Display-only counter jar (ratio-language) — the visual anchor, centered above the
              prompt; renders nothing for problems without a set model. */}
          <SetModelStimulus problem={problem} />
          {/* Every other display-only scene (percent grid, ratio table, integer line, fraction
              area, decimal place-value, factors, exponent product), behind one dispatcher; renders
              nothing for problems with no scene. */}
          <SceneStimulus problem={problem} />
          {/* The prompt: a clean 'Situation / Question / Guiding Rule' card when the KC supplies
              structured parts, else the flat statement. `statement` is composed from the same parts
              server-side, so the two never disagree (it stays the accessible fallback). */}
          {problem.prompt_parts != null ? (
            <div className="wm-tutor-prompt">
              <p className="wm-tutor-prompt-line">
                <span className="wm-tutor-prompt-label">The Situation:</span>{' '}
                {problem.prompt_parts.situation}
              </p>
              <p className="wm-tutor-prompt-line">
                <span className="wm-tutor-prompt-label">The Question:</span>{' '}
                {problem.prompt_parts.question}
              </p>
              <p className="wm-tutor-guiding-rule">
                <span className="wm-tutor-prompt-label">Guiding Rule:</span>{' '}
                {problem.prompt_parts.guiding_rule}
              </p>
            </div>
          ) : (
            <h2 className="wm-tutor-statement">{problem.statement}</h2>
          )}
          {/* Display-only stats visual (dot plot / table / histogram) — additive to the prompt
              text, never an answer input. Renders only when the problem carries a stats stimulus. */}
          <StatsStimulus problem={problem} />

          {phase !== 'feedback' ? (
            <form
              className={`wm-tutor-form${
                problem.scene != null || problem.set_model != null ? ' wm-tutor-form--centered' : ''
              }`}
              onSubmit={handleSubmit}
            >
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
              </div>
              {/* The in-lesson camera beat (HR.C1/C3) — only on paper-worked lessons (the backend
                  declares this per lesson via ProblemView.supports_written_work). Confirmed reads
                  go through the normal submit, so SymPy grades a snapped answer like a typed one. */}
              {problem.supports_written_work ? (
                <WorkCamera onConfirm={submitAnswerValue} disabled={phase === 'submitting'} />
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
              <PiMenu
                items={navItems}
                label="Open the menu"
                onOpenChange={setNavOpen}
                emotion={guideEmotion?.emotion}
                intensity={guideEmotion?.intensity}
                speaking={speaking}
                viseme={viseme}
              />
            </div>
          ) : (
            // No nav handlers (e.g. an embedded preview): the bare mascot carries the verdict
            // line itself via its own `speech` bubble (Slice AR.1). With nav handlers present the
            // PiMenu owns the figure and the line shows in the wm-tutor-speech bubble above.
            <div className="wm-tutor-pi-fig">
              <Mascot
                speech={verdictSpeech?.text}
                speechKind={verdictSpeech?.kind ?? 'say'}
                emotion={guideEmotion?.emotion}
                intensity={guideEmotion?.intensity}
                speaking={speaking}
                viseme={viseme}
              />
            </div>
          )}
        </div>
      </section>

      {/* The bilingual HELP toggle (Slice 3.6), bottom-left of the lesson world. Flipping it makes
          subsequent hints/nudges come back in Spanish (captions) with no reload — the choice rides
          the /turn request via the live `locale` above. Pi stands bottom-RIGHT, so this never
          collides. DEFERRED (not stubbed here): the avatar reading the whole PROBLEM aloud in
          Spanish (Rung-0) — that needs Spanish problem-statement translation (3.2b) + es-MX audio
          (3.5), neither built; the on-screen problem stays English. */}
      <HelpLanguageToggle />
    </main>
  );
}
