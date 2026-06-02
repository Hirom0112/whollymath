import { useEffect, useMemo, useState } from 'react';

import {
  fetchAggregateTrends,
  fetchReminders,
  fetchRoster,
  fetchTeacherStudent,
  type BucketTrends,
  type RosterStudentView,
  type StudentCategory,
  type TeacherReminder,
  type TeacherStudentView,
} from '../api/teacher';
import { AreaChart } from '../components/AreaChart';
import { Sparkline, type SparklineTone } from '../components/Sparkline';
import { TeacherShell } from '../components/TeacherShell';
import { AlertBadge, CategoryChip, ProgressBar } from '../components/TeacherSignals';
import './TeacherDashboard.css';

/**
 * The teacher roster — the teacher surface's home (TODO TCH.F2, the #1-priority lane).
 *
 * Students are grouped under RANKED category headers so the teacher's eye lands on who needs help
 * first: Struggling → Needs attention → On track (TODO TCH.B6 ranking). Each row carries the
 * student's alert badges, current unit/lesson, a trend sparkline, and course progress. A status
 * strip summarizes the class at a glance; the right rail spotlights the highest-priority student,
 * an aggregate skill-gap chart, and the teacher's reminders.
 *
 * Data source: `fetchRoster()` / `fetchAggregateTrends()` / `fetchReminders()` (TODO TCH.F1).
 * Until lane T1's /teacher endpoints land, those serve the seeded demo class (teacherDemo.ts); the
 * swap is a client flag, so this page does not change when the real API arrives.
 */

// Ranked display order — most-urgent first, the whole point of the dashboard.
const CATEGORY_ORDER: StudentCategory[] = ['struggling', 'needs_attention', 'on_track'];

const CATEGORY_BLURB: Record<StudentCategory, string> = {
  struggling: 'Has an urgent signal; look here first.',
  needs_attention: 'A warning worth a check-in.',
  on_track: 'Moving along; no action needed.',
};

const CATEGORY_LABEL: Record<StudentCategory, string> = {
  struggling: 'Struggling',
  needs_attention: 'Needs Attention',
  on_track: 'On Track',
};

// Sparkline tone per category — echoes the meaning layer (wrong/attention/correct).
const CATEGORY_TONE: Record<StudentCategory, SparklineTone> = {
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

// Format an ISO "YYYY-MM-DD" as "June 13, 2023". Parsed by parts (not new Date(iso)) so the
// rendered day never shifts by a timezone offset, and so it is deterministic in tests.
function formatAsOf(iso: string): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (m === null) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const day = Number(m[3]);
  if (month < 1 || month > 12) return null;
  return `${MONTHS[month - 1]} ${String(day)}, ${String(year)}`;
}

export function TeacherDashboard({
  onOpenStudent,
  onExit,
}: {
  onOpenStudent: (studentId: string) => void;
  onExit: () => void;
}): React.JSX.Element {
  const [students, setStudents] = useState<RosterStudentView[] | null>(null);
  const [header, setHeader] = useState<{ teacher: string; klass: string } | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [bucketTrends, setBucketTrends] = useState<BucketTrends | null>(null);
  const [aggregate, setAggregate] = useState<number[]>([]);
  const [reminders, setReminders] = useState<TeacherReminder[]>([]);
  const [primaryDetail, setPrimaryDetail] = useState<TeacherStudentView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let live = true;
    fetchRoster()
      .then((roster) => {
        if (!live) return;
        setStudents(roster.students ?? []);
        setHeader({ teacher: roster.teacher_name, klass: roster.class_name });
        setAsOf(roster.as_of ?? null);
        setBucketTrends(roster.bucket_trends ?? null);
      })
      .catch(() => {
        if (live) setError('We could not load your class. Please try again.');
      });
    return () => {
      live = false;
    };
  }, []);

  // Class-level rail data (aggregate skill-gap chart + reminders). Independent of the roster fetch.
  useEffect(() => {
    let live = true;
    fetchAggregateTrends()
      .then((a) => {
        if (live) setAggregate(a.skill_gap_series ?? []);
      })
      .catch(() => {
        /* the insights card simply renders empty if this fails */
      });
    fetchReminders()
      .then((r) => {
        if (live) setReminders(r);
      })
      .catch(() => {
        /* reminders are non-critical; leave the list empty on failure */
      });
    return () => {
      live = false;
    };
  }, []);

  const filtered = useMemo(() => {
    if (students === null) return null;
    const q = query.trim().toLowerCase();
    return q === '' ? students : students.filter((s) => s.name.toLowerCase().includes(q));
  }, [students, query]);

  const counts = useMemo(() => {
    const base: Record<StudentCategory, number> = {
      struggling: 0,
      needs_attention: 0,
      on_track: 0,
    };
    (students ?? []).forEach((s) => {
      base[s.category] += 1;
    });
    return base;
  }, [students]);

  // The class-level triage spotlight, computed from the WHOLE class (not the search-filtered view):
  // the single most-urgent student a teacher should check first (struggling, else needs-attention).
  // When nobody is struggling or needs attention, the class is all-clear and the rail celebrates it.
  const primary = useMemo(() => {
    const list = students ?? [];
    return (
      list.find((s) => s.category === 'struggling') ??
      list.find((s) => s.category === 'needs_attention') ??
      null
    );
  }, [students]);
  const primaryId = primary?.student_id ?? null;

  // Fetch the spotlight student's full detail for the Priority View (notes + remediation estimate),
  // which the lighter roster row does not carry.
  useEffect(() => {
    if (primaryId === null) {
      setPrimaryDetail(null);
      return;
    }
    let live = true;
    fetchTeacherStudent(primaryId)
      .then((d) => {
        if (live) setPrimaryDetail(d);
      })
      .catch(() => {
        if (live) setPrimaryDetail(null);
      });
    return () => {
      live = false;
    };
  }, [primaryId]);

  const allClear =
    students !== null &&
    students.length > 0 &&
    !students.some((s) => s.category === 'struggling' || s.category === 'needs_attention');

  const dateLabel = asOf !== null ? formatAsOf(asOf) : null;

  const toggleReminder = (id: string): void => {
    setReminders((rs) => rs.map((r) => (r.id === id ? { ...r, done: !r.done } : r)));
  };

  return (
    <TeacherShell
      teacherName={header?.teacher ?? null}
      klassName={header?.klass ?? null}
      onSignOut={onExit}
    >
      <div className="wm-teacher-content">
        <div className="wm-teacher-headline">
          <div>
            <h1 className="wm-teacher-title">{header?.klass ?? 'Your class'}</h1>
            {header !== null ? (
              <p className="wm-teacher-subtitle">
                {header.teacher}
                {students !== null ? ` · ${String(students.length)} students` : ''}
              </p>
            ) : null}
          </div>
          {dateLabel !== null ? <p className="wm-teacher-date">{dateLabel}</p> : null}
        </div>

        {students !== null ? (
          <div className="wm-teacher-statusstrip" aria-label="Class status overview">
            {CATEGORY_ORDER.map((cat) => (
              <StatusPill
                key={cat}
                category={cat}
                count={counts[cat]}
                trend={bucketTrends?.[cat] ?? []}
              />
            ))}
          </div>
        ) : null}

        <div className="wm-teacher-split">
          <div className="wm-teacher-list">
            <label className="wm-teacher-search">
              <span className="wm-teacher-search-ico" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false">
                  <circle
                    cx="11"
                    cy="11"
                    r="6.5"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.2"
                  />
                  <line
                    x1="16"
                    y1="16"
                    x2="21"
                    y2="21"
                    stroke="currentColor"
                    strokeWidth="2.2"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <input
                type="search"
                placeholder="Search students by name"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search students by name"
              />
            </label>

            {error !== null ? (
              <p className="wm-teacher-error" role="alert">
                {error}
              </p>
            ) : null}

            {filtered === null && error === null ? (
              <p className="wm-teacher-loading">Loading your class…</p>
            ) : null}

            {filtered !== null
              ? CATEGORY_ORDER.map((cat) => {
                  const inCat = filtered.filter((s) => s.category === cat);
                  if (inCat.length === 0) return null;
                  return (
                    <section key={cat} className="wm-teacher-section" aria-label={cat}>
                      <div className="wm-teacher-section-head">
                        <CategoryChip category={cat} />
                        <span className="wm-teacher-section-count">{inCat.length}</span>
                        <span className="wm-teacher-section-blurb">{CATEGORY_BLURB[cat]}</span>
                      </div>
                      <ul className="wm-teacher-roster">
                        {inCat.map((s) => (
                          <StudentRow key={s.student_id} student={s} onOpen={onOpenStudent} />
                        ))}
                      </ul>
                    </section>
                  );
                })
              : null}

            {filtered !== null && filtered.length === 0 ? (
              <p className="wm-teacher-empty">
                {query.trim() !== ''
                  ? `No students match “${query}”.`
                  : 'No students on your roster yet. Your class will appear here once it’s set up.'}
              </p>
            ) : null}
          </div>

          <aside className="wm-teacher-rail" aria-label="Class triage and insights">
            {allClear ? (
              <AllClearHero klassName={header?.klass ?? null} />
            ) : primary !== null ? (
              <TriageHero student={primary} detail={primaryDetail} onOpen={onOpenStudent} />
            ) : null}
            <StudentInsights data={aggregate} />
            <RemindersCard reminders={reminders} onToggle={toggleReminder} />
          </aside>
        </div>
      </div>
    </TeacherShell>
  );
}

/** A class-status pill: colored dot + label + a trend sparkline (the top status strip). */
function StatusPill({
  category,
  count,
  trend,
}: {
  category: StudentCategory;
  count: number;
  trend: number[];
}): React.JSX.Element {
  return (
    <div className={`wm-teacher-statuspill wm-teacher-statuspill--${category}`}>
      <span className="wm-teacher-statuspill-head">
        <span
          className={`wm-teacher-statuspill-dot wm-teacher-statuspill-dot--${category}`}
          aria-hidden="true"
        />
        <span className="wm-teacher-statuspill-label">{CATEGORY_LABEL[category]}</span>
        <span className="wm-teacher-statuspill-count">{count}</span>
      </span>
      <Sparkline
        data={trend}
        tone={CATEGORY_TONE[category]}
        width={120}
        height={26}
        ariaLabel={`${CATEGORY_LABEL[category]} trend`}
      />
    </div>
  );
}

/** The class-level triage spotlight: who to check first, their notes/remediation, and one click in. */
function TriageHero({
  student,
  detail,
  onOpen,
}: {
  student: RosterStudentView;
  detail: TeacherStudentView | null;
  onOpen: (studentId: string) => void;
}): React.JSX.Element {
  const unit = student.current_unit_title ?? null;
  const notes = detail?.notes ?? null;
  const remediation = detail?.remediation_estimate_minutes ?? null;
  return (
    <div className="wm-teacher-triage">
      <p className="wm-teacher-triage-eyebrow">Highest-priority triage</p>
      <h2 className="wm-teacher-triage-head">
        <span className="wm-teacher-triage-ico" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="currentColor" focusable="false">
            <path
              d="M12 3 L22 20 H2 Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinejoin="round"
            />
            <line
              x1="12"
              y1="9"
              x2="12"
              y2="14"
              stroke="currentColor"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
            <circle cx="12" cy="17.3" r="1.3" />
          </svg>
        </span>
        Check in with {student.name}
      </h2>
      <p className="wm-teacher-triage-detail">{student.category_reason}</p>
      {unit !== null ? <p className="wm-teacher-triage-where">Working in {unit}</p> : null}
      {notes !== null ? (
        <p className="wm-teacher-triage-notes">
          <span className="wm-teacher-triage-notes-label">Notes:</span> {notes}
        </p>
      ) : null}
      {remediation !== null ? (
        <p className="wm-teacher-triage-remed">Remediation time: {String(remediation)} minutes</p>
      ) : null}
      <button
        type="button"
        className="wm-teacher-triage-btn"
        onClick={() => onOpen(student.student_id)}
      >
        Open profile
      </button>
    </div>
  );
}

/** Aggregate class skill-gap trend (the "Student Insights" rail card). */
function StudentInsights({ data }: { data: number[] }): React.JSX.Element {
  return (
    <div className="wm-teacher-insights">
      <h2 className="wm-teacher-insights-head">Student Insights</h2>
      <p className="wm-teacher-insights-sub">
        An aggregate view of skill gaps across the whole class.
      </p>
      <AreaChart data={data} tone="amber" height={92} ariaLabel="Class skill-gap trend over time" />
    </div>
  );
}

/** The teacher's reminders / to-dos (the "reminders" rail card). Toggling is local in demo mode. */
function RemindersCard({
  reminders,
  onToggle,
}: {
  reminders: TeacherReminder[];
  onToggle: (id: string) => void;
}): React.JSX.Element {
  return (
    <div className="wm-teacher-reminders">
      <h2 className="wm-teacher-reminders-head">Reminders</h2>
      {reminders.length === 0 ? (
        <p className="wm-teacher-reminders-empty">No reminders yet.</p>
      ) : (
        <ul className="wm-teacher-reminders-list">
          {reminders.map((r) => (
            <li key={r.id}>
              <label className="wm-teacher-reminder">
                <input type="checkbox" checked={r.done} onChange={() => onToggle(r.id)} />
                <span
                  className={`wm-teacher-reminder-text${
                    r.done ? ' wm-teacher-reminder-text--done' : ''
                  }`}
                >
                  {r.text}
                </span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Shown when nobody is struggling or needs attention: a calm confirmation, not an empty rail. */
function AllClearHero({ klassName }: { klassName: string | null }): React.JSX.Element {
  return (
    <div className="wm-teacher-allclear">
      <span className="wm-teacher-allclear-ring" aria-hidden="true">
        <svg viewBox="0 0 24 24" focusable="false">
          <polyline
            points="4,13 10,19 20,5"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <h2 className="wm-teacher-allclear-head">Whole class on track</h2>
      <p className="wm-teacher-allclear-detail">
        No urgent or warning signals {klassName !== null ? `in ${klassName} ` : ''}right now.
        Nothing needs triage.
      </p>
    </div>
  );
}

function StudentRow({
  student,
  onOpen,
}: {
  student: RosterStudentView;
  onOpen: (studentId: string) => void;
}): React.JSX.Element {
  // The generated wire types make these optional (Pydantic defaults), so normalize to a value
  // or null and treat both null and undefined as "absent".
  const lesson = student.current_lesson_title ?? null;
  const unit = student.current_unit_title ?? null;
  const alerts = student.alerts ?? [];
  const trend = student.trend ?? [];
  // The "URGENT ACTION" corner tag is the struggling-bucket promise: these are the rows a teacher
  // must act on now. Pairing it with the bucket keeps color from being the only cue.
  const urgent = student.category === 'struggling';
  return (
    <li>
      <button
        type="button"
        className={`wm-teacher-row${urgent ? ' wm-teacher-row--urgent' : ''}`}
        onClick={() => onOpen(student.student_id)}
      >
        {urgent ? <span className="wm-teacher-row-urgenttag">Urgent action</span> : null}
        <span className="wm-teacher-row-main">
          <span className="wm-teacher-row-name">{student.name}</span>
          <span className="wm-teacher-row-reason">{student.category_reason}</span>
          <span className="wm-teacher-row-where">
            {lesson !== null ? (
              <>
                <span className="wm-teacher-row-lesson">{lesson}</span>
                {unit !== null ? <span className="wm-teacher-row-unit"> · {unit}</span> : null}
              </>
            ) : (
              <span className="wm-teacher-row-unit">Not started</span>
            )}
          </span>
        </span>
        <span className="wm-teacher-row-signals">
          {alerts.length > 0 ? (
            <span className="wm-teacher-row-alerts">
              {alerts.map((a) => (
                <AlertBadge key={a.kind} alert={a} />
              ))}
            </span>
          ) : null}
          {trend.length > 0 ? (
            <Sparkline
              data={trend}
              tone={CATEGORY_TONE[student.category]}
              width={88}
              height={22}
              ariaLabel={`${student.name} accuracy trend`}
            />
          ) : null}
          <ProgressBar value={student.percent_complete} tone={student.category} />
        </span>
        <span className="wm-teacher-row-chev" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <polyline
              points="9,5 16,12 9,19"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </button>
    </li>
  );
}
