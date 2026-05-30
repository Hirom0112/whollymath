import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LearningPathRail, type PathNode } from './LearningPathRail';

const NODES: PathNode[] = [
  {
    id: 'a',
    title: 'Equivalent fractions',
    description: 'Spot fractions that name the same amount.',
    status: 'mastered',
    tint: 'mint',
    progressPct: 100,
  },
  {
    id: 'b',
    title: 'Add fractions',
    description: 'Add with unlike denominators.',
    status: 'available',
    tint: 'warm',
    progressPct: 40,
  },
  {
    id: 'c',
    title: 'Subtract fractions',
    description: 'Locked until the earlier rows are done.',
    status: 'locked',
    tint: 'lavender',
    progressPct: null,
  },
];

describe('LearningPathRail', () => {
  it('renders a row per node with its title, description, and status label', () => {
    render(<LearningPathRail nodes={NODES} onSelect={vi.fn()} />);
    expect(screen.getByText('Equivalent fractions')).toBeInTheDocument();
    expect(screen.getByText('Add fractions')).toBeInTheDocument();
    expect(screen.getByText('Mastered')).toBeInTheDocument();
    expect(screen.getByText('Ready to start')).toBeInTheDocument();
    expect(screen.getByText('Locked')).toBeInTheDocument();
  });

  it('numbers unmastered rows by position and marks mastered rows with a check', () => {
    render(<LearningPathRail nodes={NODES} onSelect={vi.fn()} />);
    // First row is mastered → check, not "1".
    expect(screen.getByText('✓')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('calls onSelect with the node id when an unlocked row is clicked', () => {
    const onSelect = vi.fn();
    render(<LearningPathRail nodes={NODES} onSelect={onSelect} />);
    screen.getByText('Add fractions').closest('button')?.click();
    expect(onSelect).toHaveBeenCalledWith('b');
  });

  it('disables a locked row and does not fire onSelect for it', () => {
    const onSelect = vi.fn();
    render(<LearningPathRail nodes={NODES} onSelect={onSelect} />);
    const locked = screen.getByText('Subtract fractions').closest('button');
    expect(locked).toBeDisabled();
    locked?.click();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('shows the provided locked CTA so a host can say "lessons" instead of "skills"', () => {
    render(
      <LearningPathRail
        nodes={NODES}
        onSelect={vi.fn()}
        lockedCta="Finish the earlier lessons to unlock"
      />,
    );
    expect(screen.getByText('Finish the earlier lessons to unlock')).toBeInTheDocument();
  });
});
