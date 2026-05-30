import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { inequalityToAnswer, InequalityInput } from './InequalityInput';

// InequalityInput is the one-variable inequality widget (Unit 4-5). It is a controlled
// WorkspaceWidgetProps<string> built AHEAD of the backend inequality contract, so these tests drive
// it with mock props — no live backend, and the SymPy verifier (not this widget) judges correctness
// (§8.2). They pin: the compose helper, render, pick-relation, type-number, the composed onChange
// string (ASCII <=/>=), controlled rendering of an existing value, negative boundary, sanitize,
// incomplete -> "", and disabled.

describe('inequalityToAnswer', () => {
  it('composes variable + ASCII relation + number', () => {
    expect(inequalityToAnswer('x', '>', '3')).toBe('x>3');
    expect(inequalityToAnswer('x', '<=', '-2')).toBe('x<=-2');
  });

  it('returns "" when the inequality is incomplete (no relation, or no/again "-" number)', () => {
    expect(inequalityToAnswer('x', null, '3')).toBe('');
    expect(inequalityToAnswer('x', '>', '')).toBe('');
    expect(inequalityToAnswer('x', '>', '-')).toBe('');
  });
});

describe('InequalityInput', () => {
  it('renders the variable chip and the four relations', () => {
    render(<InequalityInput value="" onChange={vi.fn()} />);
    expect(screen.getByLabelText(/variable x/i)).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^less than$/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /less than or equal to/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /^greater than$/i })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /greater than or equal to/i })).toBeInTheDocument();
  });

  it('composes the answer once a relation is picked AND a number is typed', () => {
    const onChange = vi.fn();
    const { rerender } = render(<InequalityInput value="" onChange={onChange} />);

    // Picking ">" alone has no number yet, so the answer is still incomplete ("").
    fireEvent.click(screen.getByRole('radio', { name: /^greater than$/i }));
    expect(onChange).toHaveBeenLastCalledWith('');

    // With the relation now in the value, typing 3 completes "x>3".
    rerender(<InequalityInput value="x>" onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/boundary number/i), { target: { value: '3' } });
    expect(onChange).toHaveBeenLastCalledWith('x>3');
  });

  it('uses the ASCII <= token for the ≤ button (kid sees the glyph, wire gets <=)', () => {
    const onChange = vi.fn();
    // A number is already present, so picking ≤ completes the inequality immediately.
    render(<InequalityInput value="x>5" onChange={onChange} />);
    fireEvent.click(screen.getByRole('radio', { name: /less than or equal to/i }));
    expect(onChange).toHaveBeenLastCalledWith('x<=5');
  });

  it('renders a controlled value: the matching relation reads selected and the number shows', () => {
    render(<InequalityInput value="x<=-2" onChange={vi.fn()} />);
    expect(screen.getByRole('radio', { name: /less than or equal to/i })).toBeChecked();
    expect(screen.getByLabelText(/boundary number/i)).toHaveValue('-2');
    // The two-char "<=" must not be misread as "<".
    expect(screen.getByRole('radio', { name: /^less than$/i })).not.toBeChecked();
  });

  it('allows a leading-minus negative boundary but strips stray characters', () => {
    const onChange = vi.fn();
    render(<InequalityInput value="x>" onChange={onChange} />);
    const field = screen.getByLabelText(/boundary number/i);

    fireEvent.change(field, { target: { value: '-2a' } });
    expect(onChange).toHaveBeenLastCalledWith('x>-2');
    // A minus is kept only at the front; interior minuses and extra dots are dropped.
    fireEvent.change(field, { target: { value: '3-4.5.6' } });
    expect(onChange).toHaveBeenLastCalledWith('x>34.56');
  });

  it('honors a non-default variable', () => {
    const onChange = vi.fn();
    render(<InequalityInput value="" onChange={onChange} variable="n" />);
    expect(screen.getByLabelText(/variable n/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: /^greater than$/i }));
    // No number yet -> incomplete.
    expect(onChange).toHaveBeenLastCalledWith('');
  });

  it('does not change when disabled', () => {
    const onChange = vi.fn();
    render(<InequalityInput value="x>3" onChange={onChange} disabled />);
    fireEvent.click(screen.getByRole('radio', { name: /less than or equal to/i }));
    fireEvent.change(screen.getByLabelText(/boundary number/i), { target: { value: '9' } });
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: /less than or equal to/i })).toBeDisabled();
  });

  it('shows the optional prompt', () => {
    render(<InequalityInput value="" onChange={vi.fn()} prompt="Write the inequality" />);
    expect(screen.getByText(/write the inequality/i)).toBeInTheDocument();
  });
});
