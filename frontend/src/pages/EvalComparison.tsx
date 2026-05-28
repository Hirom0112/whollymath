import { useEffect, useState } from 'react';

import { fetchThreeArmComparison, type ThreeArmComparisonView } from '../api';
import './EvalComparison.css';

/**
 * The Slice 5.3 three-arm comparison, on screen (PROJECT.md §3.11). A researcher/demo view
 * reached at `?eval=1` — not part of the student flow. Shows the five adversarial personas,
 * the problems each was given, and how each of the three tutors (Adaptive / Chat / Static)
 * verdicts their mastery. The adaptive + static columns are real and deterministic; the chat
 * column is the pre-registered prediction until the cost-gated live LLM run (server says so).
 */
export function EvalComparison(): React.JSX.Element {
  const [data, setData] = useState<ThreeArmComparisonView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchThreeArmComparison()
      .then(setData)
      .catch(() => {
        setError('Could not load the comparison. Is the API running on :8000?');
      });
  }, []);

  if (error !== null) {
    return (
      <main className="wm-eval">
        <p className="wm-eval-error" role="alert">
          {error}
        </p>
      </main>
    );
  }

  if (data === null) {
    return (
      <main className="wm-eval">
        <p className="wm-eval-loading">Loading the comparison…</p>
      </main>
    );
  }

  const metrics = data.metrics ?? [];

  return (
    <main className="wm-eval">
      <header className="wm-eval-head">
        <p className="wm-eval-kicker">Slice 5.3 · three-arm comparison</p>
        <h1 className="wm-eval-title">What we&rsquo;re testing</h1>
        <p className="wm-eval-headline">{data.headline}</p>
        <div className="wm-eval-tally">
          <span className="wm-eval-chip wm-eval-chip--good">
            Adaptive false positives: {data.adaptive_false_positives}/{data.total}
          </span>
          <span
            className={`wm-eval-chip ${data.chat_live ? 'wm-eval-chip--bad' : 'wm-eval-chip--pending'}`}
          >
            {data.chat_live
              ? `Chat false positives: ${String(data.chat_false_positives ?? 0)}/${String(data.total)} (live)`
              : 'Chat: predicted (live run pending)'}
          </span>
          <span className="wm-eval-chip wm-eval-chip--neutral">
            Static: N/A (certifies nothing)
          </span>
        </div>
      </header>

      <div className="wm-eval-grid" role="table" aria-label="Three-arm comparison">
        <div className="wm-eval-row wm-eval-row--header" role="row">
          <div className="wm-eval-cell wm-eval-cell--persona" role="columnheader">
            Adversarial learner
          </div>
          <div className="wm-eval-cell" role="columnheader">
            Adaptive (ours)
          </div>
          <div className="wm-eval-cell" role="columnheader">
            Chat baseline
          </div>
          <div className="wm-eval-cell" role="columnheader">
            Static baseline
          </div>
        </div>

        {data.rows.map((row) => (
          <div className="wm-eval-row" role="row" key={row.persona_name}>
            <div className="wm-eval-cell wm-eval-cell--persona" role="cell">
              <p className="wm-eval-name">{row.persona_name}</p>
              <p className="wm-eval-attacks">attacks: {row.attacks}</p>
              <ul className="wm-eval-problems">
                {row.problems.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ul>
            </div>
            {[row.adaptive, row.chat, row.static].map((arm) => (
              <div className="wm-eval-cell" role="cell" key={arm.arm}>
                <span className={`wm-eval-verdict wm-eval-verdict--${arm.tone}`}>
                  {arm.verdict}
                </span>
                <p className="wm-eval-detail">{arm.detail}</p>
              </div>
            ))}
          </div>
        ))}
      </div>

      {metrics.length > 0 && (
        <section className="wm-eval-metrics">
          <h2 className="wm-eval-section-title">The other five pre-registered metrics</h2>
          <p className="wm-eval-section-note">
            Each is attacked by one persona. The adaptive verdict is the rule that actually blocked
            that learner in the run; the chat verdict is the live self-assessment (or, for the
            learners it denied, the honest note that it lacks the mechanism); the static walkthrough
            has no mastery construct at all.
          </p>
          <div className="wm-eval-grid" role="table" aria-label="Per-metric comparison">
            <div className="wm-eval-row wm-eval-row--header" role="row">
              <div className="wm-eval-cell wm-eval-cell--persona" role="columnheader">
                Metric (adversary)
              </div>
              <div className="wm-eval-cell" role="columnheader">
                Adaptive (ours)
              </div>
              <div className="wm-eval-cell" role="columnheader">
                Chat baseline
              </div>
              <div className="wm-eval-cell" role="columnheader">
                Static baseline
              </div>
            </div>

            {metrics.map((metric) => (
              <div className="wm-eval-row" role="row" key={metric.key}>
                <div className="wm-eval-cell wm-eval-cell--persona" role="cell">
                  <p className="wm-eval-name">{metric.name}</p>
                  <p className="wm-eval-attacks">{metric.adversary}</p>
                </div>
                {[metric.adaptive, metric.chat, metric.static].map((arm) => (
                  <div className="wm-eval-cell" role="cell" key={arm.arm}>
                    <span className={`wm-eval-verdict wm-eval-verdict--${arm.tone}`}>
                      {arm.status}
                    </span>
                    <p className="wm-eval-detail">{arm.detail}</p>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
