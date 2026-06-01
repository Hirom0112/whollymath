import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { UnitDetailView, UnitListView } from './api';
import { App, AppRoutes } from './App';
import { SessionProvider } from './state/SessionContext';

// Routing tests for the react-router migration. These assert the route table resolves the right
// page for each URL (including deep links and the unknown-path redirect), the click-through nav
// changes the rendered page, and the legacy ?teacher=1 entry point still reaches the teacher
// surface. Pages stay pure (their prop interfaces are unchanged), so we mock the api layer the
// data-fetching pages use — the same `fetch`-stub approach as Units.test.tsx / Unit.test.tsx.

const UNITS: UnitListView = {
  assigned_unit_slug: null,
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
  ],
};

const UNIT_DETAIL: UnitDetailView = {
  unit_slug: 'u1',
  title: 'Ratios & Rates',
  description: 'Compare quantities.',
  order: 1,
  ccss_cluster: '6.RP.A',
  teks_cluster: '6.4 / 6.5',
  status: 'available',
  percent_complete: 0,
  lesson_count: 0,
  assigned: false,
  lessons: [],
};

// Route the stubbed fetch by URL so /units and /unit/:slug both resolve to the right fixture.
function okJson(data: unknown): Response {
  return { ok: true, status: 200, json: () => Promise.resolve(data) } as Response;
}

function stubFetchByPath(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.startsWith('/unit/')) return Promise.resolve(okJson(UNIT_DETAIL));
      if (url.startsWith('/units')) return Promise.resolve(okJson(UNITS));
      return Promise.resolve(okJson({}));
    }),
  );
}

function renderAt(path: string): void {
  stubFetchByPath();
  render(
    <SessionProvider proactive={false}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </SessionProvider>,
  );
}

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('App routing', () => {
  it('clicks through Landing → SignIn → Units, changing the rendered page', async () => {
    vi.useFakeTimers();
    stubFetchByPath();
    // The real App supplies its own BrowserRouter; drive the animated CTAs with fake timers.
    render(<App />);

    expect(
      screen.getByRole('button', { name: /start learning as a student/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /start learning as a student/i }));
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // Now on /signin.
    expect(screen.getByRole('button', { name: /student demo free/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /student demo free/i }));
    await act(async () => {
      await vi.runAllTimersAsync();
    });

    // The roll-out is done and we've navigated to /units; hand back real timers so waitFor can poll
    // for the units fetch (a microtask-resolved promise) to settle and render the headline.
    vi.useRealTimers();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your units/i })).toBeInTheDocument();
    });
  });

  it('visiting /units directly renders the Units page', async () => {
    renderAt('/units');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /your units/i })).toBeInTheDocument();
    });
  });

  it('visiting /unit/u1 renders the Unit page for slug u1', async () => {
    renderAt('/unit/u1');
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /ratios & rates/i })).toBeInTheDocument();
    });
  });

  it('an unknown path redirects to the Landing page', () => {
    renderAt('/does-not-exist');
    expect(
      screen.getByRole('button', { name: /start learning as a student/i }),
    ).toBeInTheDocument();
  });

  it('the legacy ?teacher=1 entry point resolves to the teacher surface', async () => {
    renderAt('/?teacher=1');
    // The redirect lands on /teacher (TeacherApp), which signs in the demo teacher and loads the
    // roster. We assert we left the landing — the student CTA is gone.
    await waitFor(() => {
      expect(
        screen.queryByRole('button', { name: /start learning as a student/i }),
      ).not.toBeInTheDocument();
    });
  });
});
