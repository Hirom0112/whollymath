import { useRef, useState } from 'react';

import {
  submitTurn,
  type InterventionView,
  type MasterySnapshot,
  type ProblemView,
  type StartSessionResponse,
  type SurfaceState,
  type TurnResponse,
} from '../api';
import { Mascot } from '../components/Mascot';
import {
  fractionToAnswer,
  NumberLine,
  SymbolicEditor,
  YesNo,
  yesNoToAnswer,
  type FractionValue,
} from '../workspace';
import './Tutor.css';

const EMPTY_FRACTION: FractionValue = { numerator: '', denominator: '' };

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
 * Register: calm / editorial. The warmer "world" register lives in the onboarding
 * (landing + cold start); once the learner is working a problem the surface settles
 * (PRODUCT.md onboarding register arc).
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

// Kid-friendly label per surface state, so the surface names the mode it is in
// (refuse-rule 4 spirit: never present a state without a label). These must NOT claim
// a widget that isn't shown — the input is chosen by the surface_format (see ``isNumberLine``
// / ``isYesNo``), so the symbolic labels describe the FRAME of mind, not a manipulative. A
// number-line or yes/no problem overrides these with a fixed, literal instruction.
const STATE_LABEL: Record<SurfaceState, string> = {
  S1_symbolic_focus: 'Work it with the numbers',
  S2_number_line_primary: 'Picture how big it is',
  S3_fraction_bars_primary: 'Picture the pieces',
  S4_worked_example: "Let's take it step by step",
  S5_transfer_probe: 'Try this one a new way',
};

// Kid-friendly names for the per-KC progress strip (the mastery snapshot keys on KC id).
const KC_LABEL: Record<string, string> = {
  KC_equivalence: 'Equivalent fractions',
  KC_common_denominator: 'Common denominator',
  KC_addition_unlike: 'Adding fractions',
  KC_subtraction_unlike: 'Subtracting fractions',
  KC_number_line_placement: 'Number line',
};

// τ — the mastery probability threshold (PROJECT.md §3.4 / mastery_model). The progress
// bar fills to full as the BKT probability approaches τ; mastery needs τ AND the §3.4 rules.
const MASTERY_THRESHOLD = 0.85;

// The backend returns the snapshot for the KC answered THIS turn only. Merge by KC id, keeping
// the latest reading per KC, so the progress strip shows every skill the session has touched
// (and the goal KC's mastered state persists across interleaved companion turns).
function mergeMastery(prev: MasterySnapshot[], next: MasterySnapshot[]): MasterySnapshot[] {
  const byKc = new Map(prev.map((m) => [m.kc_id, m]));
  for (const m of next) byKc.set(m.kc_id, m);
  return [...byKc.values()];
}

export function Tutor({ session }: { session: StartSessionResponse }): React.JSX.Element {
  const sessionId = session.session_id;
  const [problem, setProblem] = useState<ProblemView>(session.problem);
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(session.surface_state);
  const [fraction, setFraction] = useState<FractionValue>(() => initialFraction(session.problem));
  const [tick, setTick] = useState<number | null>(null);
  // The yes/no selection for relational-judgment problems (true=yes, false=no, null=unset).
  const [yesNo, setYesNo] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>('answering');
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [hintUsed, setHintUsed] = useState(false);
  // A proactively-offered nudge for THIS problem (Slice 4.5): the previous turn's
  // sustained HelpNeed signal tripped the §3.7 gate, so help is shown unasked, inline in
  // the workspace (§3.8 refuse-rule 6). null unless the proactive arm fired (default OFF).
  const [intervention, setIntervention] = useState<InterventionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The per-KC mastery snapshot the backend returns each turn (BKT probability + declared
  // mastery). Merged across turns so the progress strip shows every skill touched.
  const [mastery, setMastery] = useState<MasterySnapshot[]>([]);

  // The KC this session is working toward (the cold-start route's KC). When the model
  // DECLARES mastery on it, the journey's goal is reached.
  const goalKc = session.problem.kc;
  const goalMastered = mastery.find((m) => m.kc_id === goalKc)?.mastered ?? false;
  // The S5 transfer probe: the surface state is S5 while the learner answers the probe items
  // (a different representation + an error-finding check). We frame it as a final check so
  // the learner knows this confirms mastery — it isn't just another practice problem.
  const isProbe = surfaceState === 'S5_transfer_probe';

  // When the current problem was first shown — the elapsed time is the turn's
  // latency_ms, which feeds the engagement floor (§6) and HelpNeed (§8) server-side.
  const startedAt = useRef<number>(Date.now());

  // The answer widget is chosen by what the problem asks (surface_format / answer_kind), so it
  // always matches the question — and so the SAME KC can be answered in more than one
  // representation (addition symbolically AND on the line), which mastery rule 2 needs. A
  // number-line surface (placement OR an arithmetic result in 0–1) → the draggable marker;
  // a yes/no judgment → the buttons; otherwise the fraction editor.
  const isNumberLine = problem.surface_format === 'number_line' && problem.tick_segments != null;
  // A relational-judgment problem ("Is X the same amount as Y?") is answered yes/no, not
  // by typing a fraction — the server tells us via answer_kind so the surface matches the
  // question (the coherence fix: a yes/no question must not land on a fraction input).
  const isYesNo = problem.answer_kind === 'yes_no';

  let submittedAnswer: string;
  let canSubmit: boolean;
  if (isYesNo) {
    submittedAnswer = yesNoToAnswer(yesNo);
    canSubmit = yesNo !== null;
  } else if (isNumberLine) {
    submittedAnswer = tick === null ? '' : `${String(tick)}/${String(problem.tick_segments)}`;
    canSubmit = tick !== null;
  } else {
    submittedAnswer = fractionToAnswer(fraction);
    canSubmit = submittedAnswer !== '';
  }

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (phase !== 'answering' || !canSubmit) return;
    setPhase('submitting');
    setError(null);
    setIntervention(null); // the offer pertained to this attempt; it is now spent
    try {
      const response = await submitTurn({
        session_id: sessionId,
        problem_id: problem.problem_id,
        action: 'submit_answer',
        submitted_answer: submittedAnswer,
        surface_state: surfaceState,
        latency_ms: Date.now() - startedAt.current,
        hint_used: hintUsed,
      });
      setResult(response);
      setMastery((prev) => mergeMastery(prev, response.mastery ?? []));
      setPhase('feedback');
    } catch {
      setError('Something went wrong sending your answer. Give it another try.');
      setPhase('answering');
    }
  }

  async function handleHint(): Promise<void> {
    if (phase !== 'answering') return;
    setError(null);
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

  function handleNext(): void {
    const next = result?.next_problem;
    if (!next) return;
    setProblem(next);
    setSurfaceState(result.next_surface_state);
    setFraction(initialFraction(next));
    setTick(null);
    setYesNo(null);
    setHint(null);
    setHintUsed(false);
    // Carry any proactive offer the just-finished turn produced onto this next problem.
    setIntervention(result.intervention ?? null);
    setResult(null);
    setPhase('answering');
    startedAt.current = Date.now();
  }

  // The mascot speaks ONLY on help moments (Slice 5.5.2 scope): a requested hint or
  // an unasked proactive nudge — never routine right/wrong feedback. Both are voiced
  // by one character so the surface keeps a single voice; the gesture they came from
  // (offered vs. requested) is preserved visually on the bubble. A requested hint is
  // the most specific, freshest help, so it takes precedence over a carried-over offer.
  const helpSpeech =
    hint !== null
      ? { text: hint, kind: 'hint' as const }
      : intervention !== null
        ? { text: intervention.text, kind: 'offer' as const }
        : null;

  return (
    <main className="wm-tutor">
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
        {isProbe && phase !== 'feedback' ? (
          <p className="wm-tutor-probe-badge">Final check — prove you&rsquo;ve really got it</p>
        ) : null}
        <p className="wm-tutor-mode">
          {isYesNo
            ? problem.yes_no_relation === 'greater'
              ? 'Bigger, or not?'
              : 'Same amount, or not?'
            : isNumberLine
              ? 'Place it on the number line'
              : STATE_LABEL[surfaceState]}
        </p>
        <h1 className="wm-tutor-statement">{problem.statement}</h1>

        {helpSpeech !== null ? (
          <div className="wm-tutor-mascot-row">
            <div className="wm-tutor-mascot" aria-hidden="true">
              <Mascot />
            </div>
            <p className={`wm-tutor-speech wm-tutor-speech--${helpSpeech.kind}`} role="note">
              {helpSpeech.text}
            </p>
          </div>
        ) : null}

        {phase !== 'feedback' ? (
          <form className="wm-tutor-form" onSubmit={handleSubmit}>
            {isYesNo ? (
              <YesNo
                value={yesNo}
                onChange={setYesNo}
                disabled={phase === 'submitting'}
                prompt="Your answer"
              />
            ) : isNumberLine && problem.tick_segments != null ? (
              <NumberLine
                segments={problem.tick_segments}
                value={tick}
                onChange={setTick}
                disabled={phase === 'submitting'}
              />
            ) : (
              <SymbolicEditor
                value={fraction}
                onChange={setFraction}
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
          </form>
        ) : (
          <div className="wm-tutor-feedback-block">
            {goalMastered ? (
              <div className="wm-tutor-mastered" role="status">
                <p className="wm-tutor-mastered-title">
                  You mastered {KC_LABEL[goalKc] ?? 'this skill'}!
                </p>
                <p className="wm-tutor-mastered-sub">
                  You got it right across different forms — that&rsquo;s real understanding, not one
                  lucky answer.
                </p>
              </div>
            ) : (
              <p
                className={`wm-tutor-feedback wm-tutor-feedback--${result?.correct ? 'right' : 'wrong'}`}
              >
                {result?.feedback}
              </p>
            )}
            {result?.next_problem ? (
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
      </section>
    </main>
  );
}
