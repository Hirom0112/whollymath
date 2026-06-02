import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FractionArea } from './FractionArea';
import type { FractionAreaProps } from './FractionArea';

// FractionArea is DISPLAY-ONLY (like SetModelStimulus) — it draws the two OPERAND fractions of an
// arithmetic problem as area-model bars and is NOT an answer input. These tests pin: each operand
// bar is partitioned into its denominator with its numerator shaded; add/subtract stack two bars
// while multiply/divide draw an area grid; the operands are read in the aria-label; and NO answer
// (sum/difference/product/quotient) is drawn.

function shadedCellCount(container: HTMLElement, modifier: string): number {
  return container.querySelectorAll(`rect.wm-fracarea-cell--${modifier}`).length;
}

describe('FractionArea', () => {
  it('partitions each stacked bar into its denominator with its numerator shaded (add)', () => {
    const props: FractionAreaProps = {
      op: 'add',
      first: { numerator: 1, denominator: 2 },
      second: { numerator: 1, denominator: 4 },
    };
    const { container } = render(<FractionArea {...props} />);
    const bars = container.querySelectorAll('[data-testid="wm-fracarea-bar"]');
    expect(bars).toHaveLength(2);
    // First bar: 2 cells total, 1 shaded green; second bar: 4 cells, 1 shaded pink.
    expect(bars[0].querySelectorAll('rect.wm-fracarea-cell')).toHaveLength(2);
    expect(bars[1].querySelectorAll('rect.wm-fracarea-cell')).toHaveLength(4);
    expect(shadedCellCount(container, 'a')).toBe(1);
    expect(shadedCellCount(container, 'b')).toBe(1);
  });

  it('draws an area grid of rows x cols for multiply', () => {
    const props: FractionAreaProps = {
      op: 'multiply',
      first: { numerator: 2, denominator: 3 }, // 3 columns, 2 shaded across
      second: { numerator: 1, denominator: 4 }, // 4 rows, 1 shaded down
    };
    const { container } = render(<FractionArea {...props} />);
    // Grid has denominator(first) x denominator(second) = 3 x 4 = 12 cells.
    expect(container.querySelectorAll('rect.wm-fracarea-cell')).toHaveLength(12);
    // 2 of 3 columns shaded across -> data-in-col true on 2 of every 4-row column = 8 cells.
    const inCol = container.querySelectorAll('rect[data-in-col="true"]');
    expect(inCol).toHaveLength(8);
    // 1 of 4 rows shaded down -> data-in-row true on 1 row across 3 cols = 3 cells.
    const inRow = container.querySelectorAll('rect[data-in-row="true"]');
    expect(inRow).toHaveLength(3);
  });

  it('reads the operands and operation in its accessible label', () => {
    render(
      <FractionArea
        op="divide"
        first={{ numerator: 1, denominator: 2 }}
        second={{ numerator: 3, denominator: 4 }}
      />,
    );
    expect(
      screen.getByRole('img', { name: /area model of 1\/2 divided by 3\/4/i }),
    ).toBeInTheDocument();
  });

  it('shows only the two operands, never the answer (no result bar)', () => {
    // 1/2 + 1/4 = 3/4. A "3/4" answer bar must NOT appear; only the 1/2 and 1/4 operand bars do.
    const { container } = render(
      <FractionArea
        op="add"
        first={{ numerator: 1, denominator: 2 }}
        second={{ numerator: 1, denominator: 4 }}
      />,
    );
    const denominators = [...container.querySelectorAll('[data-testid="wm-fracarea-bar"]')].map(
      (b) => b.getAttribute('data-denominator'),
    );
    expect(denominators).toEqual(['2', '4']);
    // The caption echoes operands + operator only — never an equals/result.
    expect(container.querySelector('.wm-fracarea-caption')?.textContent).toBe('1/2 + 1/4');
    expect(container.querySelector('.wm-fracarea-caption')?.textContent).not.toContain('=');
  });

  it('uses the correct operator sign for each op', () => {
    const cases: [FractionAreaProps['op'], string][] = [
      ['add', '+'],
      ['subtract', '−'],
      ['multiply', '×'],
      ['divide', '÷'],
    ];
    for (const [op, sign] of cases) {
      const { container } = render(
        <FractionArea
          op={op}
          first={{ numerator: 1, denominator: 2 }}
          second={{ numerator: 1, denominator: 3 }}
        />,
      );
      expect(container.querySelector('.wm-fracarea-caption')?.textContent).toBe(`1/2 ${sign} 1/3`);
    }
  });
});
