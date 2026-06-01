import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { CourseView } from '../api';

import { CourseMap } from './CourseMap';

// The foundation-work home renders ONLY the five terminal foundation fraction skills. /course
// returns the whole Grade-6 catalog, so the page filters on the backend-authoritative
// `is_foundation` flag — non-foundation nodes must never reach the rail. `fetch` is stubbed so this
// stays a pure component test (CLAUDE.md §9), the same approach as Units.test.tsx.

function okJson(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}

function mockCourse(data: CourseView): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(okJson(data))),
  );
}

// A MIXED catalog: two of the five foundation skills plus two non-foundation Grade-6 KCs, exactly
// the shape /course returns now (43 live nodes, only 5 flagged).
const MIXED: CourseView = {
  nodes: [
    {
      kc_id: 'KC_equivalence',
      skill_name: 'Identify equivalent fractions',
      description: 'Decide whether two fractions name the same amount.',
      status: 'available',
      prerequisites: [],
      probability: null,
      is_foundation: true,
    },
    {
      kc_id: 'KC_addition_unlike',
      skill_name: 'Add fractions with unlike denominators',
      description: 'Add two fractions whose denominators differ.',
      status: 'locked',
      prerequisites: ['KC_common_denominator'],
      probability: null,
      is_foundation: true,
    },
    {
      kc_id: 'KC_unit_rate',
      skill_name: 'Find a unit rate',
      description: 'Find how much for ONE.',
      status: 'locked',
      prerequisites: [],
      probability: null,
      is_foundation: false,
    },
    {
      kc_id: 'KC_exponents',
      skill_name: 'Evaluate an exponent',
      description: 'Evaluate a whole-number exponent.',
      status: 'locked',
      prerequisites: [],
      probability: null,
      is_foundation: false,
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('CourseMap', () => {
  it('renders only the foundation nodes from a mixed catalog', async () => {
    mockCourse(MIXED);
    render(<CourseMap onStartLesson={vi.fn()} />);

    // The two foundation skills appear…
    expect(await screen.findByText('Identify equivalent fractions')).toBeInTheDocument();
    expect(screen.getByText('Add fractions with unlike denominators')).toBeInTheDocument();

    // …and the non-foundation Grade-6 skills are filtered out (never rendered).
    expect(screen.queryByText('Find a unit rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Evaluate an exponent')).not.toBeInTheDocument();
  });

  it('shows an honest foundation-work headline (not the old full-path copy)', async () => {
    mockCourse(MIXED);
    render(<CourseMap onStartLesson={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /foundation work/i })).toBeInTheDocument();
    });
    expect(screen.queryByText('Your learning path')).not.toBeInTheDocument();
  });
});
