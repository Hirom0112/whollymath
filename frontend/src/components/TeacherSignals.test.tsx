import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { TeacherAlertView } from '../api/teacher';

import { AlertBadge, CategoryChip } from './TeacherSignals';

// The teacher alert/category visual system (TODO TCH.F4). The load-bearing invariant here is
// PRODUCT.md's accessibility rule: "never encode meaning by hue alone, pair color with shape,
// position, label, or icon." These tests fail if a future change drops the drawn icon or the
// word, so meaning can never come to rest on color alone.

describe('CategoryChip', () => {
  it.each([
    ['struggling', /struggling/i],
    ['needs_attention', /needs attention/i],
    ['on_track', /on track/i],
  ] as const)('%s renders both a word and a drawn icon (color is never the only cue)', (cat, word) => {
    const { container } = render(<CategoryChip category={cat} />);
    expect(container.textContent ?? '').toMatch(word);
    expect(container.querySelector('svg')).not.toBeNull();
  });
});

describe('AlertBadge', () => {
  const alert: TeacherAlertView = {
    kind: 'REPEATED_MISCONCEPTION',
    severity: 'urgent',
    message: 'Natural-number bias on 4 of the last 6 comparisons.',
  };

  it('pairs the severity word + rule label + icon (compact)', () => {
    const { container } = render(<AlertBadge alert={alert} />);
    const text = container.textContent ?? '';
    expect(text).toMatch(/urgent/i); // severity word, not just a red tint
    expect(text).toMatch(/repeated misconception/i); // the named rule
    expect(container.querySelector('svg')).not.toBeNull(); // a drawn icon
  });

  it('shows the plain-language message only in the full variant', () => {
    const compact = render(<AlertBadge alert={alert} />);
    expect(compact.container.textContent ?? '').not.toContain('Natural-number bias on 4');

    const full = render(<AlertBadge alert={alert} variant="full" />);
    expect(full.container.textContent ?? '').toContain('Natural-number bias on 4');
  });

  it.each(['urgent', 'warn', 'info'] as const)('renders a severity word for %s', (severity) => {
    const word = { urgent: /urgent/i, warn: /warning/i, info: /note/i }[severity];
    const { container } = render(<AlertBadge alert={{ ...alert, severity }} />);
    expect(container.textContent ?? '').toMatch(word);
  });
});
