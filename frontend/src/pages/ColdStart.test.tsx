import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ColdStart, type RouteKey } from './ColdStart';

// The cold-start screen is the first product surface (Turn 0, PROJECT.md 0.D.2).
// These tests pin the contract the tutor relies on: a kid-friendly headline, the
// three equal-weight KC options + the de-emphasized "I'm not sure" default, each
// reporting back the correct RouteKey so backend session.from_route routes right.
describe('ColdStart', () => {
  it('renders the headline and four option buttons', () => {
    render(<ColdStart onChoose={vi.fn()} />);

    expect(
      screen.getByRole('heading', { level: 1, name: /what do you want to work on\?/i }),
    ).toBeInTheDocument();

    // Three KC options + one "I'm not sure" default = four buttons.
    expect(screen.getAllByRole('button')).toHaveLength(4);
  });

  it.each<readonly [RouteKey, RegExp]>([
    ['combine', /putting two fraction pieces together/i],
    ['same_amount', /telling when two different-looking fractions/i],
    ['where_on_line', /finding where a fraction sits on a line/i],
  ])('clicking the %s option calls onChoose with that key', (key, prompt) => {
    const onChoose = vi.fn();
    render(<ColdStart onChoose={onChoose} />);

    fireEvent.click(screen.getByRole('button', { name: prompt }));

    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith(key);
  });

  it('renders the de-emphasized "not sure" option and reports it as not_sure', () => {
    const onChoose = vi.fn();
    render(<ColdStart onChoose={onChoose} />);

    const unsure = screen.getByRole('button', { name: /i'm not sure, just show me something/i });
    expect(unsure).toBeInTheDocument();
    // Lives outside the KC list (which is a <ul>); the visual de-emphasis is
    // class-based, but at the structural level the unsure button is NOT a list
    // item alongside the three KC cards.
    expect(unsure.closest('ul')).toBeNull();

    fireEvent.click(unsure);
    expect(onChoose).toHaveBeenCalledTimes(1);
    expect(onChoose).toHaveBeenCalledWith('not_sure');
  });

  it('uses no em dash in the unsure copy (impeccable copy law)', () => {
    render(<ColdStart onChoose={vi.fn()} />);
    const unsure = screen.getByRole('button', { name: /i'm not sure/i });
    expect(unsure.textContent ?? '').not.toContain('—');
  });
});
