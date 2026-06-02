// Tests for the guide-voice hook (Slice AR.3): it plays a banked line's cached audio and tracks the
// current spoken word, stays silent when there is no audio or the user has muted / prefers reduced
// motion, and toggles `speaking` from the clip's clock. Captions are the caller's job and are NEVER
// gated by this hook — these tests assert only the audio + lip-sync behavior.

import { act, renderHook } from '@testing-library/react';
import type { SpokenAudio } from '@whollymath/shared-types';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useGuideSpeech } from './useGuideSpeech';

const AUDIO: SpokenAudio = {
  audio_url: '/tts/audio/abc.mp3',
  words: ['If', 'you', 'shade'],
  wtimes: [0.0, 0.2, 0.5],
  wdurations: [0.15, 0.2, 0.3],
};

// A controllable fake of the browser Audio element: `play()` resolves, and the test drives
// `currentTime` + the rAF clock by hand so word-index advancement is deterministic.
class FakeAudio {
  static instances: FakeAudio[] = [];
  currentTime = 0;
  paused = true;
  src: string;
  private listeners: Record<string, Array<() => void>> = {};

  constructor(src: string) {
    this.src = src;
    FakeAudio.instances.push(this);
  }
  play(): Promise<void> {
    this.paused = false;
    return Promise.resolve();
  }
  pause(): void {
    this.paused = true;
  }
  addEventListener(type: string, cb: () => void): void {
    (this.listeners[type] ??= []).push(cb);
  }
  removeEventListener(type: string, cb: () => void): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== cb);
  }
  emit(type: string): void {
    for (const cb of this.listeners[type] ?? []) cb();
  }
}

// rAF in jsdom is not a real clock; capture the scheduled callback so the test can step it.
let rafCallbacks: FrameRequestCallback[] = [];

function stepFrame(): void {
  const callbacks = rafCallbacks;
  rafCallbacks = [];
  act(() => {
    for (const cb of callbacks) cb(performance.now());
  });
}

function setMuted(muted: boolean): void {
  window.localStorage.setItem('wm-mascot-muted', muted ? '1' : '0');
}

function setReducedMotion(reduce: boolean): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: reduce && query.includes('reduce'),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
}

beforeEach(() => {
  FakeAudio.instances = [];
  rafCallbacks = [];
  window.localStorage.clear();
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio);
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback): number => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  });
  vi.stubGlobal('cancelAnimationFrame', () => {});
  setReducedMotion(false);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useGuideSpeech', () => {
  it('plays the audio and reports speaking when a ref is present', async () => {
    const { result } = renderHook(() => useGuideSpeech(AUDIO));
    // The play() promise resolves on a microtask; flush it, then the first rAF sets speaking.
    await act(async () => {});
    expect(FakeAudio.instances).toHaveLength(1);
    expect(FakeAudio.instances[0].src).toContain('/tts/audio/abc.mp3');
    expect(FakeAudio.instances[0].paused).toBe(false);

    stepFrame();
    expect(result.current.speaking).toBe(true);
  });

  it('stays silent (and creates no audio) when the ref is absent', () => {
    const { result } = renderHook(() => useGuideSpeech(null));
    expect(result.current.speaking).toBe(false);
    expect(result.current.wordIndex).toBe(-1);
    expect(FakeAudio.instances).toHaveLength(0);
  });

  it('suppresses audio when the learner has muted', () => {
    setMuted(true);
    const { result } = renderHook(() => useGuideSpeech(AUDIO));
    expect(result.current.speaking).toBe(false);
    expect(FakeAudio.instances).toHaveLength(0);
  });

  it('suppresses audio when the user prefers reduced motion', () => {
    setReducedMotion(true);
    const { result } = renderHook(() => useGuideSpeech(AUDIO));
    expect(result.current.speaking).toBe(false);
    expect(FakeAudio.instances).toHaveLength(0);
  });

  it('advances the spoken word index from the clip clock (wtimes)', async () => {
    const { result } = renderHook(() => useGuideSpeech(AUDIO));
    await act(async () => {});
    const element = FakeAudio.instances[0];

    element.currentTime = 0.05; // before word 1 starts → word 0
    stepFrame();
    expect(result.current.wordIndex).toBe(0);

    element.currentTime = 0.3; // past 0.2 → word 1
    stepFrame();
    expect(result.current.wordIndex).toBe(1);

    element.currentTime = 0.6; // past 0.5 → word 2
    stepFrame();
    expect(result.current.wordIndex).toBe(2);
  });

  it('toggles speaking off when the clip ends', async () => {
    const { result } = renderHook(() => useGuideSpeech(AUDIO));
    await act(async () => {});
    stepFrame();
    expect(result.current.speaking).toBe(true);

    act(() => FakeAudio.instances[0].emit('ended'));
    expect(result.current.speaking).toBe(false);
    expect(result.current.wordIndex).toBe(-1);
  });
});
