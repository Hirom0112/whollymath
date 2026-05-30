import { useEffect, useMemo, useState } from 'react';

import { fetchRoster, type RosterStudentView, type StudentCategory } from '../api/teacher';
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

  return (
    <div className="wm-teacher">
      <header className="wm-teacher-topbar">
        <div className="wm-teacher-brand">
          <span className="wm-teacher-brand-mark" aria-hidden="true" />
          <span className="wm-teacher-brand-name">WhollyMath</span>
          <span className="wm-teacher-brand-role">Teacher</span>
        </div>
        <button type="button" className="wm-teacher-exit" onClick={onExit}>
          Sign out
        </button>
      </header>

      <main className="wm-teacher-main">
        <div className="wm-teacher-headline">
          <div>
            <h1 className="wm-teacher-title">{header?.klass ?? 'Your class'}</h1>
            {header !== null ? <p className="wm-teacher-subtitle">{header.teacher}</p> : null}
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

        <label className="wm-teacher-search">
          <span className="wm-teacher-search-ico" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false">
              <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2.2" />
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
      </main>
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
