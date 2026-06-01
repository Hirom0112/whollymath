import { useEffect, useMemo, useState } from 'react';

import { fetchRoster, type RosterStudentView, type StudentCategory } from '../api/teacher';
import { TeacherShell } from '../components/TeacherShell';
import { AlertBadge, CategoryChip, ProgressBar } from '../components/TeacherSignals';
import './TeacherDashboard.css';

/**
 * The teacher roster — the teacher surface's home (TODO TCH.F2, the #1-priority lane).
 *
 * Students are grouped under RANKED category headers so the teacher's eye lands on who needs help
 * first: Struggling → Needs attention → On track (TODO TCH.B6 ranking). Each row carries the
 * student's alert badges, current unit/lesson, and course progress. A search box filters by name.
 * Clicking a student opens the drill-in (`onOpenStudent`).
 *
 * Data source: `fetchRoster()` (TODO TCH.F1). Until lane T1's /teacher endpoints land, that
 * serves the seeded demo class (teacherDemo.ts); the swap is a client flag, so this page does not
 * change when the real API arrives.
 */

// Ranked display order — most-urgent first, the whole point of the dashboard.
const CATEGORY_ORDER: StudentCategory[] = ['struggling', 'needs_attention', 'on_track'];

const CATEGORY_BLURB: Record<StudentCategory, string> = {
  struggling: 'Has an urgent signal; look here first.',
  needs_attention: 'A warning worth a check-in.',
  on_track: 'Moving along; no action needed.',
};

export function TeacherDashboard({
  onOpenStudent,
  onExit,
}: {
  onOpenStudent: (studentId: string) => void;
  onExit: () => void;
}): React.JSX.Element {
  const [students, setStudents] = useState<RosterStudentView[] | null>(null);
  const [header, setHeader] = useState<{ teacher: string; klass: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    let live = true;
    fetchRoster()
      .then((roster) => {
        if (!live) return;
        setStudents(roster.students ?? []);
        setHeader({ teacher: roster.teacher_name, klass: roster.class_name });
      })
      .catch(() => {
        if (live) setError('We could not load your class. Please try again.');
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
  const allClear =
    students !== null &&
    students.length > 0 &&
    !students.some((s) => s.category === 'struggling' || s.category === 'needs_attention');

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
          <div className="wm-teacher-summary" aria-hidden={students === null}>
            {CATEGORY_ORDER.map((cat) => (
              <span key={cat} className="wm-teacher-summary-item">
                <CategoryChip category={cat} size="sm" />
                <span className="wm-teacher-summary-count">{counts[cat]}</span>
              </span>
            ))}
          </div>
        </div>

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

          <aside className="wm-teacher-rail" aria-label="Class triage">
            {allClear ? (
              <AllClearHero klassName={header?.klass ?? null} />
            ) : primary !== null ? (
              <TriageHero student={primary} onOpen={onOpenStudent} />
            ) : null}
          </aside>
        </div>
      </div>
    </TeacherShell>
  );
}

/** The class-level triage spotlight: who to check first, and one click into their profile. */
function TriageHero({
  student,
  onOpen,
}: {
  student: RosterStudentView;
  onOpen: (studentId: string) => void;
}): React.JSX.Element {
  const unit = student.current_unit_title ?? null;
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
  return (
    <li>
      <button type="button" className="wm-teacher-row" onClick={() => onOpen(student.student_id)}>
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
