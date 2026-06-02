import { render } from '@testing-library/react';
import type { Emotion } from '@whollymath/shared-types';
import { describe, expect, it } from 'vitest';

import { Mascot } from './Mascot';

// Avatar Phase 0: the mascot must visibly reflect the live backend emotion by applying the shared
// `wm-guide-emotion-*` class to its figure — and must NOT regress for callers that pass no emotion.

const ALL_EMOTIONS: Emotion[] = ['encourage', 'celebrate', 'think', 'reassure', 'neutral'];

describe('Mascot emotion wiring', () => {
  it('applies the matching wm-guide-emotion-* class for each emotion', () => {
    for (const emotion of ALL_EMOTIONS) {
      const { container, unmount } = render(<Mascot emotion={emotion} intensity={0.6} />);
      const figure = container.querySelector('.wm-mascot-figure');
      expect(figure).not.toBeNull();
      expect(figure?.classList.contains(`wm-guide-emotion-${emotion}`)).toBe(true);
      expect(figure?.getAttribute('data-emotion')).toBe(emotion);
      unmount();
    }
  });

  it('sets the intensity weight CSS var from the clamped contract', () => {
    const { container } = render(<Mascot emotion="celebrate" intensity={0.8} />);
    const figure = container.querySelector<HTMLElement>('.wm-mascot-figure');
    expect(figure?.style.getPropertyValue('--wm-guide-weight')).toBe('0.8');
  });

  it('renders a bare figure with no emotion class or weight var when emotion is omitted', () => {
    const { container } = render(<Mascot />);
    const figure = container.querySelector<HTMLElement>('.wm-mascot-figure');
    expect(figure).not.toBeNull();
    expect(figure?.className).toBe('wm-mascot-figure');
    expect(figure?.getAttribute('style')).toBeNull();
    expect(figure?.getAttribute('data-emotion')).toBeNull();
  });

  it('still speaks (and reflects emotion) when a line is given', () => {
    const { container, getByText } = render(
      <Mascot speech="Nice work!" emotion="celebrate" intensity={1} />,
    );
    expect(getByText('Nice work!')).toBeInTheDocument();
    const figure = container.querySelector('.wm-mascot-figure');
    expect(figure?.classList.contains('wm-guide-emotion-celebrate')).toBe(true);
  });
});

describe('Mascot talking-mouth (Slice AR.3)', () => {
  it('shows the talking class while speaking and renders the animated mouth', () => {
    const { container } = render(<Mascot speaking />);
    const figure = container.querySelector('.wm-mascot-figure');
    expect(figure?.classList.contains('wm-guide-speaking')).toBe(true);
    expect(figure?.getAttribute('data-speaking')).toBe('true');
    // The animated mouth element is present so CSS can move it while speaking.
    expect(container.querySelector('.wm-guide-mouth')).not.toBeNull();
  });

  it('does not carry the talking class when idle (no regression for non-speaking callers)', () => {
    const { container } = render(<Mascot />);
    const figure = container.querySelector('.wm-mascot-figure');
    expect(figure?.classList.contains('wm-guide-speaking')).toBe(false);
    expect(figure?.getAttribute('data-speaking')).toBeNull();
    // The bare figure className is still exactly the legacy value (the mouth element is inert).
    expect(figure?.className).toBe('wm-mascot-figure');
  });
});
