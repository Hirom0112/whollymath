import './ClassifySets.css';

import type { WorkspaceWidgetProps } from './WidgetContract';

/**
 * The number-set classification input (KC_classify_number_sets, TEKS 6.2A): given a number, the
 * student marks which set(s) of the 6th-grade number system it belongs to. The sets NEST — every
 * whole number is an integer, every integer is rational — so they are drawn as concentric regions
 * (whole inside integer inside rational), not overlapping circles, because the truth is subset
 * containment, not mere intersection.
 *
 * Controlled component (the HR.A5 {@link WorkspaceWidgetProps} contract): the parent owns the answer
 * `value` as a STRING and the widget renders / edits it. The string is the wire format the backend
 * verifier grades — the selected set ids in canonical (smallest→largest) order, comma-joined:
 * "rational", "integer,rational", "whole,integer,rational". Canonical order makes the answer stable
 * regardless of click order, so the backend compares it directly (the surface neither decides
 * membership nor grades it — §8.2; the verifier knows e.g. that −3 is integer+rational).
 *
 * Multi-select: a number can belong to several sets at once, so each region is an independent toggle
 * (role="checkbox"), keyboard-operable (Tab to a region, Space/Enter toggles). The `number` shown in
 * the middle is just the stimulus label the item provides; it carries no answer.
 *
 * Custom SVG/markup, no widget lib (TECH_STACK §2). Class names unique app-wide (global CSS).
 *
 * NOTE — wire/routing DEFERRED: this widget emits the set-id string but is NOT yet routed. The
 * backend classify-sets contract (widget_id="classify_sets" / an answer_kind, and the verifier path)
 * is not in committed code; the selectWidget case + ProblemView wiring land later against the real
 * backend types, like the expression / coordinate-plane / inequality widgets (no invented cross-lane
 * contract — §1/§5).
 */

/** The 6th-grade number sets, OUTERMOST → innermost for rendering (rational contains integer
 * contains whole). `id` is the wire token; `canonicalRank` fixes the answer-string order. */
const SETS: readonly {
  readonly id: string;
  readonly label: string;
  readonly canonicalRank: number;
}[] = [
  { id: 'rational', label: 'Rational', canonicalRank: 2 },
  { id: 'integer', label: 'Integers', canonicalRank: 1 },
  { id: 'whole', label: 'Whole', canonicalRank: 0 },
];

/** The canonical answer string for a set of selected ids: smallest→largest, comma-joined, or "". */
export function selectionToAnswer(selected: ReadonlySet<string>): string {
  return SETS.filter((s) => selected.has(s.id))
    .slice()
    .sort((a, b) => a.canonicalRank - b.canonicalRank)
    .map((s) => s.id)
    .join(',');
}

/** Parse a controlled answer string back into the set of selected ids (tolerant of whitespace and
 * unknown tokens — a stray token is ignored, validity is the verifier's call). */
export function answerToSelection(answer: string): Set<string> {
  const known = new Set(SETS.map((s) => s.id));
  return new Set(
    answer
      .split(',')
      .map((t) => t.trim())
      .filter((t) => known.has(t)),
  );
}

// Concentric region geometry (SVG viewBox units): three nested rounded rects, each inset from the
// one outside it, so containment reads at a glance.
const VIEW_W = 320;
const VIEW_H = 320;
const INSETS = [10, 58, 118]; // rational, integer, whole — outer→inner

export function ClassifySets({
  value,
  onChange,
  disabled = false,
  prompt,
  number,
}: WorkspaceWidgetProps<string> & {
  /** Optional kid-friendly label above the figure. */
  prompt?: string;
  /** The stimulus number being classified (e.g. "-3", "1/2"), shown in the center. Display only. */
  number?: string;
}): React.JSX.Element {
  const selected = answerToSelection(value);

  function toggle(id: string): void {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onChange(selectionToAnswer(next));
  }

  function handleKeyDown(event: React.KeyboardEvent<SVGGElement>, id: string): void {
    if (disabled) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggle(id);
    }
  }

  return (
    <div className="wm-venn" role="group" aria-label="Classify the number into its sets">
      {prompt !== undefined ? <p className="wm-venn-prompt">{prompt}</p> : null}
      <svg
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        width={VIEW_W}
        height={VIEW_H}
        className="wm-venn-svg"
      >
        {SETS.map((set, depth) => {
          const inset = INSETS[depth];
          const w = VIEW_W - inset * 2;
          const h = VIEW_H - inset * 2;
          const isSelected = selected.has(set.id);
          return (
            <g
              key={set.id}
              role="checkbox"
              aria-checked={isSelected}
              aria-label={set.label}
              tabIndex={disabled ? -1 : 0}
              className={`wm-venn-region${isSelected ? ' wm-venn-region--selected' : ''}`}
              onClick={(event) => {
                // Stop the click bubbling to the larger region behind it, so tapping the inner
                // "Whole" ring toggles only Whole, not Integer/Rational underneath.
                event.stopPropagation();
                toggle(set.id);
              }}
              onKeyDown={(event) => {
                handleKeyDown(event, set.id);
              }}
            >
              <rect x={inset} y={inset} width={w} height={h} rx={28} className="wm-venn-ring" />
              <text x={VIEW_W / 2} y={inset + 24} textAnchor="middle" className="wm-venn-label">
                {set.label}
              </text>
            </g>
          );
        })}
        {/* The stimulus number, dead center — display only, carries no answer. */}
        {number !== undefined ? (
          <text
            x={VIEW_W / 2}
            y={VIEW_H / 2 + 10}
            textAnchor="middle"
            className="wm-venn-number"
            aria-hidden="true"
          >
            {number}
          </text>
        ) : null}
      </svg>
    </div>
  );
}
