import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { DEFAULT_GUIDE_ID, GuideProvider, useGuide } from './GuideContext';

// GuideContext holds the learner's pick-once-and-remember guide preference plus the device
// capability. Phase 0 invariants: defaults to the mascot, persists a picked guide under the
// documented key, and the capability probe always resolves "2d".

const STORAGE_KEY = 'wm-guide-id';

function wrapper({ children }: { children: React.ReactNode }): React.JSX.Element {
  return <GuideProvider>{children}</GuideProvider>;
}

describe('useGuide', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it('defaults to the mascot guide at "2d" capability', () => {
    const { result } = renderHook(() => useGuide(), { wrapper });
    expect(result.current.guideId).toBe(DEFAULT_GUIDE_ID);
    expect(result.current.capability).toBe('2d');
  });

  it('setGuideId picks a guide and persists it to localStorage', () => {
    const { result } = renderHook(() => useGuide(), { wrapper });

    act(() => {
      result.current.setGuideId('fox');
    });

    expect(result.current.guideId).toBe('fox');
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe('fox');
  });

  it('reads a remembered guide id on mount (pick-once + remember)', () => {
    window.localStorage.setItem(STORAGE_KEY, 'owl');
    const { result } = renderHook(() => useGuide(), { wrapper });
    expect(result.current.guideId).toBe('owl');
  });

  it('outside a provider returns the safe mascot/2d fallback with an inert setter', () => {
    const { result } = renderHook(() => useGuide());
    expect(result.current.guideId).toBe(DEFAULT_GUIDE_ID);
    expect(result.current.capability).toBe('2d');
    act(() => {
      result.current.setGuideId('fox');
    });
    expect(result.current.guideId).toBe(DEFAULT_GUIDE_ID);
  });
});
