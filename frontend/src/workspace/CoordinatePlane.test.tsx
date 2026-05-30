import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { answerToPoints, CoordinatePlane, pointsToAnswer } from './CoordinatePlane';

// CoordinatePlane is the four-quadrant plotter (6.NS.8 / 6.EE.9 / 6.G.3). It is a controlled
// WorkspaceWidgetProps<string> SVG widget built AHEAD of the backend coordinate-plane contract, so
// these tests drive it with mock props — no live backend, and the verifier (not this widget) judges
// correctness (§8.2). They pin: the pure point<->string helpers, render, keyboard placement, the
// maxPoints cap + toggle, controlled rendering of an existing value, disabled, and reduced motion.

// jsdom has no matchMedia; the widget reads it to honor prefers-reduced-motion (NumberLine pattern).
function stubMatchMedia(reduced: boolean): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduced && query.includes('reduce'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

beforeEach(() => {
  stubMatchMedia(false); // default: motion allowed
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe('pointsToAnswer / answerToPoints', () => {
  it('renders a single point to its no-space wire token', () => {
    expect(pointsToAnswer([{ x: 2, y: -1 }])).toBe('(2,-1)');
  });

  it('joins a polygon as a comma-separated point list', () => {
    expect(
      pointsToAnswer([
        { x: 0, y: 0 },
        { x: 3, y: 0 },
        { x: 3, y: 2 },
      ]),
    ).toBe('(0,0),(3,0),(3,2)');
  });

  it('round-trips through the parser (tolerant of whitespace)', () => {
    expect(answerToPoints('(2,-1)')).toEqual([{ x: 2, y: -1 }]);
    expect(answerToPoints(' (0, 0) , (3 , 2) ')).toEqual([
      { x: 0, y: 0 },
      { x: 3, y: 2 },
    ]);
  });

  it('drops a malformed token instead of crashing', () => {
    expect(answerToPoints('(1,2),(garbage),(3,4)')).toEqual([
      { x: 1, y: 2 },
      { x: 3, y: 4 },
    ]);
    expect(answerToPoints('')).toEqual([]);
  });
});

describe('CoordinatePlane', () => {
  it('renders the grid and the empty-state prompt', () => {
    render(<CoordinatePlane value="" onChange={vi.fn()} />);
    expect(screen.getByRole('application', { name: /coordinate plane/i })).toBeInTheDocument();
    expect(screen.getByText(/tap the grid to place your point/i)).toBeInTheDocument();
  });

  it('renders a controlled value as a placed point + its readout', () => {
    render(<CoordinatePlane value="(2,-1)" onChange={vi.fn()} />);
    expect(screen.getByText(/placed: \(2,-1\)/i)).toBeInTheDocument();
  });

  it('places a point at the keyboard cursor and emits the string', () => {
    const onChange = vi.fn();
    render(<CoordinatePlane value="" onChange={onChange} />);
    const grid = screen.getByRole('application', { name: /coordinate plane/i });

    // Cursor starts at the origin; arrow it to (2,-1), then Enter to place.
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    fireEvent.keyDown(grid, { key: 'ArrowDown' });
    fireEvent.keyDown(grid, { key: 'Enter' });

    expect(onChange).toHaveBeenLastCalledWith('(2,-1)');
  });

  it('clamps the cursor at the axis bounds', () => {
    const onChange = vi.fn();
    render(<CoordinatePlane value="" onChange={onChange} min={-2} max={2} />);
    const grid = screen.getByRole('application');

    // Three rights from origin on a [-2,2] axis stops at x=2 (clamped), not 3.
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    fireEvent.keyDown(grid, { key: 'ArrowRight' });
    fireEvent.keyDown(grid, { key: ' ' });

    expect(onChange).toHaveBeenLastCalledWith('(2,0)');
  });

  it('appends additional vertices up to maxPoints (polygon)', () => {
    const onChange = vi.fn();
    // Already has two vertices; placing a third at the cursor (origin) appends it.
    render(<CoordinatePlane value="(3,0),(3,2)" onChange={onChange} maxPoints={3} />);
    fireEvent.keyDown(screen.getByRole('application'), { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('(3,0),(3,2),(0,0)');
  });

  it('rolls the oldest point off when placing past the cap (single-point default)', () => {
    const onChange = vi.fn();
    // maxPoints defaults to 1; one point already placed. Placing a new one at the cursor (origin)
    // evicts the old one (FIFO) so a single-point item is always re-placeable.
    render(<CoordinatePlane value="(5,5)" onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole('application'), { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('(0,0)');
  });

  it('toggles a point off when it is placed again (undo a misplacement)', () => {
    const onChange = vi.fn();
    // Cursor at origin; the origin is already placed → Enter removes it.
    render(<CoordinatePlane value="(0,0)" onChange={onChange} maxPoints={3} />);
    fireEvent.keyDown(screen.getByRole('application'), { key: 'Enter' });
    expect(onChange).toHaveBeenLastCalledWith('');
  });

  it('does not place when disabled', () => {
    const onChange = vi.fn();
    render(<CoordinatePlane value="" onChange={onChange} disabled />);
    const grid = screen.getByRole('application');
    fireEvent.keyDown(grid, { key: 'Enter' });
    expect(onChange).not.toHaveBeenCalled();
    expect(grid).toHaveAttribute('tabindex', '-1');
  });

  it('suppresses the place "pop" under prefers-reduced-motion', () => {
    stubMatchMedia(true);
    const { container } = render(<CoordinatePlane value="(1,1)" onChange={vi.fn()} />);
    // The point still renders; the pop animation class is withheld.
    expect(container.querySelector('.wm-coord-point')).not.toBeNull();
    expect(container.querySelector('.wm-coord-point--pop')).toBeNull();
  });
});
