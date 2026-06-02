// Seeded demo household for the PARENT surface, served by `parent.ts` until a real backend + real
// child logins land (the same deferral the teacher surface carries — see api/teacher.ts). These
// children are AUTHORED to look like the real thing: built on the five shipped fraction KCs and the
// misconceptions the SymPy verifier actually names (natural-number bias, add-across, etc.), so the
// parent dashboard is honest to demo against. The child-detail shape is reused verbatim from the
// teacher's `TeacherStudentView` (api/teacher.ts) — a child IS one learner's drill-in, reframed for
// a parent — so the swap to real data is a client flag, not a page rewrite.
//
// The three children span the ranked categories (struggling / needs-attention / on-track) so the
// per-child status system can be screenshot-verified end-to-end. All series are hand-authored and
// deterministic (NO Math.random / Date.now), so the dashboard renders the same pictures every time.

import type { AssignableUnitView, TeacherStudentView as ChildDetail } from './teacher';

/** A parent note / "things to ask about" item (mirrors the teacher's `TeacherReminder`). */
export interface ParentNote {
  id: string;
  text: string;
  done: boolean;
}

/** One child's at-a-glance card on the household dashboard (the lighter, list-row shape). */
export interface ChildSummary {
  child_id: string;
  name: string;
  grade: number;
  category: ChildDetail['category'];
  /** Plain-parent one-liner for the card (NOT the teacher's clinical category_reason). */
  status_line: string;
  current_unit_title: string | null;
  current_lesson_title: string | null;
  percent_complete: number;
  /** Did this child practice today? Drives the "X of N kids practiced today" summary. */
  practiced_today: boolean;
  /** 10-point recent-accuracy sparkline (0..100), oldest → newest. */
  trend: number[];
}

/** The signed-in parent + their household label + the child cards for the dashboard. */
export interface Household {
  parent_name: string;
  household_label: string;
  children: ChildSummary[];
}

/** Input for adding a child to the household (demo-only; no network, no real account). */
export interface AddChildInput {
  name: string;
  grade: number;
  username: string;
}

// The five shipped fraction KCs, by the display names the course map uses. Shared with the teacher
// demo's vocabulary so the two surfaces describe the same skills the same way.
const SKILL = {
  numberline: { kc_id: 'KC_number_line_placement', skill_name: 'Fractions on the number line' },
  equivalence: { kc_id: 'KC_equivalence', skill_name: 'Equivalent fractions' },
  common: { kc_id: 'KC_common_denominator', skill_name: 'Common denominators' },
  add: { kc_id: 'KC_addition_unlike', skill_name: 'Adding unlike fractions' },
  subtract: { kc_id: 'KC_subtraction_unlike', skill_name: 'Subtracting unlike fractions' },
} as const;

// The next units a child can move into (from CURRICULUM_STANDARD.md's Grade-6 scope). The parent
// surface only READS this (for "What's coming next") — it never assigns, unlike the teacher.
const ALL_UNITS: AssignableUnitView[] = [
  { unit_id: 'u2-fractions-decimals', title: 'Fractions & Decimals', available: true },
  { unit_id: 'u1-ratios-rates', title: 'Ratios & Rates', available: true },
  { unit_id: 'u3-rational-numbers', title: 'Rational Numbers', available: false },
];

// In-memory children added during a demo session (via `addChildInDemo`), appended after the seed
// so a freshly-added child shows up on the household dashboard immediately. Module-level so it
// persists for the life of the page (mirrors the teacher demo's `assignedOverrides` Map).
const addedChildren: ChildDetail[] = [];

// The three seeded children, authored as full drill-ins. One struggling (Jamie, natural-number
// bias — modeled on the teacher demo's Maya), one needs-attention (Alex, add-across), one on-track
// (Riley). `accuracy_history` is a 10-point per-session accuracy series (0..1) for the AreaChart.
const SEED_CHILDREN: ChildDetail[] = [
  {
    student_id: 'child-jamie',
    name: 'Jamie',
    category: 'struggling',
    category_reason:
      'Repeating the same fraction mix-up across several lessons, and accuracy is sliding.',
    alerts: [
      {
        kind: 'REPEATED_MISCONCEPTION',
        severity: 'urgent',
        message: 'Compared fractions by their numbers, not their size, on 4 of the last 6 tries.',
      },
      {
        kind: 'FAILING_TREND',
        severity: 'warn',
        message: 'Accuracy slipped from about 70% to under 40% over the last two sessions.',
      },
    ],
    struggle: {
      headline: 'Jamie is comparing fractions by their numbers, not their size.',
      detail:
        'On "which is bigger, 3/8 or 1/2?" Jamie picks 3/8 because 8 is the bigger number. This ' +
        'is a normal step in learning fractions — it just means the next practice should use the ' +
        'number line, where 1/2 is clearly farther from 0.',
      matched_misconception: 'Natural-number bias',
      helpneed_trend: 'rising',
      recent_error_rate: 0.62,
    },
    current_unit_title: 'Fractions & Decimals',
    current_lesson_title: 'Equivalent fractions',
    percent_complete: 0.28,
    strengths: [{ ...SKILL.numberline, probability: 0.74, status: 'in_progress' }],
    weaknesses: [
      { ...SKILL.equivalence, probability: 0.31, status: 'in_progress' },
      { ...SKILL.common, probability: 0.18, status: 'locked' },
    ],
    activity: [
      {
        at: '20m ago',
        label: 'Compared 3/8 and 1/2, chose 3/8 (bigger bottom number)',
        outcome: 'incorrect',
      },
      { at: '22m ago', label: 'Asked for a hint on equivalent fractions', outcome: 'neutral' },
      { at: '25m ago', label: 'Compared 2/3 and 3/4, chose 2/3', outcome: 'incorrect' },
      { at: '1d ago', label: 'Placed 3/4 on the number line', outcome: 'correct' },
    ],
    assignable_units: ALL_UNITS,
    assigned_unit_id: null,
    remediation_estimate_minutes: 25,
    accuracy_history: [0.7, 0.66, 0.61, 0.58, 0.54, 0.49, 0.47, 0.43, 0.4, 0.38],
    notes: null,
  },
  {
    student_id: 'child-alex',
    name: 'Alex',
    category: 'needs_attention',
    category_reason: 'Off to a strong start but stuck on one step: combining fractions.',
    alerts: [
      {
        kind: 'STUCK',
        severity: 'warn',
        message: 'Three tries in a row finding a common denominator without getting it.',
      },
    ],
    struggle: {
      headline: 'Alex is adding the bottom numbers instead of finding a common denominator.',
      detail:
        'For 1/4 + 1/6 Alex writes a bottom number of 10 (because 4 + 6 = 10). This "add across" ' +
        'mix-up is common right after equivalent fractions are learned. Showing why the pieces ' +
        'have to be the same size — with paper or fraction bars — clears it up quickly.',
      matched_misconception: 'Add-across denominators',
      helpneed_trend: 'steady',
      recent_error_rate: 0.41,
    },
    current_unit_title: 'Fractions & Decimals',
    current_lesson_title: 'Common denominators',
    percent_complete: 0.5,
    strengths: [
      { ...SKILL.numberline, probability: 0.9, status: 'mastered' },
      { ...SKILL.equivalence, probability: 0.85, status: 'mastered' },
    ],
    weaknesses: [{ ...SKILL.common, probability: 0.38, status: 'in_progress' }],
    activity: [
      {
        at: '30m ago',
        label: 'Common denominator for 1/4 and 1/6, answered 10',
        outcome: 'incorrect',
      },
      {
        at: '32m ago',
        label: 'Common denominator for 1/2 and 1/3, answered 5',
        outcome: 'incorrect',
      },
      { at: '4h ago', label: 'Mastered Equivalent fractions', outcome: 'correct' },
    ],
    assignable_units: ALL_UNITS,
    assigned_unit_id: null,
    remediation_estimate_minutes: 15,
    accuracy_history: [0.68, 0.66, 0.67, 0.63, 0.62, 0.6, 0.61, 0.58, 0.59, 0.57],
    notes: null,
  },
  {
    student_id: 'child-riley',
    name: 'Riley',
    category: 'on_track',
    category_reason: 'Steady progress with little help — moving through the unit nicely.',
    alerts: [],
    struggle: {
      headline: 'Riley is moving steadily and rarely needs help.',
      detail:
        'Riley is earning each skill across more than one way of showing it, with very few hints. ' +
        'Nothing to worry about here — a great time to celebrate the streak and keep the habit ' +
        'going.',
      matched_misconception: null,
      helpneed_trend: 'falling',
      recent_error_rate: 0.12,
    },
    current_unit_title: 'Fractions & Decimals',
    current_lesson_title: 'Adding unlike fractions',
    percent_complete: 0.7,
    strengths: [
      { ...SKILL.numberline, probability: 0.94, status: 'mastered' },
      { ...SKILL.equivalence, probability: 0.91, status: 'mastered' },
      { ...SKILL.common, probability: 0.89, status: 'mastered' },
    ],
    weaknesses: [{ ...SKILL.add, probability: 0.66, status: 'in_progress' }],
    activity: [
      { at: '15m ago', label: 'Added 2/5 + 1/3 on their own', outcome: 'correct' },
      { at: '18m ago', label: 'Added 1/2 + 1/4 on the number line', outcome: 'correct' },
      { at: '1d ago', label: 'Mastered Common denominators', outcome: 'correct' },
    ],
    assignable_units: ALL_UNITS,
    assigned_unit_id: null,
    remediation_estimate_minutes: null,
    accuracy_history: [0.72, 0.75, 0.77, 0.8, 0.82, 0.85, 0.87, 0.89, 0.91, 0.93],
    notes: null,
  },
];

// Per-child dashboard-only fields the lighter card needs but the detail shape doesn't carry:
// the child's grade, a plain-parent status line, the practiced-today flag, and the 10-point trend
// (0..100) for the card sparkline. Keyed by child_id, merged in `summaryOf` below.
interface ChildCardExtra {
  grade: number;
  status_line: string;
  practiced_today: boolean;
  trend: number[];
}

const CARD_EXTRA: Record<string, ChildCardExtra> = {
  'child-jamie': {
    grade: 6,
    status_line: 'Could use a little help with comparing fractions right now.',
    practiced_today: true,
    trend: [70, 66, 61, 58, 54, 49, 47, 43, 40, 38],
  },
  'child-alex': {
    grade: 6,
    status_line: 'Doing well, just stuck on one step — combining fractions.',
    practiced_today: true,
    trend: [68, 66, 67, 63, 62, 60, 61, 58, 59, 57],
  },
  'child-riley': {
    grade: 6,
    status_line: 'On track and on a roll.',
    practiced_today: false,
    trend: [72, 75, 77, 80, 82, 85, 87, 89, 91, 93],
  },
};

// Fallback card fields for a freshly-added child (no authored history yet): grade comes from the
// add form, the rest is an honest "just getting started" empty-ish state. Flat trend = "steady".
function fallbackExtra(grade: number): ChildCardExtra {
  return {
    grade,
    status_line: 'Just added — ask them to sign in and start their first lesson.',
    practiced_today: false,
    trend: [50, 50, 50, 50, 50, 50, 50, 50, 50, 50],
  };
}

/** Convert a full child detail into its lighter dashboard card summary. */
function summaryOf(child: ChildDetail): ChildSummary {
  const extra = CARD_EXTRA[child.student_id] ?? fallbackExtra(6);
  return {
    child_id: child.student_id,
    name: child.name,
    grade: extra.grade,
    category: child.category,
    status_line: extra.status_line,
    current_unit_title: child.current_unit_title ?? null,
    current_lesson_title: child.current_lesson_title ?? null,
    percent_complete: child.percent_complete,
    practiced_today: extra.practiced_today,
    trend: extra.trend,
  };
}

/** All children in the household (seed + any added this session), full-detail form. */
function allChildren(): ChildDetail[] {
  return [...SEED_CHILDREN, ...addedChildren];
}

/** The demo household — parent identity + label + the child cards. */
export const DEMO_HOUSEHOLD: Household = {
  parent_name: 'Sam Rivera',
  household_label: 'The Rivera Family',
  children: SEED_CHILDREN.map(summaryOf),
};

/** Rebuild the household summary live, so an added child appears on the next fetch. */
export function demoHousehold(): Household {
  return {
    parent_name: DEMO_HOUSEHOLD.parent_name,
    household_label: DEMO_HOUSEHOLD.household_label,
    children: allChildren().map(summaryOf),
  };
}

/** One child's full drill-in (reused `TeacherStudentView` shape), or null if not in the household. */
export function demoChild(childId: string): ChildDetail | null {
  return allChildren().find((c) => c.student_id === childId) ?? null;
}

/**
 * Append a new child to the in-memory household and return the created child's id + the login the
 * parent should share with the child. Demo-only: NO network call, NO real learner account. The
 * child starts with an empty-ish "just added" detail so the household + detail pages render honestly.
 */
export function addChildInDemo(input: AddChildInput): { childId: string; username: string } {
  // Deterministic id from the running count (no Date.now / Math.random — fixtures stay stable).
  const childId = `child-added-${String(addedChildren.length + 1)}`;
  const firstUnit = ALL_UNITS.find((u) => u.available) ?? null;
  const newChild: ChildDetail = {
    student_id: childId,
    name: input.name,
    category: 'needs_attention',
    category_reason: 'Just added — no practice yet.',
    alerts: [],
    struggle: {
      headline: `${input.name} is just getting started.`,
      detail:
        `Once ${input.name} signs in and finishes a few problems, you'll see exactly how they're ` +
        'doing here — what they worked on, where they shine, and where to lend a hand.',
      matched_misconception: null,
      helpneed_trend: null,
      recent_error_rate: null,
    },
    current_unit_title: firstUnit?.title ?? null,
    current_lesson_title: null,
    percent_complete: 0,
    strengths: [],
    weaknesses: [],
    activity: [],
    assignable_units: ALL_UNITS,
    assigned_unit_id: null,
    remediation_estimate_minutes: null,
    accuracy_history: [],
    notes: null,
  };
  addedChildren.push(newChild);
  // Stash the grade so the card summary reports it (CARD_EXTRA has no entry for added children).
  CARD_EXTRA[childId] = fallbackExtra(input.grade);
  return { childId, username: input.username };
}

/** A few parent-seeded notes for the dashboard's "Notes" card (local toggle, mirrors reminders). */
export const DEMO_PARENT_NOTES: ParentNote[] = [
  { id: 'note-1', text: 'Ask Jamie about the number line at dinner', done: false },
  { id: 'note-2', text: 'Try the paper-folding activity with Alex this weekend', done: false },
  { id: 'note-3', text: 'Tell Riley how proud we are of the streak', done: true },
];
