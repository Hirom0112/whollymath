import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PiMenu, type PiMenuItem } from './PiMenu';

// State-policy tests for Pi's nav menu (CLAUDE.md §2: the open/close/select policy is the
// testable part; the mascot's look is checked visually). We assert the popover toggles, an
// item runs its action and closes, Escape and click-outside close, the trigger reports
// aria-expanded, and an empty item list renders nothing (so a page never shows a dead trigger).

function items(onSelect = vi.fn()): PiMenuItem[] {
  return [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard', onSelect },
    { id: 'homework', label: 'Homework', icon: 'homework', onSelect: vi.fn() },
  ];
}

describe('PiMenu', () => {
  it('renders nothing when there are no items', () => {
    const { container } = render(<PiMenu items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('the trigger is a button with aria-haspopup and toggles aria-expanded', () => {
    render(<PiMenu items={items()} />);
    const trigger = screen.getByRole('button', { name: /open the menu/i });
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('menu')).toBeInTheDocument();

    fireEvent.click(trigger);
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('choosing an item runs its action and closes the menu', () => {
    const onSelect = vi.fn();
    render(<PiMenu items={items(onSelect)} />);
    fireEvent.click(screen.getByRole('button', { name: /open the menu/i }));

    fireEvent.click(screen.getByRole('menuitem', { name: /dashboard/i }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('Escape closes the menu', () => {
    render(<PiMenu items={items()} />);
    fireEvent.click(screen.getByRole('button', { name: /open the menu/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('a click outside closes the menu', () => {
    render(
      <div>
        <PiMenu items={items()} />
        <button type="button">elsewhere</button>
      </div>,
    );
    fireEvent.click(screen.getByRole('button', { name: /open the menu/i }));
    expect(screen.getByRole('menu')).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole('button', { name: /elsewhere/i }));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('reports open/closed to onOpenChange (mutual exclusivity hook)', () => {
    const onOpenChange = vi.fn();
    render(<PiMenu items={items()} onOpenChange={onOpenChange} />);
    fireEvent.click(screen.getByRole('button', { name: /open the menu/i }));
    expect(onOpenChange).toHaveBeenLastCalledWith(true);

    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });
});
