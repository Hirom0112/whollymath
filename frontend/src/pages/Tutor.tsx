import { useRef, useState } from 'react';

import {
  submitTurn,
  type ProblemView,
  type StartSessionResponse,
  type SurfaceState,
  type TurnResponse,
} from '../api';
import { fractionToAnswer, NumberLine, SymbolicEditor, type FractionValue } from '../workspace';
import './Tutor.css';

const EMPTY_FRACTION: FractionValue = { numerator: '', denominator: '' };

/**
 * The in-tutor problem surface (Turn 1 onward). Drives the real reactive loop
 * (ARCHITECTURE.md §10): present the current problem, take an answer, POST /turn,
 * show the labeled verdict, then advance to the next problem the loop chose.
 *
 * Register: calm / editorial. The warmer "world" register lives in the onboarding
 * (landing + cold start); once the learner is working a problem the surface settles
 * (PRODUCT.md onboarding register arc).
 *
 * Input selection: the answer widget is chosen by the ANSWER's nature (the KC), not
 * the surface state, so the rendered widget can always express the answer the served
 * problem wants. Number-line placement → the draggable NumberLine marker; everything
 * else → the SymbolicEditor, which expresses any "a/b" (including improper sums > 1).
 * The S2/S3 manipulatives-as-workspace morph (a number line / fraction bars that
 * VISUALIZE an arithmetic problem while the answer is entered separately) is the
 * fuller Slice 2.5 follow-up; FractionBar exists for it but is not a live answer input
 * until that "manipulate + enter answer" design lands.
 */

type Phase = 'answering' | 'submitting' | 'feedback';

// Kid-friendly label per surface state, so the surface names the mode it is in
// (refuse-rule 4 spirit: never present a state without a label). These must NOT claim
// a widget that isn't shown — the input is chosen by the KC (see ``isPlacement``), so
// the non-placement labels describe the FRAME of mind, not a manipulative. A
// number-line placement problem overrides these with a fixed, literal instruction.
const STATE_LABEL: Record<SurfaceState, string> = {
  S1_symbolic_focus: 'Work it with the numbers',
  S2_number_line_primary: 'Picture how big it is',
  S3_fraction_bars_primary: 'Picture the pieces',
  S4_worked_example: "Let's take it step by step",
  S5_transfer_probe: 'Try this one a new way',
};

export function Tutor({ session }: { session: StartSessionResponse }): React.JSX.Element {
  const sessionId = session.session_id;
  const [problem, setProblem] = useState<ProblemView>(session.problem);
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(session.surface_state);
  const [fraction, setFraction] = useState<FractionValue>(EMPTY_FRACTION);
  const [tick, setTick] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>('answering');
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [hintUsed, setHintUsed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the current problem was first shown — the elapsed time is the turn's
  // latency_ms, which feeds the engagement floor (§6) and HelpNeed (§8) server-side.
  const startedAt = useRef<number>(Date.now());

  // The input widget is chosen by the answer's nature (the KC), so it can always
  // express the served answer. Number-line placement → the draggable marker (its
  // answer is k/tick_segments); everything else → the fraction editor, which expresses
  // any "a/b" (including an addition sum > 1 the marker/bars couldn't show). Both
  // produce the "n/d" answer string the domain verifier parses server-side.
  const isPlacement = problem.kc === 'KC_number_line_placement' && problem.tick_segments != null;

  let submittedAnswer: string;
  let canSubmit: boolean;
  if (isPlacement) {
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
    setFraction(EMPTY_FRACTION);
    setTick(null);
    setHint(null);
    setHintUsed(false);
    setResult(null);
    setPhase('answering');
    startedAt.current = Date.now();
  }

  return (
    <main className="wm-tutor">
      <section className="wm-tutor-card" aria-live="polite">
        <p className="wm-tutor-mode">
          {isPlacement ? 'Place it on the number line' : STATE_LABEL[surfaceState]}
        </p>
        <h1 className="wm-tutor-statement">{problem.statement}</h1>

        {phase !== 'feedback' ? (
          <form className="wm-tutor-form" onSubmit={handleSubmit}>
            {isPlacement && problem.tick_segments != null ? (
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
            <p
              className={`wm-tutor-feedback wm-tutor-feedback--${result?.correct ? 'right' : 'wrong'}`}
            >
              {result?.feedback}
            </p>
            {result?.next_problem ? (
              <button type="button" className="wm-tutor-next" onClick={handleNext}>
                Next problem
              </button>
            ) : null}
          </div>
        )}

        {hint !== null ? (
          <p className="wm-tutor-hint" role="note">
            {hint}
          </p>
        ) : null}

        {error !== null ? (
          <p className="wm-tutor-error" role="alert">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}
