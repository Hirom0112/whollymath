import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { barToAnswer, FractionBar, type BarValue } from './FractionBar';

describe('barToAnswer', () => {
  it('composes "shaded/segments"', () => {
    expect(barToAnswer({ segments: 12, shaded: 7 })).toBe('7/12');
  });

  it('returns "" when nothing is shaded (incomplete)', () => {
    expect(barToAnswer({ segments: 4, shaded: 0 })).toBe('');
  });
});

describe('FractionBar', () => {
  it('shades up to the clicked part', () => {
    const onChange = vi.fn();
    const value: BarValue = { segments: 4, shaded: 0 };
    render(<FractionBar value={value} onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: /part 3 of 4/i }));
    expect(onChange).toHaveBeenCalledWith({ segments: 4, shaded: 3 });
  });

  it('unfills the current edge when clicked again', () => {
    const onChange = vi.fn();
    render(<FractionBar value={{ segments: 4, shaded: 3 }} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /part 3 of 4/i }));
    expect(onChange).toHaveBeenCalledWith({ segments: 4, shaded: 2 });
  });

  it('repartitions and clamps shaded to the new part count', () => {
    const onChange = vi.fn();
    render(<FractionBar value={{ segments: 4, shaded: 4 }} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /fewer parts/i }));
    expect(onChange).toHaveBeenCalledWith({ segments: 3, shaded: 3 });
  });

  it('adds a part with the more-parts stepper', () => {
    const onChange = vi.fn();
    render(<FractionBar value={{ segments: 2, shaded: 1 }} onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /more parts/i }));
    expect(onChange).toHaveBeenCalledWith({ segments: 3, shaded: 1 });
  });
});
