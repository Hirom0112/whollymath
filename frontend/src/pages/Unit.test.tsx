import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { UnitDetailView } from '../api';

import { Unit } from './Unit';

// Pins the unit-detail page's contract with GET /unit/{slug} (src/api). `fetch` is stubbed so the
// test stays a pure component test (CLAUDE.md §9), like Tutor.test.tsx.

function okJson(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}
function notFound(): Response {
  return { ok: false, status: 404, json: () => Promise.resolve({}) } as Response;
}

function mockUnit(data: UnitDetailView): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(okJson(data))),
  );
}

const DETAIL: UnitDetailView = {
  unit_slug: 'u1',
  title: 'Ratios & Rates',
  description: 'Compare quantities.',
  order: 1,
  ccss_cluster: '6.RP.A',
  teks_cluster: '6.4 / 6.5',
  status: 'available',
  percent_complete: 0,
  lesson_count: 4,
  assigned: false,
  lessons: [
    {
      lesson_slug: 'u1_l1',
      title: 'Ratio language',
      kc_id: 'KC_equivalence', // backend reports playable → launches the Tutor
      ccss_code: '6.RP.1',
      teks_code: '6.4A',
      status: 'available',
      probability: null,
      playable: true,
    },
    {
      lesson_slug: 'u1_l2',
      title: 'Unit conversion',
      kc_id: 'KC_unbuilt', // backend reports playable=false (unbuilt KC) → "coming soon"
      ccss_code: '6.RP.3d',
      teks_code: '6.4H',
      status: 'available',
      probability: null,
      playable: false,
    },
    {
      lesson_slug: 'u1_l3',
      title: 'Percent',
      kc_id: 'KC_percent',
      ccss_code: '6.RP.3c',
      teks_code: '6.4E',
      status: 'locked',
      probability: null,
      playable: true,
    },
    {
      // A concept lesson (DEC.FINLIT): not built as a tutor lesson, so it must render the honest
      // "Concept lesson" state — NOT "coming soon" — and never start a session.
      lesson_slug: 'u1_l4',
      title: 'Paying for college',
      kc_id: 'KC_college_pay',
      ccss_code: null,
      teks_code: '6.14G',
      status: 'available',
      probability: null,
      playable: false,
      concept_only: true,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('Unit', () => {
  it('renders the unit header with title and dual-standard cluster', async () => {
    mockUnit(DETAIL);
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText('Ratios & Rates')).toBeInTheDocument();
    expect(screen.getByText('6.RP.A · 6.4 / 6.5')).toBeInTheDocument();
  });

  it('renders the unit lessons on the shared rail with their CCSS·TEKS codes', async () => {
    mockUnit(DETAIL);
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText('Ratio language')).toBeInTheDocument();
    expect(screen.getByText('Unit conversion')).toBeInTheDocument();
    expect(screen.getByText('6.RP.1 · 6.4A')).toBeInTheDocument();
  });

  it('launches the Tutor with the lesson KC when a built, unlocked lesson is clicked', async () => {
    mockUnit(DETAIL);
    const onStartLesson = vi.fn();
    render(
      <Unit slug="u1" onStartLesson={onStartLesson} onBack={vi.fn()} onFoundation={vi.fn()} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Ratio language/ }));
    expect(onStartLesson).toHaveBeenCalledWith('KC_equivalence');
  });

  it('shows a "coming soon" notice (not a dead click) for a lesson with no live KC', async () => {
    mockUnit(DETAIL);
    const onStartLesson = vi.fn();
    render(
      <Unit slug="u1" onStartLesson={onStartLesson} onBack={vi.fn()} onFoundation={vi.fn()} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Unit conversion/ }));
    expect(onStartLesson).not.toHaveBeenCalled();
    expect(await screen.findByText(/coming soon/)).toBeInTheDocument();
  });

  it('renders the honest concept-lesson state (not "coming soon") for a concept_only lesson', async () => {
    mockUnit(DETAIL);
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText('Paying for college')).toBeInTheDocument();
    // The honest "Concept lesson" badge is shown, and the row never claims "coming soon".
    expect(screen.getByText('Concept lesson')).toBeInTheDocument();
    expect(
      screen.getByText(/not a tutor lesson|not an interactive tutor lesson/i),
    ).toBeInTheDocument();
  });

  it('does NOT call onStartLesson when a concept_only lesson is clicked (no /session)', async () => {
    mockUnit(DETAIL);
    const onStartLesson = vi.fn();
    render(
      <Unit slug="u1" onStartLesson={onStartLesson} onBack={vi.fn()} onFoundation={vi.fn()} />,
    );
    fireEvent.click(await screen.findByRole('button', { name: /Paying for college/ }));
    expect(onStartLesson).not.toHaveBeenCalled();
    // It shows the honest concept note, NOT the "coming soon" copy.
    expect(await screen.findByText(/concept lesson — covered in the TEKS/i)).toBeInTheDocument();
    expect(screen.queryByText(/coming soon/)).not.toBeInTheDocument();
  });

  it('disables a locked lesson', async () => {
    mockUnit(DETAIL);
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={vi.fn()} />);
    const locked = await screen.findByRole('button', { name: /Percent/ });
    expect(locked).toBeDisabled();
  });

  it('surfaces a gentle message when the unit is not found (404)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(notFound())),
    );
    render(<Unit slug="nope" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={vi.fn()} />);
    expect(await screen.findByText(/couldn't find that unit/i)).toBeInTheDocument();
  });

  it('calls onBack from the back affordance', async () => {
    mockUnit(DETAIL);
    const onBack = vi.fn();
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={onBack} onFoundation={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: /All units/ }));
    expect(onBack).toHaveBeenCalled();
  });

  it('drops to foundation work via Pi', async () => {
    mockUnit(DETAIL);
    const onFoundation = vi.fn();
    render(<Unit slug="u1" onStartLesson={vi.fn()} onBack={vi.fn()} onFoundation={onFoundation} />);
    fireEvent.click(await screen.findByRole('button', { name: /foundation work/i }));
    expect(onFoundation).toHaveBeenCalled();
  });
});
