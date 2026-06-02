import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AreaChart } from './AreaChart';

describe('AreaChart', () => {
  it('renders an accessible svg with the given aria-label', () => {
    render(<AreaChart data={[3, 4, 6, 5, 7, 9]} ariaLabel="Skill-gap trend" />);
    const svg = screen.getByRole('img', { name: 'Skill-gap trend' });
    expect(svg.tagName.toLowerCase()).toBe('svg');
  });

  it('draws a gradient-filled area and a line for a multi-point series', () => {
    const { container } = render(<AreaChart data={[2, 5, 3, 8, 6]} />);
    const area = container.querySelector('.wm-areachart-area');
    expect(area).not.toBeNull();
    expect(area?.getAttribute('fill')).toMatch(/^url\(#wm-areachart-grad-/);
    expect(container.querySelector('.wm-areachart-line')).not.toBeNull();
    expect(container.querySelector('linearGradient')).not.toBeNull();
  });

  it('degrades gracefully on empty data (svg, no paths)', () => {
    const { container } = render(<AreaChart data={[]} ariaLabel="empty insights" />);
    expect(screen.getByRole('img', { name: 'empty insights' })).toBeInTheDocument();
    expect(container.querySelector('.wm-areachart-area')).toBeNull();
    expect(container.querySelector('.wm-areachart-line')).toBeNull();
  });

  it('renders a single dot (no line) for a one-point series', () => {
    const { container } = render(<AreaChart data={[5]} />);
    expect(container.querySelector('.wm-areachart-line')).toBeNull();
    expect(container.querySelector('.wm-areachart-dot')).not.toBeNull();
  });

  it('applies the tone token color so the chart follows the theme', () => {
    const { container } = render(<AreaChart data={[1, 2, 3]} tone="green" />);
    const svg = container.querySelector('svg');
    expect(svg?.getAttribute('style')).toContain('--wm-mean-correct');
  });
});
