import { render, screen } from '@testing-library/react';
import type { ProblemView } from '@whollymath/shared-types';
import { describe, expect, it } from 'vitest';

import { SetModelStimulus } from './SetModelStimulus';

// SetModelStimulus is DISPLAY-ONLY (like StatsStimulus) — it draws the jar of counters a
// ratio-language problem names and is NOT an answer input. These tests pin: it draws one marble per
// counter with the right colour multiset (counters are MIXED, so order is not asserted), reads the
// collection in its aria-label, and renders nothing when the problem carries no set model.

function problemWith(setModel: ProblemView['set_model']): ProblemView {
  return {
    problem_id: 'p-1',
    kc: 'KC_ratio_language',
    surface_format: 'symbolic',
    statement: 'A jar has 3 green and 6 yellow counters. What fraction are green?',
    widget_id: 'fraction_editor',
    set_model: setModel,
  };
}

/** Count counters by colour via the data-colour hook (mix-order-independent). */
function colourCounts(container: HTMLElement): Record<string, number> {
  const counts: Record<string, number> = {};
  container.querySelectorAll<SVGGElement>('g[data-colour]').forEach((g) => {
    const c = g.dataset.colour ?? '';
    counts[c] = (counts[c] ?? 0) + 1;
  });
  return counts;
}

describe('SetModelStimulus', () => {
  it('draws one marble per counter across both colour groups', () => {
    const { container } = render(
      <SetModelStimulus
        problem={problemWith({
          kind: 'set_model',
          groups: [
            { colour: 'green', count: 3 },
            { colour: 'yellow', count: 6 },
          ],
          asked_colour: 'green',
        })}
      />,
    );
    // 3 + 6 = 9 counters -> 9 marbles.
    expect(container.querySelectorAll('circle.wm-setmodel-counter')).toHaveLength(9);
  });

  it('draws the right number of counters of each colour (regardless of mix order)', () => {
    const { container } = render(
      <SetModelStimulus
        problem={problemWith({
          kind: 'set_model',
          groups: [
            { colour: 'red', count: 5 },
            { colour: 'blue', count: 2 },
          ],
          asked_colour: 'red',
        })}
      />,
    );
    expect(colourCounts(container)).toEqual({ red: 5, blue: 2 });
  });

  it('mixes the counters deterministically — same problem renders the same order', () => {
    const sm = {
      kind: 'set_model' as const,
      groups: [
        { colour: 'red', count: 5 },
        { colour: 'blue', count: 2 },
      ],
      asked_colour: 'red',
    };
    const order = (c: HTMLElement): string[] =>
      [...c.querySelectorAll<SVGGElement>('g[data-colour]')].map((g) => g.dataset.colour ?? '');
    const a = render(<SetModelStimulus problem={problemWith(sm)} />);
    const b = render(<SetModelStimulus problem={problemWith(sm)} />);
    expect(order(a.container)).toEqual(order(b.container));
    // The mix is not simply grouped (red,red,red,red,red,blue,blue) — at least one blue moved up.
    expect(order(a.container).slice(0, 5)).not.toEqual(['red', 'red', 'red', 'red', 'red']);
  });

  it('reads the collection in its accessible label', () => {
    render(
      <SetModelStimulus
        problem={problemWith({
          kind: 'set_model',
          groups: [
            { colour: 'green', count: 3 },
            { colour: 'yellow', count: 6 },
          ],
          asked_colour: 'green',
        })}
      />,
    );
    expect(
      screen.getByRole('img', { name: /jar of counters: 3 green and 6 yellow/i }),
    ).toBeInTheDocument();
  });

  it('renders nothing for a problem with no set model', () => {
    const { container } = render(<SetModelStimulus problem={problemWith(null)} />);
    expect(container.querySelector('.wm-setmodel')).toBeNull();
  });
});
