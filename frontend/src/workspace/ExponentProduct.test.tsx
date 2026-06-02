import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ExponentProduct } from './ExponentProduct';

// ExponentProduct is DISPLAY-ONLY (like SetModelStimulus) — it draws base^exp as the expanded
// repeated multiplication and is NOT an answer input. These tests pin: it renders one factor term
// per exponent with the base value, reads the expansion in its aria-label, and never shows the
// evaluated power (no answer leak).

describe('ExponentProduct', () => {
  it('renders one factor term per exponent, each equal to the base', () => {
    const { container } = render(<ExponentProduct base={2} exponent={4} factors={[2, 2, 2, 2]} />);
    const factors = [...container.querySelectorAll<HTMLElement>('.wm-exp-term')].map((el) =>
      Number(el.dataset.factor),
    );
    expect(factors).toEqual([2, 2, 2, 2]);
  });

  it('shows the base and exponent of the power', () => {
    const { container } = render(<ExponentProduct base={3} exponent={4} factors={[3, 3, 3, 3]} />);
    expect(container.querySelector('.wm-exp-base')?.textContent).toBe('3');
    expect(container.querySelector('.wm-exp-exponent')?.textContent).toBe('4');
  });

  it('reads the repeated multiplication in its accessible label', () => {
    render(<ExponentProduct base={2} exponent={4} factors={[2, 2, 2, 2]} />);
    expect(
      screen.getByRole('img', { name: /2 to the 4 means 2 times 2 times 2 times 2/i }),
    ).toBeInTheDocument();
  });

  it('shows the expanded input form only — never the evaluated power', () => {
    const { container } = render(<ExponentProduct base={2} exponent={4} factors={[2, 2, 2, 2]} />);
    // 2^4 = 16; the value must not appear anywhere in the rendered text.
    expect(container.textContent ?? '').not.toContain('16');
    // No element is marked as the evaluated result.
    expect(container.querySelector('[data-value]')).toBeNull();
    expect(container.querySelector('.wm-exp-value')).toBeNull();
  });
});
