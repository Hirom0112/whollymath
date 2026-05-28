import { useRef, useState } from 'react';

import {
  submitTurn,
  type ProblemView,
  type StartSessionResponse,
  type SurfaceState,
  type TurnResponse,
} from '../api';
import './Tutor.css';

/**
 * The in-tutor problem surface (Turn 1 onward). Drives the real reactive loop
 * (ARCHITECTURE.md §10): present the current problem, take an answer, POST /turn,
 * show the labeled verdict, then advance to the next problem the loop chose.
 *
 * Register: calm / editorial. The warmer "world" register lives in the onboarding
 * (landing + cold start); once the learner is working a problem the surface settles
 * (PRODUCT.md onboarding register arc).
 *
 * Scope: this renders the problem STATEMENT and a plain answer field — enough for a
 * real end-to-end journey. The S1–S5 SVG manipulatives (SymbolicEditor / NumberLine /
 * FractionBar — Slice 2.5) are the next frontend build; until they land, the learner
 * types the fraction (e.g. "7/12"), which the domain SymPy verifier parses server-side.
 */

type Phase = 'answering' | 'submitting' | 'feedback';

// Kid-friendly label per surface state, so the surface names the mode it is in
// (refuse-rule 4 spirit: never present a state without a label). The SVG workspace
// for each (Slice 2.5) replaces the plain input later.
const STATE_LABEL: Record<SurfaceState, string> = {
  S1_symbolic_focus: 'Work it with the numbers',
  S2_number_line_primary: 'Use the number line',
  S3_fraction_bars_primary: 'Use the fraction bars',
  S4_worked_example: "Let's walk through one together",
  S5_transfer_probe: 'Try this one a new way',
};

export function Tutor({ session }: { session: StartSessionResponse }): React.JSX.Element {
  const sessionId = session.session_id;
  const [problem, setProblem] = useState<ProblemView>(session.problem);
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(session.surface_state);
  const [answer, setAnswer] = useState('');
  const [phase, setPhase] = useState<Phase>('answering');
  const [result, setResult] = useState<TurnResponse | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [hintUsed, setHintUsed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the current problem was first shown — the elapsed time is the turn's
  // latency_ms, which feeds the engagement floor (§6) and HelpNeed (§8) server-side.
  const startedAt = useRef<number>(Date.now());

  async function handleSubmit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (phase !== 'answering' || answer.trim() === '') return;
    setPhase('submitting');
    setError(null);
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
    setAnswer('');
    setHint(null);
    setHintUsed(false);
    setResult(null);
    setPhase('answering');
    startedAt.current = Date.now();
  }

  return (
    <main className="wm-tutor">
      <section className="wm-tutor-card" aria-live="polite">
        <p className="wm-tutor-mode">{STATE_LABEL[surfaceState]}</p>
        <h1 className="wm-tutor-statement">{problem.statement}</h1>

        {phase !== 'feedback' ? (
          <form className="wm-tutor-form" onSubmit={handleSubmit}>
            <label className="wm-tutor-label" htmlFor="wm-answer">
              Your answer
            </label>
            <input
              id="wm-answer"
              className="wm-tutor-input"
              type="text"
              inputMode="text"
              autoComplete="off"
              placeholder="e.g. 7/12"
              value={answer}
              onChange={(event) => {
                setAnswer(event.target.value);
              }}
              disabled={phase === 'submitting'}
            />
            <div className="wm-tutor-actions">
              <button
                type="submit"
                className="wm-tutor-submit"
                disabled={phase === 'submitting' || answer.trim() === ''}
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
