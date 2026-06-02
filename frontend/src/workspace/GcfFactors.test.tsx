import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { GcfFactors } from './GcfFactors';

// GcfFactors is DISPLAY-ONLY (like SetModelStimulus) — it draws the two given numbers and their
// factor lists for a GCF/LCM problem, and is NOT an answer input. These tests pin: it renders both
// numbers with their full factor lists, reads the data in its aria-label, frames gcf vs lcm, and
// never marks a single "the answer" factor.

function factorChips(container: HTMLElement, number: number): number[] {
  const row = container.querySelector<HTMLElement>(`.wm-gcf-row[data-number="${String(number)}"]`);
  return [...(row?.querySelectorAll<HTMLElement>('.wm-gcf-factor') ?? [])].map((el) =>
    Number(el.dataset.factor),
  );
}

describe('GcfFactors', () => {
  it('renders both given numbers with their full factor lists', () => {
    const { container } = render(
      <GcfFactors
        mode="gcf"
        first={12}
        second={18}
        first_factors={[1, 2, 3, 4, 6, 12]}
        second_factors={[1, 2, 3, 6, 9, 18]}
      />,
    );
    expect(factorChips(container, 12)).toEqual([1, 2, 3, 4, 6, 12]);
    expect(factorChips(container, 18)).toEqual([1, 2, 3, 6, 9, 18]);
  });

  it('reads the numbers and factors in its accessible label', () => {
    render(
      <GcfFactors
        mode="gcf"
        first={12}
        second={18}
        first_factors={[1, 2, 3, 4, 6, 12]}
        second_factors={[1, 2, 3, 6, 9, 18]}
      />,
    );
    expect(
      screen.getByRole('img', {
        name: /greatest common factor of 12 and 18.*factors of 12: 1, 2, 3, 4, 6, 12/i,
      }),
    ).toBeInTheDocument();
  });

  it('frames the view as common multiples for an LCM problem', () => {
    const { container } = render(
      <GcfFactors
        mode="lcm"
        first={4}
        second={6}
        first_factors={[1, 2, 4]}
        second_factors={[1, 2, 3, 6]}
      />,
    );
    expect(container.querySelector('.wm-gcf')?.getAttribute('data-mode')).toBe('lcm');
    expect(screen.getByText(/common multiples/i)).toBeInTheDocument();
  });

  it('shows the given factors only — no single factor is marked as the answer', () => {
    const { container } = render(
      <GcfFactors
        mode="gcf"
        first={12}
        second={18}
        first_factors={[1, 2, 3, 4, 6, 12]}
        second_factors={[1, 2, 3, 6, 9, 18]}
      />,
    );
    // No element carries an "answer"/"correct"/"gcf-result" marker class or attribute.
    expect(container.querySelector('[data-answer]')).toBeNull();
    expect(container.querySelector('.wm-gcf-answer')).toBeNull();
    // Both rows render the full input lists, not a single collapsed value.
    expect(factorChips(container, 12).length).toBeGreaterThan(1);
    expect(factorChips(container, 18).length).toBeGreaterThan(1);
  });
});
