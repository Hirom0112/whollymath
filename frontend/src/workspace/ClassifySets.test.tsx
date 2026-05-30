import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { answerToSelection, ClassifySets, selectionToAnswer } from './ClassifySets';

// ClassifySets is the number-set classification widget (KC_classify_number_sets, TEKS 6.2A). It is a
// controlled WorkspaceWidgetProps<string> built AHEAD of the backend classify-sets contract, so
// these tests drive it with mock props — no live backend, and the verifier (not this widget) decides
// membership/correctness (§8.2). They pin: the canonical-order helpers, render of the three nested
// regions + the stimulus number, toggle emitting the canonical string regardless of click order,
// multi-select + deselect, controlled rendering, keyboard toggle, and disabled.

describe('selectionToAnswer / answerToSelection', () => {
  it('emits selected set ids in canonical smallest->largest order', () => {
    expect(selectionToAnswer(new Set(['rational', 'whole', 'integer']))).toBe(
      'whole,integer,rational',
    );
    expect(selectionToAnswer(new Set(['rational', 'integer']))).toBe('integer,rational');
    expect(selectionToAnswer(new Set(['rational']))).toBe('rational');
    expect(selectionToAnswer(new Set())).toBe('');
  });

  it('parses an answer string back to the selected set (tolerant of whitespace + unknown tokens)', () => {
    expect(answerToSelection('integer,rational')).toEqual(new Set(['integer', 'rational']));
    expect(answerToSelection(' whole , integer ')).toEqual(new Set(['whole', 'integer']));
    expect(answerToSelection('integer,bogus')).toEqual(new Set(['integer']));
    expect(answerToSelection('')).toEqual(new Set());
  });
});

describe('ClassifySets', () => {
  it('renders the three nested regions and the stimulus number', () => {
    render(<ClassifySets value="" onChange={vi.fn()} number="-3" />);
    expect(screen.getByRole('checkbox', { name: /rational/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /integers/i })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /whole/i })).toBeInTheDocument();
    expect(screen.getByText('-3')).toBeInTheDocument();
  });

  it('selecting a region emits the canonical answer (order-independent of clicks)', () => {
    const onChange = vi.fn();
    const { rerender } = render(<ClassifySets value="" onChange={onChange} number="-3" />);

    // Click the OUTER set first…
    fireEvent.click(screen.getByRole('checkbox', { name: /rational/i }));
    expect(onChange).toHaveBeenLastCalledWith('rational');

    // …then the inner one; even though "integer" was clicked second, the answer is canonical order.
    rerender(<ClassifySets value="rational" onChange={onChange} number="-3" />);
    fireEvent.click(screen.getByRole('checkbox', { name: /integers/i }));
    expect(onChange).toHaveBeenLastCalledWith('integer,rational');
  });

  it('renders a controlled value as the checked regions', () => {
    render(<ClassifySets value="whole,integer,rational" onChange={vi.fn()} number="5" />);
    expect(screen.getByRole('checkbox', { name: /whole/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /integers/i })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: /rational/i })).toBeChecked();
  });

  it('deselects a region that is toggled off', () => {
    const onChange = vi.fn();
    render(<ClassifySets value="integer,rational" onChange={onChange} number="-3" />);
    fireEvent.click(screen.getByRole('checkbox', { name: /integers/i }));
    expect(onChange).toHaveBeenLastCalledWith('rational');
  });

  it('toggles via the keyboard (Space / Enter)', () => {
    const onChange = vi.fn();
    render(<ClassifySets value="" onChange={onChange} number="1/2" />);
    const rational = screen.getByRole('checkbox', { name: /rational/i });

    fireEvent.keyDown(rational, { key: ' ' });
    expect(onChange).toHaveBeenLastCalledWith('rational');
    fireEvent.keyDown(rational, { key: 'Enter' });
    // Still firing (the parent owns state; here value didn't change, so it re-adds → 'rational').
    expect(onChange).toHaveBeenLastCalledWith('rational');
  });

  it('does not toggle when disabled', () => {
    const onChange = vi.fn();
    render(<ClassifySets value="" onChange={onChange} number="-3" disabled />);
    const rational = screen.getByRole('checkbox', { name: /rational/i });
    fireEvent.click(rational);
    fireEvent.keyDown(rational, { key: ' ' });
    expect(onChange).not.toHaveBeenCalled();
    expect(rational).toHaveAttribute('tabindex', '-1');
  });
});
