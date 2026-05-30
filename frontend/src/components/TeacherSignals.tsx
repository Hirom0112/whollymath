// Shared alert + category visual system for the teacher surface (TODO TCH.F4). Two primitives
// reused by the roster (TCH.F2) and the student drill-in (TCH.F3):
//
//   <CategoryChip>  — the ranked bucket (struggling / needs-attention / on-track)
//   <AlertBadge>    — one named alert at a severity (info / warn / urgent)
//
// Accessibility rule (TEACHER_NEEDS.md B "color never the sole signal"): every chip and badge
// pairs its color with a DRAWN icon and a WORD, so meaning survives color-blindness and grayscale.
// Icons are inline SVG, never emoji (project convention). Colors come from the semantic
// `--wm-mean-*` tokens. Class names are unique app-wide (`.wm-teacher-*`).

import type { AlertKind, AlertSeverity, StudentCategory, TeacherAlertView } from '../api/teacher';
import './TeacherSignals.css';

/* ── Drawn icons (currentColor; aria-hidden — the adjacent word carries the meaning) ── */

function IconAlertTriangle(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M12 3 L22 20 H2 Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <line x1="12" y1="9" x2="12" y2="14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="12" cy="17.3" r="1.3" fill="currentColor" />
    </svg>
  );
}

function IconEye(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        d="M2 12 C5 6 19 6 22 12 C19 18 5 18 2 12 Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}

function IconCheck(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <polyline
        points="4,13 10,19 20,5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function IconInfo(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.2" />
      <circle cx="12" cy="7.6" r="1.3" fill="currentColor" />
      <line x1="12" y1="11" x2="12" y2="17" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

/* ── Category chip (TCH.B6 ranking) ── */

const CATEGORY_META: Record<
  StudentCategory,
  { label: string; tint: string; icon: () => React.JSX.Element }
> = {
  struggling: { label: 'Struggling', tint: 'wrong', icon: IconAlertTriangle },
  needs_attention: { label: 'Needs attention', tint: 'attention', icon: IconEye },
  on_track: { label: 'On track', tint: 'correct', icon: IconCheck },
};

/** The ranked-category chip: drawn icon + word + semantic tint (color is never the only cue). */
export function CategoryChip({
  category,
  size = 'md',
}: {
  category: StudentCategory;
  size?: 'sm' | 'md';
}): React.JSX.Element {
  const meta = CATEGORY_META[category];
  const Icon = meta.icon;
  return (
    <span className={`wm-teacher-chip wm-teacher-chip--${meta.tint} wm-teacher-chip--${size}`}>
      <span className="wm-teacher-chip-ico">
        <Icon />
      </span>
      {meta.label}
    </span>
  );
}

/* ── Progress bar (shared by the roster + drill-in for course % complete) ── */

/**
 * A course-progress bar. `value` is 0..1. The numeric percent label sits beside it so the bar's
 * meaning never depends on width/color alone. `tone` tints the fill to echo the student's
 * category without becoming the only cue (the label and chip carry the state).
 */
export function ProgressBar({
  value,
  tone = 'neutral',
}: {
  value: number;
  tone?: 'neutral' | StudentCategory;
}): React.JSX.Element {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <span className="wm-teacher-progress">
      <span className="wm-teacher-progress-track">
        <span
          className={`wm-teacher-progress-fill wm-teacher-progress-fill--${tone}`}
          style={{ width: `${String(pct)}%` }}
        />
      </span>
      <span className="wm-teacher-progress-label">{pct}%</span>
    </span>
  );
}

/* ── Alert badge (TCH.B5 named, tunable rules) ── */

// Short human label per named rule. The plain-language `message` carries the specifics.
const ALERT_LABEL: Record<AlertKind, string> = {
  STUCK: 'Stuck',
  REPEATED_MISCONCEPTION: 'Repeated misconception',
  LOW_ENGAGEMENT: 'Low engagement',
  FAILING_TREND: 'Falling accuracy',
  IDLE: 'Idle',
  REMEDIATION_STUCK: 'Stuck in remediation',
  HINT_DEPENDENT: 'Hint dependent',
};

const SEVERITY_META: Record<
  AlertSeverity,
  { tint: string; icon: () => React.JSX.Element; word: string }
> = {
  urgent: { tint: 'wrong', icon: IconAlertTriangle, word: 'Urgent' },
  warn: { tint: 'attention', icon: IconAlertTriangle, word: 'Warning' },
  info: { tint: 'info', icon: IconInfo, word: 'Note' },
};

/**
 * One alert. Two layouts:
 *  - `compact` (default): a small pill (icon + rule label) for the roster row's badge cluster.
 *  - `full`: icon + rule label + the plain-language message, for the drill-in alert banner.
 * The severity word is exposed to assistive tech via the pill's title/label so color isn't relied on.
 */
export function AlertBadge({
  alert,
  variant = 'compact',
}: {
  alert: TeacherAlertView;
  variant?: 'compact' | 'full';
}): React.JSX.Element {
  const sev = SEVERITY_META[alert.severity];
  const Icon = sev.icon;
  const label = ALERT_LABEL[alert.kind];
  return (
    <span
      className={`wm-teacher-alert wm-teacher-alert--${sev.tint} wm-teacher-alert--${variant}`}
      title={`${sev.word}: ${label}`}
    >
      <span className="wm-teacher-alert-ico">
        <Icon />
      </span>
      <span className="wm-teacher-alert-body">
        <span className="wm-teacher-alert-label">
          <span className="wm-teacher-alert-sev">{sev.word}</span>
          {label}
        </span>
        {variant === 'full' ? (
          <span className="wm-teacher-alert-msg">{alert.message}</span>
        ) : null}
      </span>
    </span>
  );
}
