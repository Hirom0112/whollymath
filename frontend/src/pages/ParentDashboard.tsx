import { useEffect, useMemo, useState } from 'react';

import {
  fetchHousehold,
  fetchParentNotes,
  type ChildSummary,
  type Household,
  type ParentNote,
} from '../api/parent';
import { AreaChart } from '../components/AreaChart';
import { ParentShell } from '../components/ParentShell';
import { Sparkline, type SparklineTone } from '../components/Sparkline';
import { CategoryChip, ProgressBar } from '../components/TeacherSignals';
import './ParentDashboard.css';

/**
 * The household dashboard — the parent surface's home (mirrors TeacherDashboard's layout, reframed
 * for a parent watching several children). Instead of a ranked roster it shows one card per child
 * (status pill + accuracy sparkline + progress), a friendly cross-kid summary, an "Add a child"
 * card, and a right rail with a "Family this week" insight chart and a parent "Notes" card.
 *
 * Data: `fetchHousehold()` / `fetchParentNotes()` — demo-backed (parentDemo.ts) until a real backend
 * lands; the swap is a client flag, so this page does not change when the real API arrives.
 */

// Sparkline tone per category — echoes the meaning layer (wrong/attention/correct), same as teacher.
const CATEGORY_TONE: Record<ChildSummary['category'], SparklineTone> = {
  struggling: 'red',
  needs_attention: 'amber',
  on_track: 'green',
};

const MONTHS = [
  'January',
  'February',
  'March',
  'April',
  'May',
  'June',
  'July',
  'August',
  'September',
  'October',
  'November',
  'December',
];

// Format an ISO "YYYY-MM-DD" as "June 13, 2023". Parsed by parts (not new Date(iso)) so the rendered
// day never shifts by a timezone offset and is deterministic — same convention as TeacherDashboard.
function formatAsOf(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (m === null) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12) return null;
  return `${MONTHS[month - 1]} ${String(day)}, ${String(year)}`;
}

// A fixed "as of" date for the header, matching the teacher demo's deterministic timestamp (no
// Date.now — the demo renders the same date every time and stays honest to screenshot).
const DEMO_AS_OF = '2026-06-01';

export function ParentDashboard({
  onOpenChild,
  onAddChild,
  onExit,
}: {
  onOpenChild: (childId: string) => void;
  onAddChild: () => void;
  onExit: () => void;
}): React.JSX.Element {
  const [household, setHousehold] = useState<Household | null>(null);
  const [notes, setNotes] = useState<ParentNote[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchHousehold()
      .then((h) => {
        if (live) setHousehold(h);
      })
      .catch(() => {
        if (live) setError('We could not load your family. Please try again.');
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    let live = true;
    fetchParentNotes()
      .then((n) => {
        if (live) setNotes(n);
      })
      .catch(() => {
        /* notes are non-critical; leave the list empty on failure */
      });
    return () => {
      live = false;
    };
  }, []);

  const children = household?.children ?? null;

  // Combined family activity for the "Family this week" rail chart: a point-wise average of each
  // child's recent-accuracy trend, so the area chart reflects the whole household at a glance.
  const familySeries = useMemo(() => combineTrends(children ?? []), [children]);

  const practicedCount = (children ?? []).filter((c) => c.practiced_today).length;
  const firstName = (household?.parent_name ?? '').trim().split(/\s+/)[0] || 'there';
  const dateLabel = formatAsOf(DEMO_AS_OF);

  const toggleNote = (id: string): void => {
    setNotes((ns) => ns.map((n) => (n.id === id ? { ...n, done: !n.done } : n)));
  };

  return (
    <ParentShell
      parentName={household?.parent_name ?? null}
      householdLabel={household?.household_label ?? null}
      onSignOut={onExit}
    >
      <div className="wm-parent-content">
        <div className="wm-parent-headline">
          <div>
            <h1 className="wm-parent-title">Hi, {firstName}</h1>
            {household !== null ? (
              <p className="wm-parent-subtitle">
                {household.household_label}
                {children !== null
                  ? ` · ${String(children.length)} ${children.length === 1 ? 'child' : 'children'}`
                  : ''}
              </p>
            ) : null}
          </div>
          {dateLabel !== null ? <p className="wm-parent-date">{dateLabel}</p> : null}
        </div>

        {children !== null && children.length > 0 ? (
          <p className="wm-parent-summary">
            {practicedCount} of your {children.length} {children.length === 1 ? 'child' : 'kids'}{' '}
            practiced today.
          </p>
        ) : null}

        {error !== null ? (
          <p className="wm-parent-error" role="alert">
            {error}
          </p>
        ) : null}

        {children === null && error === null ? (
          <p className="wm-parent-loading">Loading your family…</p>
        ) : null}

        <div className="wm-parent-split">
          <div className="wm-parent-list">
            {children !== null ? (
              <div className="wm-parent-grid">
                {children.map((child) => (
                  <ChildCard key={child.child_id} child={child} onOpen={onOpenChild} />
                ))}
                <button type="button" className="wm-parent-add" onClick={onAddChild}>
                  <span className="wm-parent-add-plus" aria-hidden="true">
                    <svg viewBox="0 0 24 24" focusable="false">
                      <line
                        x1="12"
                        y1="5"
                        x2="12"
                        y2="19"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                      />
                      <line
                        x1="5"
                        y1="12"
                        x2="19"
                        y2="12"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                      />
                    </svg>
                  </span>
                  <span className="wm-parent-add-label">Add a child</span>
                  <span className="wm-parent-add-sub">Create a login for another kid</span>
                </button>
              </div>
            ) : null}
          </div>

          <aside className="wm-parent-rail" aria-label="Family insights">
            <FamilyThisWeek data={familySeries} />
            <NotesCard notes={notes} onToggle={toggleNote} />
          </aside>
        </div>
      </div>
    </ParentShell>
  );
}

/** Point-wise average of every child's trend so the family chart reflects the whole household. */
function combineTrends(children: ChildSummary[]): number[] {
  const series = children.map((c) => c.trend).filter((t) => t.length > 0);
  if (series.length === 0) return [];
  const len = Math.min(...series.map((t) => t.length));
  const out: number[] = [];
  for (let i = 0; i < len; i += 1) {
    const sum = series.reduce((acc, t) => acc + t[i], 0);
    out.push(Math.round(sum / series.length));
  }
  return out;
}

/** One child's at-a-glance card: name, grade, current unit, status pill, accuracy trend, progress. */
function ChildCard({
  child,
  onOpen,
}: {
  child: ChildSummary;
  onOpen: (childId: string) => void;
}): React.JSX.Element {
  const lesson = child.current_lesson_title;
  const unit = child.current_unit_title;
  return (
    <button
      type="button"
      className={`wm-parent-card wm-parent-card--${child.category}`}
      onClick={() => onOpen(child.child_id)}
    >
      <span className="wm-parent-card-top">
        <span className="wm-parent-card-id">
          <span className="wm-parent-card-name">{child.name}</span>
          <span className="wm-parent-card-grade">Grade {child.grade}</span>
        </span>
        <CategoryChip category={child.category} size="sm" />
      </span>

      <span className="wm-parent-card-status">{child.status_line}</span>

      <span className="wm-parent-card-where">
        {lesson !== null ? (
          <>
            <span className="wm-parent-card-lesson">{lesson}</span>
            {unit !== null ? <span className="wm-parent-card-unit"> · {unit}</span> : null}
          </>
        ) : (
          <span className="wm-parent-card-unit">Not started yet</span>
        )}
      </span>

      {child.trend.length > 0 ? (
        <Sparkline
          data={child.trend}
          tone={CATEGORY_TONE[child.category]}
          width={220}
          height={34}
          ariaLabel={`${child.name} accuracy trend`}
        />
      ) : null}

      <ProgressBar value={child.percent_complete} tone={child.category} />

      <span className="wm-parent-card-cta">
        View {child.name}&rsquo;s progress
        <span aria-hidden="true"> →</span>
      </span>
    </button>
  );
}

/** Combined household activity this week (the "Family this week" rail card). */
function FamilyThisWeek({ data }: { data: number[] }): React.JSX.Element {
  return (
    <div className="wm-parent-insights">
      <h2 className="wm-parent-insights-head">Family this week</h2>
      <p className="wm-parent-insights-sub">
        How your kids are doing across their practice, all together.
      </p>
      <AreaChart data={data} tone="blue" height={92} ariaLabel="Family accuracy this week" />
    </div>
  );
}

/** The parent's "Notes" / things-to-ask-about card (the rail's second card). Toggling is local. */
function NotesCard({
  notes,
  onToggle,
}: {
  notes: ParentNote[];
  onToggle: (id: string) => void;
}): React.JSX.Element {
  return (
    <div className="wm-parent-notes">
      <h2 className="wm-parent-notes-head">Notes</h2>
      {notes.length === 0 ? (
        <p className="wm-parent-notes-empty">No notes yet.</p>
      ) : (
        <ul className="wm-parent-notes-list">
          {notes.map((n) => (
            <li key={n.id}>
              <label className="wm-parent-note">
                <input type="checkbox" checked={n.done} onChange={() => onToggle(n.id)} />
                <span
                  className={`wm-parent-note-text${n.done ? ' wm-parent-note-text--done' : ''}`}
                >
                  {n.text}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
