import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { fractionToAnswer, SymbolicEditor, type FractionValue } from './SymbolicEditor';

describe('fractionToAnswer', () => {
  it('composes "n/d" when both parts are present', () => {
    expect(fractionToAnswer({ numerator: '7', denominator: '12' })).toBe('7/12');
  });

  it('returns "" when either part is empty (incomplete answer)', () => {
    expect(fractionToAnswer({ numerator: '7', denominator: '' })).toBe('');
    expect(fractionToAnswer({ numerator: '', denominator: '12' })).toBe('');
  });
});

describe('SymbolicEditor', () => {
  it('reports digit-only edits to the numerator and denominator', () => {
    const onChange = vi.fn();
    const value: FractionValue = { numerator: '', denominator: '' };
    render(<SymbolicEditor value={value} onChange={onChange} />);

    // Non-digits are stripped at the surface so a typo never reaches the verifier.
    fireEvent.change(screen.getByLabelText(/numerator/i), { target: { value: '7a' } });
    expect(onChange).toHaveBeenCalledWith({ numerator: '7', denominator: '' });

    fireEvent.change(screen.getByLabelText(/denominator/i), { target: { value: 'x12' } });
    expect(onChange).toHaveBeenCalledWith({ numerator: '', denominator: '12' });
  });
});
