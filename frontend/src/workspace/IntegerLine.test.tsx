import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { IntegerLine } from './IntegerLine';

// IntegerLine is DISPLAY-ONLY (like SetModelStimulus): it draws the integer number line a problem
// in the integer-arithmetic family names, and is NOT an answer input. These tests pin, per KC: the
// right marks/jumps/spans are drawn from the INPUTS, the axis ticks (including 0) render, the
// aria-label reads the scene, and NO answer (sum / |x| / opposite) is shown anywhere.

/** Collect the integer tick values rendered (via the data-tick hook). */
function tickValues(container: HTMLElement): number[] {
  return [...container.querySelectorAll<SVGGElement>('g[data-tick]')].map((g) =>
    Number(g.dataset.tick),
  );
}

describe('IntegerLine', () => {
  it('draws ticks across the whole axis including a zero tick', () => {
    const { container } = render(
      <IntegerLine kind="signed_point" axis_min={-4} axis_max={4} points={[-3]} />,
    );
    const ticks = tickValues(container);
    expect(ticks).toEqual([-4, -3, -2, -1, 0, 1, 2, 3, 4]);
    expect(container.querySelector('.wm-intline-tick-zero')).not.toBeNull();
  });

  describe('add/subtract jump', () => {
    it('marks the start and draws a jump of the second operand, without labelling the sum', () => {
      // 5 + (-3): start at 5, jump -3. The sum (2) must NOT appear as a point label.
      const { container } = render(
        <IntegerLine kind="integer_jump" axis_min={-1} axis_max={6} start={5} delta={-3} />,
      );
      const jump = container.querySelector('g[data-start]');
      expect(jump?.getAttribute('data-start')).toBe('5');
      expect(jump?.getAttribute('data-delta')).toBe('-3');
      // The arrow is drawn.
      expect(container.querySelector('.wm-intline-arrow')).not.toBeNull();
      // The only labelled point is the start (5); the landing (2) is never labelled (no answer leak).
      const labels = [...container.querySelectorAll('.wm-intline-point-label')].map(
        (t) => t.textContent,
      );
      expect(labels).toEqual(['5']);
      expect(labels).not.toContain('2');
    });

    it('reads the jump direction and magnitude in its accessible label', () => {
      render(<IntegerLine kind="integer_jump" axis_min={-1} axis_max={6} start={5} delta={-3} />);
      expect(
        screen.getByRole('img', { name: /point at 5 with an arrow jumping 3 left/i }),
      ).toBeInTheDocument();
    });
  });

  describe('absolute value', () => {
    it('marks the point and draws its distance span to zero, without labelling the distance', () => {
      // |-7|: mark -7, show span to 0. The distance (7) must NOT appear as a label.
      const { container } = render(
        <IntegerLine kind="absolute_value" axis_min={-8} axis_max={1} point={-7} />,
      );
      expect(container.querySelector('g[data-point]')?.getAttribute('data-point')).toBe('-7');
      expect(container.querySelector('.wm-intline-span')).not.toBeNull();
      const labels = [...container.querySelectorAll('.wm-intline-point-label')].map(
        (t) => t.textContent,
      );
      expect(labels).toEqual(['-7']);
      expect(labels).not.toContain('7'); // the answer |−7| = 7 is never shown
    });

    it('reads the point and its distance to zero in its accessible label', () => {
      render(<IntegerLine kind="absolute_value" axis_min={-8} axis_max={1} point={-7} />);
      expect(
        screen.getByRole('img', { name: /point at -7 and its distance to zero/i }),
      ).toBeInTheDocument();
    });
  });

  describe('signed point', () => {
    it('marks the given integer and not its opposite', () => {
      // "opposite of -6": mark -6. The opposite (6) is the answer and must NOT be marked.
      const { container } = render(
        <IntegerLine kind="signed_point" axis_min={-7} axis_max={7} points={[-6]} />,
      );
      const points = [...container.querySelectorAll<SVGGElement>('g[data-point]')].map(
        (g) => g.dataset.point,
      );
      expect(points).toEqual(['-6']);
      const labels = [...container.querySelectorAll('.wm-intline-point-label')].map(
        (t) => t.textContent,
      );
      expect(labels).toEqual(['-6']);
      expect(labels).not.toContain('6'); // the opposite (answer) is never marked
    });
  });
});
