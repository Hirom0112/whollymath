import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { SparkCount } from './SparkCount';

describe('SparkCount', () => {
  it('renders the total as readable text', () => {
    render(<SparkCount total={45} />);
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText(/sparks/)).toBeInTheDocument();
  });

  it('shows the new total after re-rendering with a higher value', () => {
    const { rerender } = render(<SparkCount total={45} />);
    expect(screen.getByText('45')).toBeInTheDocument();

    rerender(<SparkCount total={48} />);
    expect(screen.getByText('48')).toBeInTheDocument();
    expect(screen.queryByText('45')).not.toBeInTheDocument();
  });

  it('exposes the count in a polite live region for announcement', () => {
    const { container } = render(<SparkCount total={3} />);
    const live = container.querySelector('[aria-live="polite"]');
    expect(live).not.toBeNull();
    expect(live?.textContent).toContain('3');
  });
});
