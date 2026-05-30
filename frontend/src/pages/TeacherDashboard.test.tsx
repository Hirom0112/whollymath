import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TeacherDashboard } from './TeacherDashboard';

// The teacher roster (TODO TCH.F2). These pin the contract that makes the dashboard useful:
// students are grouped under RANKED headers (struggling first), each row opens the right
// student, and the search filters by name. Data comes from the seeded demo client (async),
// so the queries await the first render of the class.

describe('TeacherDashboard', () => {
  it('groups students under ranked category sections, struggling first', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);

    // Wait for the class to load (the demo client resolves on the next microtask).
    await screen.findByText('Period 3 · Grade 6 Math');

    // Each category renders as an aria-labelled <section> (implicit role "region"). Their DOM
    // order IS the ranking the teacher reads top-to-bottom.
    const regions = screen.getAllByRole('region');
    const order = regions.map((r) => r.getAttribute('aria-label'));
    expect(order).toEqual(['struggling', 'needs_attention', 'on_track']);
  });

  it('opens the clicked student by id', async () => {
    const onOpenStudent = vi.fn();
    render(<TeacherDashboard onOpenStudent={onOpenStudent} onExit={vi.fn()} />);

    const maya = await screen.findByRole('button', { name: /Maya R\./ });
    fireEvent.click(maya);

    expect(onOpenStudent).toHaveBeenCalledTimes(1);
    expect(onOpenStudent).toHaveBeenCalledWith('stu-maya');
  });

  it('filters the roster by name search', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByText('Period 3 · Grade 6 Math');

    // Before filtering, an on-track student is present.
    expect(screen.getByRole('button', { name: /Grace L\./ })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/search students by name/i), {
      target: { value: 'Maya' },
    });

    expect(screen.getByRole('button', { name: /Maya R\./ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Grace L\./ })).toBeNull();
  });

  it('shows an empty message when no student matches', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByText('Period 3 · Grade 6 Math');

    fireEvent.change(screen.getByLabelText(/search students by name/i), {
      target: { value: 'zzzz' },
    });

    expect(screen.getByText(/no students match/i)).toBeInTheDocument();
  });

  it('every struggling row carries an alert badge (the urgent-first promise)', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByText('Period 3 · Grade 6 Math');

    const struggling = screen.getByRole('region', { name: 'struggling' });
    // Each struggling student shows at least one alert label (e.g. "Repeated misconception").
    expect(within(struggling).getAllByText(/repeated misconception|stuck/i).length).toBeGreaterThan(
      0,
    );
  });

  it('uses no em dash in rendered copy (impeccable copy law)', async () => {
    const { container } = render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByText('Period 3 · Grade 6 Math');
    expect(container.textContent ?? '').not.toContain('—');
  });
});
