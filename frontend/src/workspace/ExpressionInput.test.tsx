import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ExpressionInput } from './ExpressionInput';

// ExpressionInput is the typed-algebra answer widget (Unit 4–5: write/evaluate/equivalent
// expressions). It is a controlled WorkspaceWidgetProps<string> input built AHEAD of the Wave-5
// backend expression KC, so these tests drive it with mock props — no live backend, and the SymPy
// verifier (not this widget) decides correctness (§8.2). They pin: it renders, accepts a typed
// expression, reports the controlled string, sanitizes to a SymPy-parseable set (but ALLOWS the
// letters a variable needs), the palette inserts the SymPy operators, and disabled is honored.

describe('ExpressionInput', () => {
  it('renders the field and the controlled value', () => {
    render(<ExpressionInput value="n + 5" onChange={vi.fn()} />);
    expect(screen.getByLabelText(/your expression/i)).toHaveValue('n + 5');
  });

  it('reports the typed expression as a controlled string (variables allowed)', () => {
    const onChange = vi.fn();
    render(<ExpressionInput value="" onChange={onChange} />);

    // A variable is the whole point — letters must pass through, unlike the numeric widgets.
    fireEvent.change(screen.getByLabelText(/your expression/i), { target: { value: '2*x - 3' } });
    expect(onChange).toHaveBeenCalledWith('2*x - 3');
  });

  it('sanitizes characters that can never appear in a SymPy-parseable expression', () => {
    const onChange = vi.fn();
    render(<ExpressionInput value="" onChange={onChange} />);

    // Stray punctuation/symbols are stripped at the surface so a typo never reaches the verifier;
    // the algebra characters (letters, digits, operators, parens, caret, dot) survive.
    fireEvent.change(screen.getByLabelText(/your expression/i), {
      target: { value: 'n + 5!@#; x^2/4' },
    });
    expect(onChange).toHaveBeenCalledWith('n + 5 x^2/4');
  });

  it('inserts the SymPy operator (not the kid-facing glyph) when a palette key is tapped', () => {
    const onChange = vi.fn();
    // The learner has typed "3n" and taps ×; the value gains a "*", not the "×" glyph, so what
    // ships parses while the button reads like math class.
    render(<ExpressionInput value="3n" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: /multiply/i }));
    expect(onChange).toHaveBeenCalledWith('3n*');
  });

  it('inserts a parenthesis pair from the palette', () => {
    const onChange = vi.fn();
    render(<ExpressionInput value="2" onChange={onChange} />);

    fireEvent.click(screen.getByRole('button', { name: /parentheses/i }));
    expect(onChange).toHaveBeenCalledWith('2()');
  });

  it('is read-only when disabled (no edits, no palette inserts)', () => {
    const onChange = vi.fn();
    render(<ExpressionInput value="n + 5" onChange={onChange} disabled />);

    expect(screen.getByLabelText(/your expression/i)).toBeDisabled();
    // A disabled palette button can't fire an insert.
    expect(screen.getByRole('button', { name: /multiply/i })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /multiply/i }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('shows the optional prompt above the field', () => {
    render(<ExpressionInput value="" onChange={vi.fn()} prompt="Write the expression" />);
    expect(screen.getByText(/write the expression/i)).toBeInTheDocument();
  });
});
