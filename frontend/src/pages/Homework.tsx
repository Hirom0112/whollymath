import { QRCodeSVG } from 'qrcode.react';
import { useEffect, useState } from 'react';

import {
  hwAssign,
  hwConfirm,
  hwStatus,
  type HwAssignResponse,
  type HwDraftItemView,
  type HwGradeResultView,
  type KnowledgeComponentId,
} from '../api';
import './Homework.css';

/**
 * The DESKTOP homework flow (PROJECT.md §3.4 two-star model). At lesson end the learner already
 * earned ★ (the transfer probe). Homework earns the optional ★★:
 *   assign → show a QR (phone opens the capture page) + the question checklist, poll for the upload
 *   → read-back ("I read this as 1/4 — right?") → confirm → SymPy grades → ★★ (≥0.8) or redo-loop.
 * The probe already gated mastery, so this never blocks progression — a miss just recommends
 * redoing the lesson with a fresh set (RD.0.9).
 */
type Phase = 'assigning' | 'waiting' | 'review' | 'graded' | 'error';

const POLL_MS = 2000;

// Lesson number + name per skill (the teaching/spine order). Homework starts at Lesson 2 — Lesson 1
// (number-line placement) has no scannable homework (its answer is a mark on a line, not writing).
const LESSON: Record<string, { n: number; name: string }> = {
  KC_number_line_placement: { n: 1, name: 'Place a fraction on a number line' },
  KC_equivalence: { n: 2, name: 'Equivalent fractions' },
  KC_common_denominator: { n: 3, name: 'Common denominator' },
  KC_addition_unlike: { n: 4, name: 'Adding fractions' },
  KC_subtraction_unlike: { n: 5, name: 'Subtracting fractions' },
};

function lessonLabel(kc: string): string {
  const l = LESSON[kc];
  return l ? `Lesson ${String(l.n)} · ${l.name}` : kc;
}

export function Homework({
  kc,
  sessionId,
  onBack,
}: {
  kc: KnowledgeComponentId;
  sessionId?: string | null;
  onBack: () => void;
}): React.JSX.Element {
  const [phase, setPhase] = useState<Phase>('assigning');
  const [assign, setAssign] = useState<HwAssignResponse | null>(null);
  const [draft, setDraft] = useState<HwDraftItemView[]>([]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<HwGradeResultView | null>(null);

  // Assign the set once on mount.
  useEffect(() => {
    let live = true;
    hwAssign(kc, sessionId)
      .then((a) => {
        if (live) {
          setAssign(a);
          setPhase('waiting');
        }
      })
      .catch(() => {
        if (live) setPhase('error');
      });
    return () => {
      live = false;
    };
  }, [kc, sessionId]);

  // While waiting, poll until the phone's pages arrive and a draft is transcribed.
  useEffect(() => {
    if (phase !== 'waiting' || assign === null) return;
    const id = setInterval(() => {
      void hwStatus(assign.token)
        .then((s) => {
          const items = s.draft ?? [];
          if (s.state === 'ready_for_review' && items.length > 0) {
            setDraft(items);
            setAnswers(Object.fromEntries(items.map((d) => [d.index, d.read_as ?? ''])));
            setPhase('review');
          }
        })
        .catch(() => {
          /* transient poll error — keep trying */
        });
    }, POLL_MS);
    return () => clearInterval(id);
  }, [phase, assign]);

  async function confirm(): Promise<void> {
    if (assign === null) return;
    const payload = draft.map((d) => {
      const value = (answers[d.index] ?? '').trim();
      return { index: d.index, answer: value === '' ? null : value };
    });
    try {
      const status = await hwConfirm(assign.token, payload);
      if (status.result !== null && status.result !== undefined) {
        setResult(status.result);
        setPhase('graded');
      }
    } catch {
      setPhase('error');
    }
  }

  if (phase === 'error') {
    return (
      <Shell onBack={onBack}>
        <p className="wm-hw-error" role="alert">
          Something went wrong with the homework. Is the API running on :8000?
        </p>
      </Shell>
    );
  }

  if (phase === 'assigning' || assign === null) {
    return (
      <Shell onBack={onBack}>
        <p className="wm-hw-loading">Putting your homework together…</p>
      </Shell>
    );
  }

  if (phase === 'waiting') {
    const uploadUrl = `${window.location.origin}/hw/upload?token=${encodeURIComponent(assign.token)}`;
    return (
      <Shell onBack={onBack}>
        <p className="wm-hw-lesson">{lessonLabel(assign.target_kc)}</p>
        <div className="wm-hw-scan">
          <div className="wm-hw-qr-card">
            <h2 className="wm-hw-qr-title">Scan to send your pages</h2>
            <p className="wm-hw-qr-sub">Open your phone camera and point it here.</p>
            <div className="wm-hw-qr">
              <QRCodeSVG value={uploadUrl} size={196} />
            </div>
            <p className="wm-hw-qr-url">{uploadUrl}</p>
            {uploadUrl.includes('localhost') && (
              <p className="wm-hw-qr-hint">
                ⚠ Your phone can’t reach “localhost”. Open this page at your computer’s network
                address (e.g. http://10.10.1.130:5173) so the QR works.
              </p>
            )}
            <p className="wm-hw-qr-wait">Waiting for your photo…</p>
            <p className="wm-hw-qr-privacy">No faces, just math.</p>
          </div>
          <div className="wm-hw-checklist">
            <h3 className="wm-hw-checklist-title">On your sheet:</h3>
            <ol className="wm-hw-checklist-list">
              {assign.questions.map((q) => (
                <li key={q.index} className={q.is_target ? 'wm-hw-q--target' : 'wm-hw-q--review'}>
                  {q.statement}
                  {!q.is_target && <span className="wm-hw-q-tag"> review</span>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </Shell>
    );
  }

  if (phase === 'review') {
    return (
      <Shell onBack={onBack}>
        <div className="wm-hw-review">
          <h2 className="wm-hw-review-title">Let’s check what I read</h2>
          <p className="wm-hw-review-sub">
            Make sure I got your answers right. Fix any I misread, then we’ll go through them.
          </p>
          {draft.map((d) => (
            <div key={d.index} className="wm-hw-review-row">
              <p className="wm-hw-review-q">{d.statement}</p>
              <label className="wm-hw-review-field">
                <span>I read this as</span>
                <input
                  type="text"
                  value={answers[d.index] ?? ''}
                  placeholder="(couldn’t read)"
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [d.index]: e.currentTarget.value }))
                  }
                />
              </label>
            </div>
          ))}
          <button type="button" className="wm-hw-primary" onClick={() => void confirm()}>
            Looks right — check my work →
          </button>
        </div>
      </Shell>
    );
  }

  // phase === 'graded'
  return (
    <Shell onBack={onBack}>
      <Result result={result} onBack={onBack} />
    </Shell>
  );
}

function Result({
  result,
  onBack,
}: {
  result: HwGradeResultView | null;
  onBack: () => void;
}): React.JSX.Element {
  if (result === null) {
    return <p className="wm-hw-loading">Grading…</p>;
  }
  const pct = Math.round(result.target_score * 100);
  return (
    <div className="wm-hw-result">
      {result.passed ? (
        <>
          <p className="wm-hw-stars">★★</p>
          <h2 className="wm-hw-result-title">You earned your second star!</h2>
          <p className="wm-hw-result-sub">
            {result.target_correct}/{result.target_total} on the new skill ({pct}%). You’ve got it —
            and now you’ve shown it on your own, on paper.
          </p>
        </>
      ) : (
        <>
          <p className="wm-hw-stars wm-hw-stars--one">★</p>
          <h2 className="wm-hw-result-title">Let’s give this one another go</h2>
          <p className="wm-hw-result-sub">
            {result.target_correct}/{result.target_total} on the new skill ({pct}%). No worries —
            let’s run through the lesson again and try a fresh sheet. (You keep your first star.)
          </p>
        </>
      )}

      <ul className="wm-hw-result-list">
        {result.results.map((q) => (
          <li
            key={q.index}
            className={`wm-hw-result-item wm-hw-result-item--${q.correct ? 'ok' : 'no'}`}
          >
            <span className="wm-hw-result-mark">{q.correct ? '✓' : '✗'}</span>
            <span className="wm-hw-result-q">{q.statement}</span>
            <span className="wm-hw-result-ans">
              {q.submitted ?? '—'}
              {!q.is_target && <span className="wm-hw-q-tag"> review</span>}
            </span>
          </li>
        ))}
      </ul>

      <button type="button" className="wm-hw-primary" onClick={onBack}>
        ← Back to my path
      </button>
    </div>
  );
}

function Shell({
  children,
  onBack,
}: {
  children: React.ReactNode;
  onBack: () => void;
}): React.JSX.Element {
  return (
    <main className="wm-hw">
      <header className="wm-hw-head">
        <button type="button" className="wm-hw-back" onClick={onBack}>
          ← My path
        </button>
        <h1 className="wm-hw-title">Homework</h1>
      </header>
      {children}
    </main>
  );
}
