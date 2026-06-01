import { useEffect, useState } from 'react';

import {
  assignUnit,
  fetchTeacherStudent,
  type ActivityEventView,
  type AssignableUnitView,
  type HelpNeedTrend,
  type KcMasteryView,
  type TeacherStudentView as StudentDetail,
} from '../api/teacher';
import { TeacherShell } from '../components/TeacherShell';
import { AlertBadge, CategoryChip, ProgressBar } from '../components/TeacherSignals';
import './TeacherStudentView.css';

/**
 * One student's drill-in for the teacher (TODO TCH.F3). Read-only except for the assign action.
 * Section order is deliberate (the spec): (1) ALERTS banner at the very top with aria-live so a
 * screen reader announces it, (2) what + WHY struggling — the named misconception we compute and
 * used to throw away (TEACHER_NEEDS.md headline), (3) current unit/lesson, (4) strengths /
 * weaknesses by BKT, (5) recent-activity timeline, (6) Assign next unit.
 *
 * Data: `fetchTeacherStudent` / `assignUnit` (TODO TCH.F1), demo-backed until lane T1's endpoints
 * land — the page does not change at the swap.
 */

const TREND_LABEL: Record<HelpNeedTrend, string> = {
  rising: 'Help-need rising',
  steady: 'Help-need steady',
  falling: 'Help-need falling',
};

export function TeacherStudentView({
  studentId,
  onBack,
  onExit,
  teacherName = null,
  klassName = null,
}: {
  studentId: string;
  onBack: () => void;
  // Optional sign-out, surfaced in the shell side-nav when the container can end the session.
  onExit?: () => void;
  // Optional shell header context (the class this student belongs to), passed by the container.
  teacherName?: string | null;
  klassName?: string | null;
}): React.JSX.Element {
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assigning, setAssigning] = useState(false);

  useEffect(() => {
    let live = true;
    setStudent(null);
    setError(null);
    fetchTeacherStudent(studentId)
      .then((s) => {
        if (live) setStudent(s);
      })
      .catch(() => {
        if (live) setError('We could not load this student. They may not be on your roster.');
      });
    return () => {
      live = false;
    };
  }, [studentId]);

  async function handleAssign(unitId: string): Promise<void> {
    setAssigning(true);
    try {
      const updated = await assignUnit(studentId, unitId);
      setStudent(updated);
    } catch {
      setError('We could not assign that unit. Please try again.');
    } finally {
      setAssigning(false);
    }
  }

  return (
    <TeacherShell
      teacherName={teacherName}
      klassName={klassName}
      onHome={onBack}
      onSignOut={onExit}
    >
      <div className="wm-tstudent-content">
        <button type="button" className="wm-tstudent-back" onClick={onBack}>
          <span aria-hidden="true" className="wm-tstudent-back-ico">
            <svg viewBox="0 0 24 24" focusable="false">
              <polyline
                points="14,5 7,12 14,19"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          Back to class
        </button>

        {error !== null ? (
          <p className="wm-tstudent-error" role="alert">
            {error}
          </p>
        ) : null}

        {student === null && error === null ? (
          <p className="wm-tstudent-loading">Loading…</p>
        ) : null}

        {student !== null ? (
          <div className="wm-tstudent-main">
            <div className="wm-tstudent-identity">
              <h1 className="wm-tstudent-name">{student.name}</h1>
              <CategoryChip category={student.category} />
            </div>
            <p className="wm-tstudent-reason">{student.category_reason}</p>

            {/* (1) ALERTS — first, and announced. aria-live so a screen reader reads new alerts. */}
            <section className="wm-tstudent-alerts" aria-label="Alerts" aria-live="polite">
              {(student.alerts ?? []).length > 0 ? (
                (student.alerts ?? []).map((a) => (
                  <AlertBadge key={a.kind} alert={a} variant="full" />
                ))
              ) : (
                <p className="wm-tstudent-noalerts">No alerts. This student is moving along.</p>
              )}
            </section>

            {/* (2) What + WHY struggling — the diagnostic teachers asked for. */}
            <WhySection student={student} />

            {/* (3) Current unit/lesson + course progress. */}
            <section className="wm-tstudent-card" aria-label="Current work">
              <h2 className="wm-tstudent-h2">Working on</h2>
              <div className="wm-tstudent-current">
                <div>
                  <p className="wm-tstudent-current-lesson">
                    {student.current_lesson_title ?? 'Not started yet'}
                  </p>
                  {student.current_unit_title != null ? (
                    <p className="wm-tstudent-current-unit">{student.current_unit_title}</p>
                  ) : null}
                </div>
                <ProgressBar value={student.percent_complete} tone={student.category} />
              </div>
            </section>

            {/* (4) Strengths / weaknesses by BKT. */}
            <section className="wm-tstudent-card" aria-label="Strengths and weaknesses">
              <h2 className="wm-tstudent-h2">Skills</h2>
              <div className="wm-tstudent-skills">
                <SkillColumn title="Strengths" tone="strong" skills={student.strengths ?? []} />
                <SkillColumn title="Needs work" tone="weak" skills={student.weaknesses ?? []} />
              </div>
            </section>

            {/* (5) Recent-activity timeline. */}
            <section className="wm-tstudent-card" aria-label="Recent activity">
              <h2 className="wm-tstudent-h2">Recent activity</h2>
              <Timeline events={student.activity ?? []} />
            </section>

            {/* (6) Assign next unit. */}
            <AssignSection
              units={student.assignable_units ?? []}
              assignedUnitId={student.assigned_unit_id ?? null}
              busy={assigning}
              onAssign={(unitId) => void handleAssign(unitId)}
            />
          </div>
        ) : null}
      </div>
    </TeacherShell>
  );
}

function WhySection({ student }: { student: StudentDetail }): React.JSX.Element {
  const { struggle } = student;
  return (
    <section
      className="wm-tstudent-card wm-tstudent-why"
      aria-label="Why this student is struggling"
    >
      <h2 className="wm-tstudent-h2">What’s going on</h2>
      <p className="wm-tstudent-why-headline">{struggle.headline}</p>
      <p className="wm-tstudent-why-detail">{struggle.detail}</p>
      <div className="wm-tstudent-why-tags">
        {struggle.matched_misconception != null ? (
          <span className="wm-tstudent-tag wm-tstudent-tag--misconception">
            <span className="wm-tstudent-tag-key">Misconception</span>
            {struggle.matched_misconception}
          </span>
        ) : null}
        {struggle.helpneed_trend != null ? (
          <span className="wm-tstudent-tag wm-tstudent-tag--trend">
            {TREND_LABEL[struggle.helpneed_trend]}
          </span>
        ) : null}
        {struggle.recent_error_rate != null ? (
          <span className="wm-tstudent-tag wm-tstudent-tag--rate">
            {Math.round(struggle.recent_error_rate * 100)}% recent errors
          </span>
        ) : null}
      </div>
    </section>
  );
}

function SkillColumn({
  title,
  tone,
  skills,
}: {
  title: string;
  tone: 'strong' | 'weak';
  skills: KcMasteryView[];
}): React.JSX.Element {
  return (
    <div className={`wm-tstudent-skillcol wm-tstudent-skillcol--${tone}`}>
      <h3 className="wm-tstudent-skillcol-title">{title}</h3>
      {skills.length === 0 ? (
        <p className="wm-tstudent-skillcol-empty">
          {tone === 'strong' ? 'No mastered skills yet.' : 'Nothing flagged.'}
        </p>
      ) : (
        <ul className="wm-tstudent-skilllist">
          {skills.map((skill) => (
            <li key={skill.kc_id} className="wm-tstudent-skill">
              <span className="wm-tstudent-skill-name">{skill.skill_name}</span>
              <span className="wm-tstudent-skill-bar" aria-hidden="true">
                <span
                  className={`wm-tstudent-skill-fill wm-tstudent-skill-fill--${tone}`}
                  style={{ width: `${String(Math.round(skill.probability * 100))}%` }}
                />
              </span>
              <span className="wm-tstudent-skill-pct">{Math.round(skill.probability * 100)}%</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const OUTCOME_DOT: Record<ActivityEventView['outcome'], string> = {
  correct: 'correct',
  incorrect: 'incorrect',
  neutral: 'neutral',
};

function Timeline({ events }: { events: ActivityEventView[] }): React.JSX.Element {
  if (events.length === 0) {
    return <p className="wm-tstudent-skillcol-empty">No recent activity.</p>;
  }
  return (
    <ol className="wm-tstudent-timeline">
      {events.map((ev, i) => (
        <li key={`${ev.at}-${String(i)}`} className="wm-tstudent-tl-item">
          <span
            className={`wm-tstudent-tl-dot wm-tstudent-tl-dot--${OUTCOME_DOT[ev.outcome]}`}
            aria-hidden="true"
          />
          <span className="wm-tstudent-tl-body">
            <span className="wm-tstudent-tl-label">{ev.label}</span>
            <span className="wm-tstudent-tl-time">{ev.at}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function AssignSection({
  units,
  assignedUnitId,
  busy,
  onAssign,
}: {
  units: AssignableUnitView[];
  assignedUnitId: string | null;
  busy: boolean;
  onAssign: (unitId: string) => void;
}): React.JSX.Element {
  return (
    <section className="wm-tstudent-card wm-tstudent-assign" aria-label="Assign next unit">
      <h2 className="wm-tstudent-h2">Assign next unit</h2>
      <p className="wm-tstudent-assign-hint">
        The student sees this as their starred “Keep going” target.
      </p>
      <ul className="wm-tstudent-assign-list">
        {units.map((unit) => {
          const assigned = unit.unit_id === assignedUnitId;
          return (
            <li key={unit.unit_id} className="wm-tstudent-assign-row">
              <span className="wm-tstudent-assign-info">
                <span className="wm-tstudent-assign-title">{unit.title}</span>
                {!unit.available ? (
                  <span className="wm-tstudent-assign-lock">Prerequisites not met</span>
                ) : null}
              </span>
              {assigned ? (
                <span className="wm-tstudent-assign-done">
                  <span className="wm-tstudent-assign-star" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                      <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
                    </svg>
                  </span>
                  Assigned
                </span>
              ) : (
                <button
                  type="button"
                  className="wm-tstudent-assign-btn"
                  disabled={busy || !unit.available}
                  onClick={() => onAssign(unit.unit_id)}
                >
                  Assign
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
