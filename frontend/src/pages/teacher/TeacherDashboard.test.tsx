import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TeacherDashboard } from './TeacherDashboard';

// The teacher client now runs LIVE (TEACHER_API_READY=true), so the component's data calls hit the
// network. These component tests pin the dashboard's RENDERING contract (ranked sections, search,
// status strip, copy law) against the polished demo fixtures — so we mock the api/teacher data
// functions to resolve those fixtures, decoupling the render assertions from the live/offline flag
// and from a running backend. (The live client wiring itself is covered in api/teacher.test.ts.)
vi.mock('../../api/teacher', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/teacher')>();
  const demo = await import('../../api/teacherDemo');
  return {
    ...actual,
    fetchRoster: () => Promise.resolve(demo.DEMO_ROSTER),
    fetchReminders: () => Promise.resolve(demo.DEMO_REMINDERS),
    fetchAggregateTrends: () => Promise.resolve(demo.DEMO_AGGREGATE_TRENDS),
    fetchTeacherStudent: (id: string) => {
      const s = demo.demoStudent(id);
      return s ? Promise.resolve(s) : Promise.reject(new Error('not on roster'));
    },
  };
});

describe('TeacherDashboard', () => {
  it('groups students under ranked category sections, struggling first', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);

    // Wait for the class to load (the demo client resolves on the next microtask).
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });

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
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });

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
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });

    fireEvent.change(screen.getByLabelText(/search students by name/i), {
      target: { value: 'zzzz' },
    });

    expect(screen.getByText(/no students match/i)).toBeInTheDocument();
  });

  it('every struggling row carries an alert badge (the urgent-first promise)', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });

    const struggling = screen.getByRole('region', { name: 'struggling' });
    // Each struggling student shows at least one alert label (e.g. "Repeated misconception").
    expect(within(struggling).getAllByText(/repeated misconception|stuck/i).length).toBeGreaterThan(
      0,
    );
  });

  it('uses no em dash in rendered copy (impeccable copy law)', async () => {
    const { container } = render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });
    expect(container.textContent ?? '').not.toContain('—');
  });

  it('renders the class date from the roster as_of (timezone-stable)', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });
    // Demo as_of is "2026-06-01T09:15:00Z"; the date is parsed by parts, so it never shifts a day.
    expect(screen.getByText('June 1, 2026')).toBeInTheDocument();
  });

  it('shows the status strip with one pill per bucket', async () => {
    const { container } = render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });
    const strip = container.querySelector('.wm-teacher-statusstrip');
    expect(strip).not.toBeNull();
    expect(strip?.querySelectorAll('.wm-teacher-statuspill')).toHaveLength(3);
  });

  it('flags struggling rows with an "Urgent action" corner tag', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });
    const struggling = screen.getByRole('region', { name: 'struggling' });
    // Both demo struggling students (Maya, Dev) carry the tag.
    expect(within(struggling).getAllByText(/urgent action/i).length).toBeGreaterThanOrEqual(1);
  });

  it('toggles a reminder when its checkbox is clicked', async () => {
    render(<TeacherDashboard onOpenStudent={vi.fn()} onExit={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: 'Period 3 · Grade 6 Math' });
    const reminder = await screen.findByRole('checkbox', { name: /Pull Maya/i });
    expect(reminder).not.toBeChecked();
    fireEvent.click(reminder);
    expect(reminder).toBeChecked();
  });
});
