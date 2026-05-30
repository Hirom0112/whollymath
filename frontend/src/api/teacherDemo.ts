// Seeded demo class for the teacher surface, served by `teacher.ts` until lane T1's real
// /teacher endpoints + TCH.B9 seeded class land. These rows are AUTHORED to look like the real
// thing: built on the five shipped fraction KCs and the misconceptions the SymPy verifier
// actually names (natural-number bias, add-across, etc.), so the dashboard is honest to demo
// against. T1's TCH.B9 replaces this with numbers replayed through the real mastery/verifier
// path; the shapes here match `teacher.ts` so that swap is a client flag, not a page rewrite.
//
// The class spans every ranked category (struggling / needs-attention / on-track) and every
// alert kind, so the ranked roster + alert visual system can be screenshot-verified end-to-end.

import type {
  AssignableUnitView,
  RosterStudentView,
  TeacherRosterView,
  TeacherStudentView,
} from './teacher';

// The five shipped fraction KCs, by the display names the course map uses. Strengths/weaknesses
// and the activity timeline draw from these so the demo never references unbuilt Grade-6 content.
const SKILL = {
  numberline: { kc_id: 'KC_number_line_placement', skill_name: 'Fractions on the number line' },
  equivalence: { kc_id: 'KC_equivalence', skill_name: 'Equivalent fractions' },
  common: { kc_id: 'KC_common_denominator', skill_name: 'Common denominators' },
  add: { kc_id: 'KC_addition_unlike', skill_name: 'Adding unlike fractions' },
  subtract: { kc_id: 'KC_subtraction_unlike', skill_name: 'Subtracting unlike fractions' },
} as const;

// The next units a teacher can assign (from CURRICULUM_STANDARD.md's Grade-6 scope). Availability
// reflects prereqs at a glance; the real gate is the KC DAG server-side (TODO DAT.7, DEC.1).
const ALL_UNITS: AssignableUnitView[] = [
  { unit_id: 'u2-fractions-decimals', title: 'Fractions & Decimals', available: true },
  { unit_id: 'u1-ratios-rates', title: 'Ratios & Rates', available: true },
  { unit_id: 'u3-rational-numbers', title: 'Rational Numbers', available: false },
];

// In-memory assigned-unit overrides so the "Assign next unit" action visibly updates the
// drill-in within a session (TODO TCH.B7 is idempotent; this mirrors that for the demo).
const assignedOverrides = new Map<string, string>();

interface DemoSeed {
  student: TeacherStudentView;
}

const SEED: DemoSeed[] = [
  {
    student: {
      student_id: 'stu-maya',
      name: 'Maya R.',
      category: 'struggling',
      category_reason: 'Repeating the same misconception across 4 lessons, and the trend is down.',
      alerts: [
        {
          kind: 'REPEATED_MISCONCEPTION',
          severity: 'urgent',
          message: 'Natural-number bias on 4 of the last 6 comparisons.',
        },
        {
          kind: 'FAILING_TREND',
          severity: 'warn',
          message: 'Accuracy fell from 70% to 38% over the last two sessions.',
        },
      ],
      struggle: {
        headline: 'Maya is comparing fractions by their whole numbers, not their size.',
        detail:
          'On "which is bigger, 3/8 or 1/2?" she picks 3/8 because 8 > 2. This is natural-number ' +
          'bias: treating numerator and denominator as separate whole numbers. She needs the ' +
          'number line, where 1/2 is visibly farther from 0, before more symbolic comparison.',
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
        { at: '20m ago', label: 'Compared 3/8 and 1/2, chose 3/8 (bigger denominator)', outcome: 'incorrect' },
        { at: '22m ago', label: 'Asked for a hint on equivalent fractions', outcome: 'neutral' },
        { at: '25m ago', label: 'Compared 2/3 and 3/4, chose 2/3', outcome: 'incorrect' },
        { at: '1d ago', label: 'Placed 3/4 on the number line', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-dev',
      name: 'Dev P.',
      category: 'struggling',
      category_reason: 'Dropped to a prerequisite skill and has been stuck there for 3 sessions.',
      alerts: [
        {
          kind: 'REMEDIATION_STUCK',
          severity: 'urgent',
          message: 'In remediation on "Fractions on the number line" without mastering it.',
        },
        {
          kind: 'STUCK',
          severity: 'warn',
          message: '6 attempts on the current problem, no correct answer.',
        },
      ],
      struggle: {
        headline: 'Dev is counting tick marks instead of reasoning about unit size.',
        detail:
          'He places 2/3 by counting two ticks from zero regardless of how the line is ' +
          'partitioned. When the endpoints change, the placement breaks. He needs varied ' +
          'partitions where the unit fraction has to be reasoned about, not counted.',
        matched_misconception: 'Tick-counting (ignores the whole)',
        helpneed_trend: 'steady',
        recent_error_rate: 0.55,
      },
      current_unit_title: 'Fractions & Decimals',
      current_lesson_title: 'Fractions on the number line (remediation)',
      percent_complete: 0.12,
      strengths: [],
      weaknesses: [
        { ...SKILL.numberline, probability: 0.29, status: 'in_progress' },
        { ...SKILL.equivalence, probability: 0.15, status: 'locked' },
      ],
      activity: [
        { at: '5m ago', label: 'Placed 2/3 on a line marked 0 to 2, landed on 2/6', outcome: 'incorrect' },
        { at: '8m ago', label: 'Worked example shown (re-teach)', outcome: 'neutral' },
        { at: '10m ago', label: 'Placed 2/3, landed at the second tick', outcome: 'incorrect' },
        { at: '2d ago', label: 'Entered remediation from Equivalent fractions', outcome: 'neutral' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-liam',
      name: 'Liam T.',
      category: 'needs_attention',
      category_reason: 'Doing the work, but help-need is rising and engagement is thin.',
      alerts: [
        {
          kind: 'LOW_ENGAGEMENT',
          severity: 'warn',
          message: 'Long pauses and quick guesses, then answering before reading.',
        },
      ],
      struggle: {
        headline: 'Liam is rushing, answering before the problem is read.',
        detail:
          'His latency pattern is bimodal: very long idle, then an instant answer. The HelpNeed ' +
          'signal is rising even though accuracy is okay, which usually means disengagement ' +
          'rather than a specific misconception. Worth a check-in before it becomes a slide.',
        matched_misconception: null,
        helpneed_trend: 'rising',
        recent_error_rate: 0.34,
      },
      current_unit_title: 'Fractions & Decimals',
      current_lesson_title: 'Common denominators',
      percent_complete: 0.46,
      strengths: [
        { ...SKILL.numberline, probability: 0.88, status: 'mastered' },
        { ...SKILL.equivalence, probability: 0.81, status: 'mastered' },
      ],
      weaknesses: [{ ...SKILL.common, probability: 0.44, status: 'in_progress' }],
      activity: [
        { at: '1h ago', label: 'Found a common denominator for 1/4 and 1/6', outcome: 'correct' },
        { at: '1h ago', label: 'Idle 90s, then answered in under a second', outcome: 'incorrect' },
        { at: '3h ago', label: 'Mastered Equivalent fractions', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-sofia',
      name: 'Sofia M.',
      category: 'needs_attention',
      category_reason: 'Stalled on common denominators after a strong start.',
      alerts: [
        {
          kind: 'STUCK',
          severity: 'warn',
          message: 'Three wrong attempts on finding a common denominator.',
        },
      ],
      struggle: {
        headline: 'Sofia is adding the denominators instead of finding a common one.',
        detail:
          'For 1/4 + 1/6 she writes a denominator of 10 (4 + 6). The "add across" pattern is ' +
          'common right after equivalence is learned. Fraction bars showing why the pieces must ' +
          'be the same size would target this directly.',
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
        { at: '30m ago', label: 'Common denominator for 1/4 and 1/6, answered 10', outcome: 'incorrect' },
        { at: '32m ago', label: 'Common denominator for 1/2 and 1/3, answered 5', outcome: 'incorrect' },
        { at: '4h ago', label: 'Mastered Equivalent fractions', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-aiden',
      name: 'Aiden K.',
      category: 'needs_attention',
      category_reason: "Hasn't practiced in 5 days; was mid-lesson.",
      alerts: [
        {
          kind: 'IDLE',
          severity: 'info',
          message: 'No activity for 5 days; left mid-lesson on adding fractions.',
        },
      ],
      struggle: {
        headline: 'Aiden has gone quiet: no misconception, just no recent practice.',
        detail:
          'When last active, Aiden was on track. There is no diagnostic signal to act on; this ' +
          'is an engagement nudge, not a learning problem. A quick "pick up where you left off" ' +
          'is likely all that is needed.',
        matched_misconception: null,
        helpneed_trend: null,
        recent_error_rate: null,
      },
      current_unit_title: 'Fractions & Decimals',
      current_lesson_title: 'Adding unlike fractions',
      percent_complete: 0.58,
      strengths: [
        { ...SKILL.numberline, probability: 0.92, status: 'mastered' },
        { ...SKILL.equivalence, probability: 0.86, status: 'mastered' },
        { ...SKILL.common, probability: 0.83, status: 'mastered' },
      ],
      weaknesses: [{ ...SKILL.add, probability: 0.52, status: 'in_progress' }],
      activity: [
        { at: '5d ago', label: 'Added 1/3 + 1/6 with a common denominator', outcome: 'correct' },
        { at: '5d ago', label: 'Mastered Common denominators', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-grace',
      name: 'Grace L.',
      category: 'on_track',
      category_reason: 'Steady, unscaffolded progress across the unit.',
      alerts: [],
      struggle: {
        headline: 'Grace is moving steadily and rarely needs help.',
        detail:
          'Mastery is being earned across more than one representation, with few hints. Nothing ' +
          'to intervene on; a candidate for the next unit when she finishes.',
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
        { at: '15m ago', label: 'Added 2/5 + 1/3 unscaffolded', outcome: 'correct' },
        { at: '18m ago', label: 'Added 1/2 + 1/4 on the number line', outcome: 'correct' },
        { at: '1d ago', label: 'Mastered Common denominators', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-noah',
      name: 'Noah B.',
      category: 'on_track',
      category_reason: 'Three skills mastered; pacing well.',
      alerts: [],
      struggle: {
        headline: 'Noah has mastered the first three skills cleanly.',
        detail:
          'Consistent accuracy with low help-need. On pace to finish the unit this week. No ' +
          'action needed beyond keeping the next unit ready.',
        matched_misconception: null,
        helpneed_trend: 'steady',
        recent_error_rate: 0.16,
      },
      current_unit_title: 'Fractions & Decimals',
      current_lesson_title: 'Adding unlike fractions',
      percent_complete: 0.62,
      strengths: [
        { ...SKILL.numberline, probability: 0.93, status: 'mastered' },
        { ...SKILL.equivalence, probability: 0.88, status: 'mastered' },
        { ...SKILL.common, probability: 0.85, status: 'mastered' },
      ],
      weaknesses: [{ ...SKILL.add, probability: 0.58, status: 'in_progress' }],
      activity: [
        { at: '2h ago', label: 'Started Adding unlike fractions', outcome: 'neutral' },
        { at: '2h ago', label: 'Mastered Common denominators', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
  {
    student: {
      student_id: 'stu-emma',
      name: 'Emma S.',
      category: 'on_track',
      category_reason: 'Near the end of the unit; ready for what is next.',
      alerts: [],
      struggle: {
        headline: 'Emma is nearly through the unit and ready for the next one.',
        detail:
          'Four of five skills mastered across representations. A strong candidate to assign the ' +
          'next unit so she does not stall waiting.',
        matched_misconception: null,
        helpneed_trend: 'falling',
        recent_error_rate: 0.09,
      },
      current_unit_title: 'Fractions & Decimals',
      current_lesson_title: 'Subtracting unlike fractions',
      percent_complete: 0.86,
      strengths: [
        { ...SKILL.numberline, probability: 0.95, status: 'mastered' },
        { ...SKILL.equivalence, probability: 0.93, status: 'mastered' },
        { ...SKILL.common, probability: 0.9, status: 'mastered' },
        { ...SKILL.add, probability: 0.9, status: 'mastered' },
      ],
      weaknesses: [{ ...SKILL.subtract, probability: 0.71, status: 'in_progress' }],
      activity: [
        { at: '10m ago', label: 'Subtracted 3/4 − 1/3 unscaffolded', outcome: 'correct' },
        { at: '12m ago', label: 'Mastered Adding unlike fractions', outcome: 'correct' },
      ],
      assignable_units: ALL_UNITS,
      assigned_unit_id: null,
    },
  },
];

function rosterRow(s: TeacherStudentView): RosterStudentView {
  return {
    student_id: s.student_id,
    name: s.name,
    category: s.category,
    category_reason: s.category_reason,
    current_unit_title: s.current_unit_title,
    current_lesson_title: s.current_lesson_title,
    percent_complete: s.percent_complete,
    alerts: s.alerts,
  };
}

/** The demo roster (TODO TCH.B8 `GET /teacher/roster` shape). */
export const DEMO_ROSTER: TeacherRosterView = {
  teacher_name: 'Ms. Alvarez',
  class_name: 'Period 3 · Grade 6 Math',
  students: SEED.map((seed) => rosterRow(seed.student)),
};

/** One student's full drill-in, with any in-session assigned-unit override applied. */
export function demoStudent(studentId: string): TeacherStudentView | null {
  const seed = SEED.find((s) => s.student.student_id === studentId);
  if (seed === undefined) return null;
  const override = assignedOverrides.get(studentId);
  return override === undefined ? seed.student : { ...seed.student, assigned_unit_id: override };
}

/** Record an assign-next-unit in the demo (idempotent), returning the updated student. */
export function assignUnitInDemo(studentId: string, unitId: string): TeacherStudentView | null {
  const seed = SEED.find((s) => s.student.student_id === studentId);
  if (seed === undefined) return null;
  assignedOverrides.set(studentId, unitId);
  return { ...seed.student, assigned_unit_id: unitId };
}
