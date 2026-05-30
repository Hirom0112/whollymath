import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { describeFigure, FigureStimulus, type FigureSpec } from './FigureStimulus';

// FigureStimulus is a DISPLAY-ONLY geometry figure for the Unit-6 area/volume problem statements —
// not a WorkspaceWidget answer input (geometry answers stay numeric via NumberEntry). So there is no
// onChange/value to drive; these tests pin the screen-reader description, the role="img" label, and
// that each shape renders its figure + dimension labels.

describe('describeFigure', () => {
  it('describes each shape with its measurements in reading order', () => {
    expect(describeFigure({ shape: 'rectangle', labels: { base: '8 cm', height: '3 cm' } })).toBe(
      'Rectangle, base 8 cm, height 3 cm',
    );
    expect(describeFigure({ shape: 'triangle', labels: { base: '10 in', height: '4 in' } })).toBe(
      'Triangle, base 10 in, height 4 in',
    );
    expect(describeFigure({ shape: 'parallelogram', labels: { base: '6 m', height: '5 m' } })).toBe(
      'Parallelogram, base 6 m, height 5 m',
    );
    expect(
      describeFigure({
        shape: 'prism',
        labels: { length: '5 cm', width: '2 cm', height: '3 cm' },
      }),
    ).toBe('Right rectangular prism, length 5 cm, width 2 cm, height 3 cm');
  });
});

describe('FigureStimulus', () => {
  it('renders as a labeled image describing the figure for screen readers', () => {
    const spec: FigureSpec = { shape: 'rectangle', labels: { base: '8 cm', height: '3 cm' } };
    render(<FigureStimulus spec={spec} />);
    expect(
      screen.getByRole('img', { name: /rectangle, base 8 cm, height 3 cm/i }),
    ).toBeInTheDocument();
  });

  it('shows the dimension labels on the drawing', () => {
    render(
      <FigureStimulus spec={{ shape: 'triangle', labels: { base: '10 in', height: '4 in' } }} />,
    );
    expect(screen.getByText('10 in')).toBeInTheDocument();
    expect(screen.getByText('4 in')).toBeInTheDocument();
  });

  it('renders the prism with all three dimensions labeled', () => {
    render(
      <FigureStimulus
        spec={{ shape: 'prism', labels: { length: '5 cm', width: '2 cm', height: '3 cm' } }}
      />,
    );
    expect(
      screen.getByRole('img', {
        name: /right rectangular prism, length 5 cm, width 2 cm, height 3 cm/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('5 cm')).toBeInTheDocument();
    expect(screen.getByText('2 cm')).toBeInTheDocument();
    expect(screen.getByText('3 cm')).toBeInTheDocument();
  });

  it('renders the parallelogram shape', () => {
    const { container } = render(
      <FigureStimulus spec={{ shape: 'parallelogram', labels: { base: '6 m', height: '5 m' } }} />,
    );
    // The shape is drawn as a polygon outline; the dashed altitude is the aux line.
    expect(container.querySelector('polygon.wm-fig-shape')).not.toBeNull();
    expect(container.querySelector('.wm-fig-aux')).not.toBeNull();
  });
});
