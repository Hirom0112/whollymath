import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { assignUnitInDemo, demoStudent } from '../api/teacherDemo';

import { TeacherStudentView } from './TeacherStudentView';

// The student drill-in (TODO TCH.F3). These pin the spec's load-bearing order and the one
// write action: the ALERTS banner comes first, the named misconception is surfaced (the
// diagnostic teachers asked for), assigning a unit reflects immediately, and back navigates out.
// The live client calls GET/POST /teacher/student/* — fetch is stubbed against the demo data.

function jsonResponse(payload: unknown, ok = true, status = 200): Response {
  return { ok, status, json: () => Promise.resolve(payload) } as Response;
}

describe('TeacherStudentView', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string, init?: RequestInit) => {
        const assign = url.match(/^\/teacher\/student\/([^/]+)\/assign-unit$/);
        if (assign && init?.method === 'POST') {
          const unitId = (JSON.parse(String(init.body)) as { unit_id: string }).unit_id;
          const student = assignUnitInDemo(decodeURIComponent(assign[1]), unitId);
          return Promise.resolve(
            student ? jsonResponse({ student }) : jsonResponse({}, false, 404),
          );
        }
        const drill = url.match(/^\/teacher\/student\/([^/]+)$/);
        if (drill) {
          const student = demoStudent(decodeURIComponent(drill[1]));
          return Promise.resolve(student ? jsonResponse(student) : jsonResponse({}, false, 404));
        }
        return Promise.resolve(jsonResponse({}, false, 404));
      }),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the alerts banner before the rest of the sections', async () => {
    render(<TeacherStudentView studentId="stu-maya" onBack={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: /Maya R\./ });

    const regions = screen.getAllByRole('region');
    // The first aria-labelled region is the alerts banner (spec §1: "at the very top").
    expect(regions[0].getAttribute('aria-label')).toBe('Alerts');
  });

  it('surfaces the named misconception', async () => {
    render(<TeacherStudentView studentId="stu-maya" onBack={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: /Maya R\./ });

    // It appears in the alert, the misconception tag, and the detail; assert it surfaces at all.
    expect(screen.getAllByText(/natural-number bias/i).length).toBeGreaterThan(0);
  });

  it('assigning a unit reflects immediately as Assigned', async () => {
    render(<TeacherStudentView studentId="stu-noah" onBack={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: /Noah B\./ });

    const assignButtons = screen.getAllByRole('button', { name: /^assign$/i });
    fireEvent.click(assignButtons[0]);

    // The clicked row swaps the button for an "Assigned" confirmation.
    expect(await screen.findByText(/assigned/i)).toBeInTheDocument();
  });

  it('shows a 404-style message for a student not on the roster', async () => {
    render(<TeacherStudentView studentId="stu-nobody" onBack={vi.fn()} />);
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load this student/i);
  });

  it('back button calls onBack', async () => {
    const onBack = vi.fn();
    render(<TeacherStudentView studentId="stu-maya" onBack={onBack} />);
    await screen.findByRole('heading', { level: 1, name: /Maya R\./ });

    fireEvent.click(screen.getByRole('button', { name: /class/i }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('uses no em dash in rendered copy (impeccable copy law)', async () => {
    const { container } = render(<TeacherStudentView studentId="stu-maya" onBack={vi.fn()} />);
    await screen.findByRole('heading', { level: 1, name: /Maya R\./ });
    expect(container.textContent ?? '').not.toContain('—');
  });
});
