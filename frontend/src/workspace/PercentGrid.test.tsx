import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PercentGrid } from './PercentGrid';

// PercentGrid is DISPLAY-ONLY (like SetModelStimulus) — it draws the 10x10 hundred-grid with the
// named percent shaded, and is NOT an answer input. These tests pin: it always draws 100 cells;
// it shades exactly `shaded` of them; it shades the percent and NOT the computed answer (no leak);
// it reads the rate-per-100 in its aria-label; and a stray value is clamped to the grid.

function filledCount(container: HTMLElement): number {
  return container.querySelectorAll('[data-filled="true"]').length;
}

describe('PercentGrid', () => {
  it('always draws 100 cells', () => {
    const { container } = render(<PercentGrid percent={30} shaded={30} />);
    expect(container.querySelectorAll('.wm-pctgrid-cell')).toHaveLength(100);
  });

  it('shades exactly `shaded` cells with the green-accent modifier', () => {
    const { container } = render(<PercentGrid percent={30} shaded={30} />);
    expect(filledCount(container)).toBe(30);
    expect(container.querySelectorAll('.wm-pctgrid-cell--on')).toHaveLength(30);
  });

  it('shades the percent (30), never the computed answer (18 for "30% of 60")', () => {
    const { container } = render(<PercentGrid percent={30} shaded={30} />);
    // 30 cells shaded, not 18 — the picture shows the question input, not the answer.
    expect(filledCount(container)).toBe(30);
    expect(filledCount(container)).not.toBe(18);
  });

  it('fills cells in reading order from the top-left', () => {
    const { container } = render(<PercentGrid percent={12} shaded={12} />);
    // The first 12 cells (indices 0..11) are filled; the 13th is not.
    expect(container.querySelector('[data-cell-index="11"]')?.getAttribute('data-filled')).toBe(
      'true',
    );
    expect(container.querySelector('[data-cell-index="12"]')?.getAttribute('data-filled')).toBe(
      'false',
    );
  });

  it('reads the rate per 100 in its accessible label', () => {
    render(<PercentGrid percent={30} shaded={30} />);
    expect(
      screen.getByRole('img', {
        name: /30 of 100 cells shaded: 30 percent, a rate of 30 per 100/i,
      }),
    ).toBeInTheDocument();
  });

  it('shows the caption "N per 100"', () => {
    render(<PercentGrid percent={75} shaded={75} />);
    expect(screen.getByText('75 per 100')).toBeInTheDocument();
  });

  it('clamps a stray shaded value to the 100-cell grid', () => {
    const { container } = render(<PercentGrid percent={150} shaded={150} />);
    expect(filledCount(container)).toBe(100);
    const { container: under } = render(<PercentGrid percent={-10} shaded={-10} />);
    expect(filledCount(under)).toBe(0);
  });

  it('renders the same output every time for the same props (deterministic)', () => {
    const order = (c: HTMLElement): string[] =>
      [...c.querySelectorAll<SVGRectElement>('[data-cell-index]')].map(
        (r) => r.getAttribute('data-filled') ?? '',
      );
    const a = render(<PercentGrid percent={40} shaded={40} />);
    const b = render(<PercentGrid percent={40} shaded={40} />);
    expect(order(a.container)).toEqual(order(b.container));
  });
});
