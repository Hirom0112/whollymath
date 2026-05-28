import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { clampTick, nearestTick, NumberLine } from './NumberLine';

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
