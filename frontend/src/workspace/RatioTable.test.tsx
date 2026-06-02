import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { RatioTable } from './RatioTable';
import type { RatioTableProps } from './RatioTable';

// RatioTable is DISPLAY-ONLY (like SetModelStimulus) — it draws the two-row equivalent-ratios
// scaffold and is NOT an answer input. These tests pin: it shows the given numbers, leaves the
// asked cell BLANK (so no answer leaks, §8.2), shows the scale step, and reads the table in its
// caption. It takes explicit typed props mirroring the backend RatioTableStimulus dataclass.

// A unit-rate table: unit column (blank top, 1 bottom), then the given column (24, 6), scaled ÷6.
const unitRateProps: RatioTableProps = {
  top_label: 'Amount',
  bottom_label: 'Units',
  columns: [
    { top: null, bottom: 1 },
    { top: 24, bottom: 6 },
  ],
  scale_label: '÷6',
};

// An equivalent-ratios table: given column (2, 3), then asked column (blank top, 12), scaled ×4.
const equivProps: RatioTableProps = {
  top_label: 'Top',
  bottom_label: 'Bottom',
  columns: [
    { top: 2, bottom: 3 },
    { top: null, bottom: 12 },
  ],
  scale_label: '×4',
};

describe('RatioTable', () => {
  it('renders a real table with both labelled rows', () => {
    render(<RatioTable {...unitRateProps} />);
    const table = screen.getByTestId('wm-ratiotbl');
    expect(table.tagName).toBe('TABLE');
    expect(within(table).getByRole('rowheader', { name: 'Amount' })).toBeInTheDocument();
    expect(within(table).getByRole('rowheader', { name: 'Units' })).toBeInTheDocument();
  });

  it('shows the given numbers for a unit-rate table', () => {
    render(<RatioTable {...unitRateProps} />);
    const table = screen.getByTestId('wm-ratiotbl');
    expect(within(table).getByText('24')).toBeInTheDocument();
    expect(within(table).getByText('6')).toBeInTheDocument();
    expect(within(table).getByText('1')).toBeInTheDocument();
  });

  it('leaves the asked cell BLANK and never renders the answer (unit rate)', () => {
    const { container } = render(<RatioTable {...unitRateProps} />);
    // Exactly one blank cell, carrying the accessible "unknown value" label.
    const blanks = container.querySelectorAll('.wm-ratiotbl-cell-blank');
    expect(blanks).toHaveLength(1);
    expect(screen.getByLabelText('unknown value')).toBeInTheDocument();
    // The unit rate here is 24 / 6 = 4 — it must NOT appear as a numeric cell.
    const table = screen.getByTestId('wm-ratiotbl');
    expect(within(table).queryByText('4')).toBeNull();
  });

  it('leaves the asked cell BLANK and never renders the answer (equivalent ratios)', () => {
    const { container } = render(<RatioTable {...equivProps} />);
    expect(container.querySelectorAll('.wm-ratiotbl-cell-blank')).toHaveLength(1);
    // The missing term is 2 × 4 = 8 — it must NOT appear as a numeric cell.
    const table = screen.getByTestId('wm-ratiotbl');
    expect(within(table).queryByText('8')).toBeNull();
    // The givens DO appear.
    expect(within(table).getByText('2')).toBeInTheDocument();
    expect(within(table).getByText('3')).toBeInTheDocument();
    expect(within(table).getByText('12')).toBeInTheDocument();
  });

  it('shows the scale step (the scaffold structure, not the answer)', () => {
    render(<RatioTable {...equivProps} />);
    expect(screen.getByTestId('wm-ratiotbl-scale')).toHaveTextContent('×4');
  });

  it('reads the table in its accessible caption', () => {
    render(<RatioTable {...equivProps} />);
    expect(
      screen.getByText(/Ratio table\. Top over Bottom\..*2 to 3.*unknown to 12.*Scale step ×4/),
    ).toBeInTheDocument();
  });
});
