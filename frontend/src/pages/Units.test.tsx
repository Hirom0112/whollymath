import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { UnitListView } from '../api';

import { Units } from './Units';

// Pins the unit-shelf's contract with GET /units (src/api). `fetch` is stubbed so the test stays a
// pure component test (CLAUDE.md §9), the same approach as Tutor.test.tsx.

function okJson(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}

function mockUnits(data: UnitListView): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(okJson(data))),
  );
}

const LIST: UnitListView = {
  assigned_unit_slug: 'u2',
  units: [
    {
      unit_slug: 'u1',
      title: 'Ratios & Rates',
      description: 'Compare quantities.',
      order: 1,
      ccss_cluster: '6.RP.A',
      teks_cluster: '6.4 / 6.5',
      status: 'available',
      percent_complete: 0,
      lesson_count: 6,
      assigned: false,
    },
    {
      unit_slug: 'u2',
      title: 'Fractions & Decimals',
      description: 'The number system.',
      order: 2,
      ccss_cluster: '6.NS.1-4',
      teks_cluster: '6.2E / 6.3',
      status: 'in_progress',
      percent_complete: 40,
      lesson_count: 8,
      assigned: true,
    },
    {
      unit_slug: 'u3',
      title: 'Rational Numbers',
      description: 'Negatives and the line.',
      order: 3,
      ccss_cluster: null,
      teks_cluster: null,
      status: 'locked',
      percent_complete: 0,
      lesson_count: 7,
      assigned: false,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Units', () => {
  it('renders a card per unit with title, dual-standard codes, and status', async () => {
    mockUnits(LIST);
    render(<Units onOpenUnit={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText('Ratios & Rates')).toBeInTheDocument();
    expect(screen.getByText('Fractions & Decimals')).toBeInTheDocument();
    // CCSS · TEKS cluster surfaced in the learner view.
    expect(screen.getByText('6.RP.A · 6.4 / 6.5')).toBeInTheDocument();
    expect(screen.getByText('Locked')).toBeInTheDocument();
  });

  it('opens an unlocked unit on click', async () => {
    mockUnits(LIST);
    const onOpenUnit = vi.fn();
    render(<Units onOpenUnit={onOpenUnit} onFoundation={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /Ratios & Rates/ }));
    expect(onOpenUnit).toHaveBeenCalledWith('u1');
  });

  it('disables a locked unit and does not open it', async () => {
    mockUnits(LIST);
    const onOpenUnit = vi.fn();
    render(<Units onOpenUnit={onOpenUnit} onFoundation={vi.fn()} />);
    const locked = await screen.findByRole('button', { name: /Rational Numbers/ });
    expect(locked).toBeDisabled();
    fireEvent.click(locked);
    expect(onOpenUnit).not.toHaveBeenCalled();
  });

  it('surfaces the teacher-assigned-unit banner and opens it on tap', async () => {
    mockUnits(LIST);
    const onOpenUnit = vi.fn();
    render(<Units onOpenUnit={onOpenUnit} onFoundation={vi.fn()} />);
    const banner = await screen.findByRole('button', { name: /Your teacher set this/ });
    fireEvent.click(banner);
    expect(onOpenUnit).toHaveBeenCalledWith('u2');
  });

  it('shows no assigned banner when there is no assignment (demo learner)', async () => {
    mockUnits({ ...LIST, assigned_unit_slug: null });
    render(<Units onOpenUnit={vi.fn()} onFoundation={vi.fn()} />);
    await screen.findByText('Ratios & Rates');
    expect(screen.queryByText(/Your teacher set this/)).not.toBeInTheDocument();
  });

  it('shows an empty state when there are no units', async () => {
    mockUnits({ units: [], assigned_unit_slug: null });
    render(<Units onOpenUnit={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText(/No units yet/)).toBeInTheDocument();
  });

  it('drops to foundation work from the foundation affordance', async () => {
    mockUnits(LIST);
    const onFoundation = vi.fn();
    render(<Units onOpenUnit={vi.fn()} onFoundation={onFoundation} />);
    fireEvent.click(await screen.findByRole('button', { name: /foundation work/i }));
    expect(onFoundation).toHaveBeenCalled();
  });

  it('gates later units when the backend is ungated (fresh-student stopgap)', async () => {
    // Two units, both `available` (current ungated backend): unit 1 opens, unit 2 locks until unit 1
    // is complete. unit 1 has 0% so unit 2 must read as locked and ignore clicks.
    mockUnits({
      assigned_unit_slug: null,
      units: [
        { ...LIST.units![0], unit_slug: 'a', title: 'Alpha', order: 1, status: 'available', percent_complete: 0, assigned: false },
        { ...LIST.units![0], unit_slug: 'b', title: 'Beta', order: 2, status: 'available', percent_complete: 0, assigned: false },
      ],
    });
    const onOpenUnit = vi.fn();
    render(<Units onOpenUnit={onOpenUnit} onFoundation={vi.fn()} />);
    expect(await screen.findByText('Alpha')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Beta/ }));
    expect(onOpenUnit).not.toHaveBeenCalledWith('b');
    fireEvent.click(screen.getByRole('button', { name: /Alpha/ }));
    expect(onOpenUnit).toHaveBeenCalledWith('a');
  });
});
