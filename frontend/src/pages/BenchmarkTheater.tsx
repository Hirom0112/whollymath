import { useEffect, useState } from 'react';

import {
  fetchBenchmarkPersonas,
  fetchBenchmarkTranscript,
  type AdaptiveTurnView,
  type BenchmarkPersonaSummaryView,
  type BenchmarkTranscriptView,
  type ChatTurnView,
  type StaticTurnView,
} from '../api';
import './BenchmarkTheater.css';

/**
 * The "benchmark theater" — a teaching view of the Slice 5.3 three-arm comparison
 * (PROJECT.md §3.11), reached at `?theater=1`. The Slice 5.3 dashboard (`?eval=1`) shows the
 * verdicts; this view shows the step-by-step they are read off of: pick one adversarial
 * persona, watch the SAME problems run through all three tutors turn by turn, and see WHY our
 * adaptive tutor refuses false mastery, where a chat tutor self-certifies, and that the static
 * walkthrough checks nothing. "Both" layout (decision): a side-by-side overview plus a
 * click-through into each arm's own full page. Not part of the student flow.
 */

type Mode = 'overview' | 'adaptive' | 'chat' | 'static';

const ARM_BLURB = {
  adaptive: 'Our tutor. Checks every answer with SymPy, then applies the mastery rules.',
  chat: 'A plain AI chatbot. Grades itself in conversation — no rules, no checker.',
  static: 'A fixed worked-example page. Shows the solution; checks and tracks nothing.',
} as const;

const DEFAULT_PERSONA = 'procedure_priya';

export function BenchmarkTheater(): React.JSX.Element {
  const [personas, setPersonas] = useState<BenchmarkPersonaSummaryView[] | null>(null);
  const [personaId, setPersonaId] = useState<string>(DEFAULT_PERSONA);
  const [data, setData] = useState<BenchmarkTranscriptView | null>(null);
  const [mode, setMode] = useState<Mode>('overview');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchBenchmarkPersonas()
      .then(setPersonas)
      .catch(() => {
        setError('Could not load the personas. Is the API running on :8000?');
      });
  }, []);

  useEffect(() => {
    setData(null);
    fetchBenchmarkTranscript(personaId)
      .then(setData)
      .catch(() => {
        setError('Could not load that run. Is the API running on :8000?');
      });
  }, [personaId]);

  if (error !== null) {
    return (
      <main className="wm-theater">
        <p className="wm-theater-error" role="alert">
          {error}
        </p>
      </main>
    );
  }

  return (
    <main className="wm-theater">
      <header className="wm-theater-head">
        <p className="wm-theater-kicker">
          Benchmark theater · the three-arm comparison, step by step
        </p>
        <h1 className="wm-theater-title">Same student, same problems, three tutors</h1>
        <p className="wm-theater-lead">
          Pick one of our five “fake students” — each is built to hide a specific gap. Watch the
          same problems run through all three tutors. The whole test: can a tutor be fooled into
          saying “mastered” when the student is faking it?
        </p>

        <PersonaSwitcher
          personas={personas}
          selected={personaId}
          onSelect={(id) => {
            setPersonaId(id);
            setMode('overview');
          }}
        />

        {data !== null && (
          <p className="wm-theater-attacks">
            <strong>{data.persona_name}</strong> attacks: {data.attacks} &nbsp;·&nbsp; skill under
            test: <code>{data.kc}</code>
          </p>
        )}

        <nav className="wm-theater-tabs" aria-label="View">
          {(['overview', 'adaptive', 'chat', 'static'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={`wm-theater-tab ${mode === m ? 'wm-theater-tab--active' : ''}`}
              onClick={() => setMode(m)}
            >
              {m === 'overview' ? 'Side-by-side' : labelForArm(m)}
            </button>
          ))}
        </nav>
      </header>

      {data === null ? (
        <p className="wm-theater-loading">Loading the run…</p>
      ) : mode === 'overview' ? (
        <Overview data={data} onOpen={(m) => setMode(m)} />
      ) : (
        <ArmDetail data={data} arm={mode} onBack={() => setMode('overview')} />
      )}
    </main>
  );
}

function labelForArm(arm: 'adaptive' | 'chat' | 'static'): string {
  if (arm === 'adaptive') return 'Our tutor';
  if (arm === 'chat') return 'AI chatbot';
  return 'Static page';
}

function PersonaSwitcher({
  personas,
  selected,
  onSelect,
}: {
  personas: BenchmarkPersonaSummaryView[] | null;
  selected: string;
  onSelect: (id: string) => void;
}): React.JSX.Element {
  return (
    <div className="wm-theater-personas" role="tablist" aria-label="Choose a fake student">
      {(personas ?? []).map((p) => (
        <button
          key={p.persona_id}
          type="button"
          role="tab"
          aria-selected={p.persona_id === selected}
          className={`wm-theater-persona ${
            p.persona_id === selected ? 'wm-theater-persona--active' : ''
          }`}
          onClick={() => onSelect(p.persona_id)}
        >
          {p.persona_name}
        </button>
      ))}
    </div>
  );
}

/* ───────────────────────── side-by-side overview ───────────────────────── */

function Overview({
  data,
  onOpen,
}: {
  data: BenchmarkTranscriptView;
  onOpen: (arm: 'adaptive' | 'chat' | 'static') => void;
}): React.JSX.Element {
  return (
    <div className="wm-theater-cols">
      <ArmColumn arm="adaptive" data={data} onOpen={() => onOpen('adaptive')}>
        {data.adaptive_turns.map((t, i) => (
          <AdaptiveCard key={i} turn={t} index={i + 1} />
        ))}
        <TransferProbe data={data} />
      </ArmColumn>

      <ArmColumn arm="chat" data={data} onOpen={() => onOpen('chat')}>
        <p className="wm-theater-illus">⚠ {data.chat_illustrative_note}</p>
        {data.chat_turns.map((t, i) => (
          <ChatCard key={i} turn={t} index={i + 1} />
        ))}
      </ArmColumn>

      <ArmColumn arm="static" data={data} onOpen={() => onOpen('static')}>
        {data.static_turns.map((t, i) => (
          <StaticCard key={i} turn={t} index={i + 1} compact />
        ))}
      </ArmColumn>
    </div>
  );
}

function ArmColumn({
  arm,
  data,
  onOpen,
  children,
}: {
  arm: 'adaptive' | 'chat' | 'static';
  data: BenchmarkTranscriptView;
  onOpen: () => void;
  children: React.ReactNode;
}): React.JSX.Element {
  const verdict =
    arm === 'adaptive'
      ? { label: data.adaptive_verdict, tone: data.adaptive_tone }
      : arm === 'chat'
        ? { label: data.chat_verdict, tone: data.chat_tone }
        : { label: data.static_verdict, tone: data.static_tone };

  return (
    <section className={`wm-theater-col wm-theater-col--${arm}`}>
      <header className="wm-theater-col-head">
        <h2 className="wm-theater-col-title">{labelForArm(arm)}</h2>
        <p className="wm-theater-col-blurb">{ARM_BLURB[arm]}</p>
      </header>
      <div className="wm-theater-turns">{children}</div>
      <Verdict arm={arm} data={data} label={verdict.label} tone={verdict.tone} />
      <button type="button" className="wm-theater-open" onClick={onOpen}>
        See the full {labelForArm(arm).toLowerCase()} →
      </button>
    </section>
  );
}

/* ───────────────────────── per-arm detail page ───────────────────────── */

function ArmDetail({
  data,
  arm,
  onBack,
}: {
  data: BenchmarkTranscriptView;
  arm: 'adaptive' | 'chat' | 'static';
  onBack: () => void;
}): React.JSX.Element {
  return (
    <section className={`wm-theater-detail wm-theater-col--${arm}`}>
      <button type="button" className="wm-theater-back" onClick={onBack}>
        ← Back to side-by-side
      </button>
      <h2 className="wm-theater-detail-title">{labelForArm(arm)}</h2>
      <p className="wm-theater-detail-blurb">{ARM_BLURB[arm]}</p>

      {arm === 'chat' && <p className="wm-theater-illus">⚠ {data.chat_illustrative_note}</p>}

      <div className="wm-theater-detail-turns">
        {arm === 'adaptive' &&
          data.adaptive_turns.map((t, i) => (
            <AdaptiveCard key={i} turn={t} index={i + 1} detailed />
          ))}
        {arm === 'chat' &&
          data.chat_turns.map((t, i) => <ChatCard key={i} turn={t} index={i + 1} />)}
        {arm === 'static' &&
          data.static_turns.map((t, i) => <StaticCard key={i} turn={t} index={i + 1} />)}
      </div>

      {arm === 'adaptive' && <TransferProbe data={data} />}

      <Verdict
        arm={arm}
        data={data}
        verbose
        label={
          arm === 'adaptive'
            ? data.adaptive_verdict
            : arm === 'chat'
              ? data.chat_verdict
              : data.static_verdict
        }
        tone={
          arm === 'adaptive'
            ? data.adaptive_tone
            : arm === 'chat'
              ? data.chat_tone
              : data.static_tone
        }
      />
    </section>
  );
}

/* ───────────────────────── turn cards ───────────────────────── */

function AdaptiveCard({
  turn,
  index,
  detailed = false,
}: {
  turn: AdaptiveTurnView;
  index: number;
  detailed?: boolean;
}): React.JSX.Element {
  return (
    <article className="wm-theater-card">
      <div className="wm-theater-card-top">
        <span className="wm-theater-step">#{index}</span>
        <span className="wm-theater-fmt">{turn.format_label}</span>
      </div>
      <p className="wm-theater-q">{turn.problem_statement}</p>
      <p className="wm-theater-ans">
        answer: <strong>{turn.student_answer}</strong>
      </p>
      <p className={`wm-theater-check wm-theater-check--${turn.correct ? 'ok' : 'no'}`}>
        {turn.correct ? '✓' : '✗'} {turn.result_label}{' '}
        <span className="wm-theater-byline">· SymPy</span>
      </p>
      {detailed && <p className="wm-theater-feedback">“{turn.feedback}”</p>}
      <div className="wm-theater-flags">
        <span className="wm-theater-flag">{turn.latency_label}</span>
        {turn.hint_used && (
          <span className="wm-theater-flag wm-theater-flag--warn">used a hint</span>
        )}
        {turn.below_engagement_floor && (
          <span className="wm-theater-flag wm-theater-flag--warn">too fast — doesn’t count</span>
        )}
        {detailed && <span className="wm-theater-flag">{turn.state_label}</span>}
      </div>
    </article>
  );
}

function ChatCard({ turn, index }: { turn: ChatTurnView; index: number }): React.JSX.Element {
  return (
    <article className="wm-theater-card">
      <div className="wm-theater-card-top">
        <span className="wm-theater-step">#{index}</span>
      </div>
      <p className="wm-theater-q">{turn.problem_statement}</p>
      <div className="wm-theater-bubble wm-theater-bubble--student">{turn.student_answer}</div>
      <div className="wm-theater-bubble wm-theater-bubble--tutor">{turn.tutor_reply}</div>
    </article>
  );
}

function StaticCard({
  turn,
  index,
  compact = false,
}: {
  turn: StaticTurnView;
  index: number;
  compact?: boolean;
}): React.JSX.Element {
  return (
    <article className="wm-theater-card">
      <div className="wm-theater-card-top">
        <span className="wm-theater-step">#{index}</span>
      </div>
      <p className="wm-theater-q">{turn.problem_statement}</p>
      {compact ? (
        <p className="wm-theater-walk-note">📄 worked-example walkthrough shown</p>
      ) : (
        <pre className="wm-theater-walk">{turn.walkthrough}</pre>
      )}
      <p className="wm-theater-ans">
        student wrote: <strong>{turn.student_answer}</strong>{' '}
        <span className="wm-theater-byline">· not checked</span>
      </p>
    </article>
  );
}

/* ───────────────────────── verdict banner ───────────────────────── */

function Verdict({
  arm,
  data,
  label,
  tone,
  verbose = false,
}: {
  arm: 'adaptive' | 'chat' | 'static';
  data: BenchmarkTranscriptView;
  label: string;
  tone: string;
  verbose?: boolean;
}): React.JSX.Element {
  const why =
    arm === 'adaptive' ? data.adaptive_why : arm === 'chat' ? data.chat_why : data.static_note;
  return (
    <div className={`wm-theater-verdict wm-theater-verdict--${tone}`}>
      <p className="wm-theater-verdict-label">{label}</p>
      {/* The plain-language, read-aloud explanation — the demo's talking point. */}
      <p className="wm-theater-why">{why}</p>
      {arm === 'chat' && (
        <p className="wm-theater-verdict-note">
          chat tutor said: <strong>{data.chat_self_assessment}</strong>
          {data.chat_live ? ' (real recorded run)' : ''}
        </p>
      )}
      {/* The exact rule strings, kept for the detail page only (small print). */}
      {verbose && arm === 'adaptive' && (data.adaptive_reasons ?? []).length > 0 && (
        <ul className="wm-theater-reasons">
          {(data.adaptive_reasons ?? []).map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ───────────────────────── transfer probe (the real test) ───────────────────────── */

function TransferProbe({ data }: { data: BenchmarkTranscriptView }): React.JSX.Element | null {
  const steps = data.adaptive_probe_steps ?? [];
  if (!data.adaptive_probe_ran || steps.length === 0) return null;
  return (
    <div className="wm-theater-probe">
      <p className="wm-theater-probe-head">
        ✦ All practice answers correct — but correct isn’t the same as understanding. So we run the{' '}
        <strong>transfer probe</strong>:
      </p>
      {steps.map((s, i) => (
        <article
          key={i}
          className={`wm-theater-probe-item wm-theater-probe-item--${s.passed ? 'ok' : 'no'}`}
        >
          <p className="wm-theater-probe-type">
            {s.item_type === 'error_finding'
              ? 'Can they catch a mistake?'
              : 'Same skill, new format'}
          </p>
          <p className="wm-theater-q">{s.prompt}</p>
          <p className={`wm-theater-check wm-theater-check--${s.passed ? 'ok' : 'no'}`}>
            {s.passed ? '✓ passed' : '✗ failed'}
          </p>
          <p className="wm-theater-probe-detail">{s.detail}</p>
        </article>
      ))}
    </div>
  );
}
