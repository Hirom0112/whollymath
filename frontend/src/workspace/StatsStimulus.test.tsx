import { render, screen } from '@testing-library/react';
import type { ProblemView } from '@whollymath/shared-types';
import { describe, expect, it } from 'vitest';

import { StatsStimulus } from './StatsStimulus';

// StatsStimulus is DISPLAY-ONLY (like FigureStimulus) — it visualizes a stats problem's data set
// inside the statement and is NOT an answer input. These tests pin: a dot plot draws one dot per
// data occurrence, a frequency table draws one row per category, a histogram draws one bar per
// occupied bin, and a problem with no stimulus renders nothing.

function problemWith(stimulus: ProblemView['stimulus']): ProblemView {
  return {
    problem_id: 'p-1',
    kc: 'KC_summary_statistics',
    surface_format: 'symbolic',
    statement: 'Find the mean of 4, 4, 5, 6, 9.',
    widget_id: 'number_entry',
    stimulus,
  };
}

describe('StatsStimulus', () => {
  it('draws one dot per data occurrence in a dot plot', () => {
    const { container } = render(
      <StatsStimulus
        problem={problemWith({
          kind: 'dot_plot',
          values: [4, 4, 5, 6, 9],
          axis_label: 'Value',
        })}
      />,
    );
    // 5 data points -> 5 dots (two stacked above 4).
    expect(container.querySelectorAll('circle.wm-statstim-dot')).toHaveLength(5);
    // One labeled tick per distinct value (4, 5, 6, 9).
    expect(screen.getByRole('img', { name: /dot plot/i })).toBeInTheDocument();
  });

  it('draws one row per category in a frequency table', () => {
    render(
      <StatsStimulus
        problem={problemWith({
          kind: 'frequency_table',
          rows: [
            { label: 'red', count: 8 },
            { label: 'blue', count: 5 },
            { label: 'green', count: 2 },
          ],
          category_label: 'Choice',
          count_label: 'Count',
        })}
      />,
    );
    // One <tbody> data row per category (3); header row excluded by scope.
    expect(screen.getByRole('rowheader', { name: /red/i })).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: /blue/i })).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: /green/i })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '8' })).toBeInTheDocument();
  });

  it('draws one bar per occupied bin in a histogram', () => {
    const { container } = render(
      <StatsStimulus
        problem={problemWith({
          kind: 'histogram',
          bins: [
            { lo: 10, hi: 19, count: 1 },
            { lo: 30, hi: 39, count: 5 },
          ],
          bin_width: 10,
          axis_label: 'Value',
        })}
      />,
    );
    // Two occupied bins -> two bars.
    expect(container.querySelectorAll('rect.wm-statstim-bar')).toHaveLength(2);
    expect(screen.getByRole('img', { name: /histogram/i })).toBeInTheDocument();
  });

  it('renders nothing for a problem with no stimulus', () => {
    const { container } = render(<StatsStimulus problem={problemWith(null)} />);
    expect(container.querySelector('.wm-statstim')).toBeNull();
  });
});
