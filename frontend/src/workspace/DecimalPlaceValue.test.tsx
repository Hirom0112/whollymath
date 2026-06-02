import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DecimalPlaceValue } from './DecimalPlaceValue';
import type { DecimalPlaceValueProps } from './DecimalPlaceValue';

// DecimalPlaceValue is DISPLAY-ONLY (like RatioTable / SetModelStimulus) — it draws the factor
// decimals in aligned place columns and is NOT an answer input. These tests pin: it draws a real
// table with the place labels and one row per operand, lays each operand's digits in the right
// columns, aligns the decimal point after the ones column, reads the chart in its caption, and
// shows the FACTORS only (no product, §8.2). It takes explicit typed props mirroring the backend
// DecimalPlaceValueStimulus dataclass.

// 0.5 × 0.15 laid on a shared ones·tenths·hundredths grid: 0.50 and 0.15.
const props: DecimalPlaceValueProps = {
  kind: 'decimal_place_value',
  columns: ['ones', 'tenths', 'hundredths'],
  point_after: 0,
  rows: [
    { decimal_text: '0.50', digits: ['0', '5', '0'] },
    { decimal_text: '0.15', digits: ['0', '1', '5'] },
  ],
};

describe('DecimalPlaceValue', () => {
  it('renders a real table with a column header per place', () => {
    render(<DecimalPlaceValue {...props} />);
    const table = screen.getByTestId('wm-placeval');
    expect(table.tagName).toBe('TABLE');
    expect(within(table).getByRole('columnheader', { name: 'ones' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'tenths' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'hundredths' })).toBeInTheDocument();
  });

  it('renders one labelled row per operand with its decimal literal', () => {
    render(<DecimalPlaceValue {...props} />);
    expect(screen.getByRole('rowheader', { name: '0.50' })).toBeInTheDocument();
    expect(screen.getByRole('rowheader', { name: '0.15' })).toBeInTheDocument();
  });

  it("lays each operand's digits into the place columns in order", () => {
    const { container } = render(<DecimalPlaceValue {...props} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    const digitsOf = (row: Element): string[] =>
      [...row.querySelectorAll('.wm-placeval-cell')].map((c) => c.textContent ?? '');
    expect(digitsOf(rows[0])).toEqual(['0', '5', '0']);
    expect(digitsOf(rows[1])).toEqual(['0', '1', '5']);
  });

  it('draws an aligned decimal-point marker after the ones column in every row', () => {
    const { container } = render(<DecimalPlaceValue {...props} />);
    // One point marker per body row (2), each rendering the "." glyph.
    const points = container.querySelectorAll('td[data-testid="wm-placeval-point"]');
    expect(points).toHaveLength(2);
    points.forEach((p) => {
      expect(p.textContent).toBe('.');
    });
  });

  it('reads the chart in its accessible caption', () => {
    render(<DecimalPlaceValue {...props} />);
    expect(
      screen.getByText(/place-value chart\. columns: ones, tenths, hundredths/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/lined up on the decimal point: 0\.50 and 0\.15/i)).toBeInTheDocument();
  });

  it('shows only the factors — the product never appears as a row', () => {
    // 0.5 × 0.15 = 0.075; neither "0.075" nor "0.75" is a row label.
    render(<DecimalPlaceValue {...props} />);
    expect(screen.queryByRole('rowheader', { name: '0.075' })).toBeNull();
    expect(screen.queryByRole('rowheader', { name: '0.75' })).toBeNull();
    expect(screen.getAllByRole('rowheader')).toHaveLength(2);
  });
});
