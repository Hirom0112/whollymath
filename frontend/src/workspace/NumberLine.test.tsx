import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { clampTick, nearestTick, NumberLine } from './NumberLine';

// Default jsdom has no matchMedia; the widget reads it to honor prefers-reduced-motion. Install a
// stub the tests can flip between "no preference" and "reduce".
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

describe('nearestTick / clampTick', () => {
  it('rounds a ratio to the nearest tick', () => {
    expect(nearestTick(0.6, 5)).toBe(3); // 0.6 * 5 = 3.0
    expect(nearestTick(0.59, 5)).toBe(3); // rounds to 3
    expect(nearestTick(0.5, 4)).toBe(2);
  });

  it('clamps out-of-range placements to the ends', () => {
    expect(nearestTick(-0.2, 5)).toBe(0);
    expect(nearestTick(1.3, 5)).toBe(5);
    expect(clampTick(7, 5)).toBe(5);
    expect(clampTick(-1, 5)).toBe(0);
  });
});

describe('NumberLine', () => {
  it('moves the marker by one tick on arrow keys', () => {
    const onChange = vi.fn();
    render(<NumberLine segments={5} value={3} onChange={onChange} />);

    const marker = screen.getByRole('slider', { name: /number line marker/i });
    fireEvent.keyDown(marker, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith(4);

    fireEvent.keyDown(marker, { key: 'ArrowLeft' });
    expect(onChange).toHaveBeenCalledWith(2);
  });

  it('does not move past the ends', () => {
    const onChange = vi.fn();
    render(<NumberLine segments={5} value={5} onChange={onChange} />);
    fireEvent.keyDown(screen.getByRole('slider'), { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith(5); // clamped at the top
  });

  it('offers a start affordance before the first placement', () => {
    const onChange = vi.fn();
    render(<NumberLine segments={5} value={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /place your marker/i }));
    expect(onChange).toHaveBeenCalledWith(0);
  });
});

describe('NumberLine verdict reveal (Slice AR.1)', () => {
  beforeEach(() => {
    stubMatchMedia(false); // default: motion allowed
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('on a correct verdict draws the segment and animates the marker to the placed tick', () => {
    const { container } = render(
      <NumberLine segments={4} value={1} onChange={vi.fn()} disabled verdict="correct" />,
    );
    // (a) the 0→tick segment is rendered…
    const segment = container.querySelector('.wm-nl-segment');
    expect(segment).not.toBeNull();
    // …and (with motion allowed) the marker travels: the draw + travel classes are present.
    expect(container.querySelector('.wm-nl-segment--draw')).not.toBeNull();
    expect(container.querySelector('.wm-nl-pin--travel')).not.toBeNull();
  });

  it('on a wrong verdict reveals nothing — no segment, no snap to the answer', () => {
    const { container } = render(
      <NumberLine segments={4} value={3} onChange={vi.fn()} disabled verdict="incorrect" />,
    );
    expect(container.querySelector('.wm-nl-segment')).toBeNull();
    // The marker stays exactly where the learner left it (no correction applied).
    expect(screen.getByRole('slider')).toHaveAttribute('aria-valuenow', '3');
  });

  it('suppresses the animation under prefers-reduced-motion (final state shown instantly)', () => {
    stubMatchMedia(true); // reduce motion
    const { container } = render(
      <NumberLine segments={4} value={1} onChange={vi.fn()} disabled verdict="correct" />,
    );
    // The segment still renders (the final state), but the draw-on / travel animations are off.
    expect(container.querySelector('.wm-nl-segment')).not.toBeNull();
    expect(container.querySelector('.wm-nl-segment--draw')).toBeNull();
    expect(container.querySelector('.wm-nl-pin--travel')).toBeNull();
  });
});
