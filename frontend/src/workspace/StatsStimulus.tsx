import type {
  DotPlotStimulusView,
  FrequencyTableStimulusView,
  HistogramStimulusView,
  ProblemView,
} from '@whollymath/shared-types';

import './StatsStimulus.css';

/**
 * A DISPLAY-ONLY statistics stimulus for the Unit-7 stats problem statements (CCSS 6.SP, TEKS
 * 6.12D). It draws the problem's data set as a VISUAL — a dot plot, a frequency/data table, or a
 * histogram — from the structured `stimulus` the backend attaches to a stats `ProblemView`.
 *
 * Like `FigureStimulus`, this is a STIMULUS, not an answer input: it renders inside the problem
 * statement and is NOT a WorkspaceWidget. The data set is the QUESTION INPUT; the answer (the
 * computed statistic) is never in the stimulus and is graded server-side by SymPy (no answer leak).
 * So this takes no value/onChange and never touches selectWidget / the answer contract — it only
 * displays. The prompt text remains the accessible fallback (the SVG/table is supplementary).
 *
 * Accessibility: each visual is one labeled region (role="img" for the SVG plots, a real <table>
 * for the frequency table) with an aria-label that reads the data, so a screen-reader user gets the
 * same information. The SVGs are static (no animation) → inherently reduced-motion safe.
 *
 * Custom SVG, no charting lib (TECH_STACK §2). Class names unique app-wide (prefix `wm-statstim-`).
 */

// SVG viewBox geometry (a fixed coordinate space; CSS scales it) — mirrors the NumberLine idiom.
const VIEW_W = 520;
const PLOT_PAD_X = 36;
const AXIS_Y_DOT = 150;
const DOT_R = 7;
const DOT_GAP = 18; // vertical spacing between stacked dots
const TICK_H = 8;

/** The distinct values present, sorted ascending — the dot-plot / x-axis categories. */
function distinctSorted(values: readonly number[]): number[] {
  return [...new Set(values)].sort((a, b) => a - b);
}

/** How many times each value occurs (the stack height above each tick). */
function countOf(values: readonly number[], value: number): number {
  return values.filter((v) => v === value).length;
}

function DotPlot({ stimulus }: { stimulus: DotPlotStimulusView }): React.JSX.Element {
  const values = stimulus.values;
  const categories = distinctSorted(values);
  const maxStack = categories.reduce((m, v) => Math.max(m, countOf(values, v)), 0);
  // Lay the categories out evenly across the track; one labeled tick per distinct value.
  const trackStart = PLOT_PAD_X;
  const trackEnd = VIEW_W - PLOT_PAD_X;
  const step = categories.length > 1 ? (trackEnd - trackStart) / (categories.length - 1) : 0;
  const xFor = (i: number): number =>
    categories.length > 1 ? trackStart + i * step : (trackStart + trackEnd) / 2;
  // The viewBox grows UPWARD with the tallest stack so the top dots never clip; the axis stays at a
  // fixed y and the dots stack above it. minY is negative when the stack is taller than the headroom.
  const stackTop = AXIS_Y_DOT - DOT_R - 2 - (maxStack - 1) * DOT_GAP;
  const minY = Math.min(0, stackTop - DOT_R - 6);
  const viewH = AXIS_Y_DOT + TICK_H + 46 - minY;
  const label = `Dot plot. ${categories
    .map((v) => `${String(countOf(values, v))} at ${String(v)}`)
    .join(', ')}.`;
  return (
    <svg
      viewBox={`0 ${String(minY)} ${String(VIEW_W)} ${String(viewH)}`}
      className="wm-statstim-svg"
      role="img"
      aria-label={label}
    >
      {/* axis line */}
      <line
        x1={trackStart - 12}
        y1={AXIS_Y_DOT}
        x2={trackEnd + 12}
        y2={AXIS_Y_DOT}
        className="wm-statstim-axis"
      />
      {categories.map((value, i) => {
        const x = xFor(i);
        const stack = countOf(values, value);
        return (
          <g key={value}>
            <line
              x1={x}
              y1={AXIS_Y_DOT}
              x2={x}
              y2={AXIS_Y_DOT + TICK_H}
              className="wm-statstim-tick"
            />
            <text
              x={x}
              y={AXIS_Y_DOT + TICK_H + 20}
              textAnchor="middle"
              className="wm-statstim-axislabel"
            >
              {value}
            </text>
            {Array.from({ length: stack }, (_, k) => (
              <circle
                key={k}
                cx={x}
                cy={AXIS_Y_DOT - DOT_R - 2 - k * DOT_GAP}
                r={DOT_R}
                className="wm-statstim-dot"
              />
            ))}
          </g>
        );
      })}
      <text
        x={(trackStart + trackEnd) / 2}
        y={AXIS_Y_DOT + TICK_H + 38}
        textAnchor="middle"
        className="wm-statstim-caption"
      >
        {stimulus.axis_label}
      </text>
    </svg>
  );
}

function FrequencyTable({ stimulus }: { stimulus: FrequencyTableStimulusView }): React.JSX.Element {
  const caption = `Frequency table. ${stimulus.rows
    .map((r) => `${r.label}: ${String(r.count)}`)
    .join(', ')}.`;
  return (
    <table className="wm-statstim-table" aria-label={caption}>
      <thead>
        <tr>
          <th scope="col">{stimulus.category_label}</th>
          <th scope="col">{stimulus.count_label}</th>
        </tr>
      </thead>
      <tbody>
        {stimulus.rows.map((row) => (
          <tr key={row.label}>
            <th scope="row">{row.label}</th>
            <td>{row.count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const HIST_VIEW_H = 200;
const HIST_AXIS_Y = 160;
const HIST_BAR_GAP = 14;

function Histogram({ stimulus }: { stimulus: HistogramStimulusView }): React.JSX.Element {
  const bins = stimulus.bins;
  const maxCount = bins.reduce((m, b) => Math.max(m, b.count), 0) || 1;
  const trackStart = PLOT_PAD_X;
  const trackEnd = VIEW_W - PLOT_PAD_X;
  const barSlot = bins.length > 0 ? (trackEnd - trackStart) / bins.length : trackEnd - trackStart;
  const barW = Math.max(barSlot - HIST_BAR_GAP, 8);
  const maxBarH = HIST_AXIS_Y - 20;
  const label = `Histogram. ${bins
    .map((b) => `${String(b.lo)} to ${String(b.hi)}: ${String(b.count)}`)
    .join(', ')}.`;
  return (
    <svg
      viewBox={`0 0 ${String(VIEW_W)} ${String(HIST_VIEW_H)}`}
      className="wm-statstim-svg"
      role="img"
      aria-label={label}
    >
      <line
        x1={trackStart - 12}
        y1={HIST_AXIS_Y}
        x2={trackEnd + 12}
        y2={HIST_AXIS_Y}
        className="wm-statstim-axis"
      />
      {bins.map((bin, i) => {
        const x = trackStart + i * barSlot + (barSlot - barW) / 2;
        const h = bin.count > 0 ? (bin.count / maxCount) * maxBarH : 0;
        return (
          <g key={bin.lo}>
            {bin.count > 0 ? (
              <rect x={x} y={HIST_AXIS_Y - h} width={barW} height={h} className="wm-statstim-bar" />
            ) : null}
            <text
              x={x + barW / 2}
              y={HIST_AXIS_Y - h - 6}
              textAnchor="middle"
              className="wm-statstim-barcount"
            >
              {bin.count}
            </text>
            <text
              x={x + barW / 2}
              y={HIST_AXIS_Y + 18}
              textAnchor="middle"
              className="wm-statstim-axislabel"
            >
              {bin.lo}–{bin.hi}
            </text>
          </g>
        );
      })}
      <text
        x={(trackStart + trackEnd) / 2}
        y={HIST_AXIS_Y + 36}
        textAnchor="middle"
        className="wm-statstim-caption"
      >
        {stimulus.axis_label}
      </text>
    </svg>
  );
}

/**
 * Render the display-only stimulus a stats `ProblemView` carries, or nothing when it has none
 * (every non-stats problem, and KC_statistical_questions). The Tutor calls this above the answer
 * form; the prompt text is shown regardless, so this is purely additive.
 */
export function StatsStimulus({ problem }: { problem: ProblemView }): React.JSX.Element | null {
  const stimulus = problem.stimulus;
  if (stimulus == null) return null;
  return (
    <div className="wm-statstim">
      {stimulus.kind === 'dot_plot' ? <DotPlot stimulus={stimulus} /> : null}
      {stimulus.kind === 'frequency_table' ? <FrequencyTable stimulus={stimulus} /> : null}
      {stimulus.kind === 'histogram' ? <Histogram stimulus={stimulus} /> : null}
    </div>
  );
}
