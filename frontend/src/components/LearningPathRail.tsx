import './LearningPathRail.css';

/**
 * LearningPathRail — the shared "connected sequence of nodes" visual the learning path uses.
 *
 * Extracted from CourseMap so the course home and the per-unit lesson list render the SAME rail
 * (one rail, no divergence — STU.4 / the cross-cutting rail-extraction item). It is purely
 * presentational: the host normalizes whatever it has (course KCs, a unit's lessons) into
 * `PathNode`s and gets clicks back via `onSelect`. It owns the status badge, the gold mastery
 * star, the numbered/✓ dot, the connecting rail line, and the card — so both consumers stay
 * identical. Class names are unique app-wide (`wm-pathrail-*`); color always pairs with a label
 * and the lock state, never carrying meaning alone (tokens.css note).
 *
 * Generic over the id type so a caller keeps its own branded id (e.g. `KnowledgeComponentId`) end
 * to end; the rail only needs the id to key rows and hand back to `onSelect`.
 */

export type PathNodeStatus = 'locked' | 'available' | 'in_progress' | 'mastered' | 'due_review';

/** A soft per-row tint (row IDENTITY, not status — the badge carries status). */
export type PathNodeTint = 'sky' | 'mint' | 'butter' | 'warm' | 'lavender';

export interface PathNode<TId extends string = string> {
  /** Unique row id — keys the row and is handed back on click. */
  id: TId;
  /** The row's name (a skill name, a lesson title). */
  title: string;
  /** One-line description under the title. */
  description: string;
  status: PathNodeStatus;
  /** Identity tint for the dot + card. */
  tint: PathNodeTint;
  /** 0–100 mastery/progress bar; null hides the bar. */
  progressPct: number | null;
  /**
   * True for a lesson deliberately NOT built as an interactive tutor lesson — a pure-concept
   * item with no tutor mechanism (DEC.FINLIT). Such a row shows an honest "Concept lesson"
   * badge + copy instead of a status CTA, and the host's `onSelect` must not start a session
   * for it. Defaults to absent/false (a normal, status-driven row).
   */
  conceptOnly?: boolean;
}

// Per-status label + call-to-action. The label is always rendered (status is never color-only).
const STATUS_META: Record<PathNodeStatus, { label: string; cta: string | null }> = {
  locked: { label: 'Locked', cta: null },
  available: { label: 'Ready to start', cta: 'Start' },
  in_progress: { label: 'In progress', cta: 'Keep going' },
  mastered: { label: 'Mastered', cta: 'Practice again' },
  due_review: { label: 'Time to review', cta: 'Review' },
};

// A concept-only lesson is honest about NOT being an interactive tutor lesson: it carries its
// own badge + CTA copy (DEC.FINLIT), never the status "Ready to start"/"Start" of a tutor lesson.
const CONCEPT_BADGE = 'Concept lesson';
const CONCEPT_CTA = 'Covered in the TEKS personal-financial-literacy strand — not a tutor lesson.';

function StatusBadge({ status }: { status: PathNodeStatus }): React.JSX.Element {
  return (
    <span className={`wm-pathrail-badge wm-pathrail-badge--${status}`}>
      {STATUS_META[status].label}
    </span>
  );
}

function ConceptBadge(): React.JSX.Element {
  return <span className="wm-pathrail-badge wm-pathrail-badge--concept">{CONCEPT_BADGE}</span>;
}

// The gold mastery star beside a mastered row's name — the drawn brand spark (never an emoji),
// additive to the "Mastered" badge + check dot (color reinforces, never the only cue).
function MasteryStar(): React.JSX.Element {
  return (
    <span className="wm-pathrail-star" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
      </svg>
    </span>
  );
}

function PathRow<TId extends string>({
  node,
  index,
  lockedCta,
  onSelect,
}: {
  node: PathNode<TId>;
  index: number;
  lockedCta: string;
  onSelect: (id: TId) => void;
}): React.JSX.Element {
  // A concept-only lesson is non-interactive by design (DEC.FINLIT): never locked-styled,
  // never status-driven. It stays clickable so the host can surface its explanatory note.
  const conceptOnly = node.conceptOnly === true;
  const locked = !conceptOnly && node.status === 'locked';
  const meta = STATUS_META[node.status];
  const pct = node.progressPct != null ? Math.round(node.progressPct) : null;

  return (
    <li
      className={`wm-pathrail-node wm-pathrail-node--${node.status}${
        conceptOnly ? ' wm-pathrail-node--concept' : ''
      }`}
    >
      <span className="wm-pathrail-rail" aria-hidden="true">
        <span className={`wm-pathrail-dot wm-pathrail-dot--${node.tint}`}>
          {node.status === 'mastered' ? '✓' : index + 1}
        </span>
      </span>
      <button
        type="button"
        className={`wm-pathrail-card wm-pathrail-card--${node.tint}${
          conceptOnly ? ' wm-pathrail-card--concept' : ''
        }`}
        disabled={locked}
        aria-disabled={locked}
        onClick={() => {
          if (!locked) onSelect(node.id);
        }}
      >
        <span className="wm-pathrail-card-top">
          <span className="wm-pathrail-skill">
            {node.title}
            {!conceptOnly && node.status === 'mastered' ? <MasteryStar /> : null}
          </span>
          {conceptOnly ? <ConceptBadge /> : <StatusBadge status={node.status} />}
        </span>
        <span className="wm-pathrail-desc">{node.description}</span>
        {!conceptOnly && pct != null ? (
          <span className="wm-pathrail-progress" aria-hidden="true">
            <span className="wm-pathrail-progress-fill" style={{ width: `${String(pct)}%` }} />
          </span>
        ) : null}
        <span className="wm-pathrail-cta">
          {conceptOnly ? CONCEPT_CTA : locked ? lockedCta : meta.cta}
        </span>
      </button>
    </li>
  );
}

export function LearningPathRail<TId extends string = string>({
  nodes,
  onSelect,
  lockedCta = 'Finish the earlier skills to unlock',
}: {
  nodes: PathNode<TId>[];
  onSelect: (id: TId) => void;
  /** CTA text shown on a locked row (e.g. "…earlier lessons…" on a unit). */
  lockedCta?: string;
}): React.JSX.Element {
  return (
    <ol className="wm-pathrail-list">
      {nodes.map((node, i) => (
        <PathRow key={node.id} node={node} index={i} lockedCta={lockedCta} onSelect={onSelect} />
      ))}
    </ol>
  );
}
