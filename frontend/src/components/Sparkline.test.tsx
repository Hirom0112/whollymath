import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Sparkline } from './Sparkline';

describe('Sparkline', () => {
  it('renders an accessible svg with the given aria-label', () => {
    render(<Sparkline data={[1, 2, 3, 2, 4]} ariaLabel="Maya trend" />);
    const svg = screen.getByRole('img', { name: 'Maya trend' });
    expect(svg.tagName.toLowerCase()).toBe('svg');
  });

  it('draws a line and an area path for a multi-point series', () => {
    const { container } = render(<Sparkline data={[5, 3, 4, 1, 2]} />);
    expect(container.querySelector('.wm-spark-line')).not.toBeNull();
    expect(container.querySelector('.wm-spark-area')).not.toBeNull();
  });

  it('degrades gracefully on empty data (svg, no paths)', () => {
    const { container } = render(<Sparkline data={[]} ariaLabel="empty" />);
    expect(screen.getByRole('img', { name: 'empty' })).toBeInTheDocument();
    expect(container.querySelector('.wm-spark-line')).toBeNull();
    expect(container.querySelector('.wm-spark-area')).toBeNull();
  });

  it('renders a single dot (no line) for a one-point series', () => {
    const { container } = render(<Sparkline data={[7]} />);
    expect(container.querySelector('.wm-spark-line')).toBeNull();
    expect(container.querySelector('.wm-spark-dot')).not.toBeNull();
  });

  it('applies the tone token color so the mark follows the theme', () => {
    const { container } = render(<Sparkline data={[1, 2]} tone="red" />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('style')).toContain('--wm-mean-wrong');
  });

  it('falls back to a default aria-label when none is given', () => {
    render(<Sparkline data={[1, 2, 3]} />);
    expect(screen.getByRole('img', { name: 'trend' })).toBeInTheDocument();
  });
});
