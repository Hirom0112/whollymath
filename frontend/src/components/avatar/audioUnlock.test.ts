// Tests for the Safari/iOS audio-unlock module (Slice AR.3 bugfix): it keeps ONE shared <audio>
// element and "blesses" it on the learner's first gesture (so Safari permits later, out-of-gesture
// play() for the voice). These tests prove the LOGIC — that the element is reused, blessed exactly
// once, and that install is idempotent. They CANNOT prove Safari's real autoplay policy (jsdom has
// no such policy); that remains a manual check on a real device.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installAudioUnlock, resetAudioUnlockForTest, sharedAudioElement } from './audioUnlock';

// Minimal fake of the browser Audio element (mirrors the one in useGuideSpeech.test.ts): counts
// play() calls so we can assert the element was blessed exactly once.
class FakeAudio {
  static instances: FakeAudio[] = [];
  currentTime = 0;
  paused = true;
  muted = false;
  src = '';
  playCount = 0;

  constructor() {
    FakeAudio.instances.push(this);
  }
  play(): Promise<void> {
    this.playCount += 1;
    this.paused = false;
    return Promise.resolve();
  }
  pause(): void {
    this.paused = true;
  }
}

// Guard the jsdom window: dispatchEvent needs a real Event constructor, present in jsdom.
function dispatchGesture(type: string): void {
  window.dispatchEvent(new Event(type));
}

beforeEach(() => {
  resetAudioUnlockForTest();
  FakeAudio.instances = [];
  vi.stubGlobal('Audio', FakeAudio as unknown as typeof Audio);
});

afterEach(() => {
  resetAudioUnlockForTest();
  vi.unstubAllGlobals();
});

describe('audioUnlock', () => {
  it('sharedAudioElement returns one reused element', () => {
    const a = sharedAudioElement();
    const b = sharedAudioElement();
    expect(a).not.toBeNull();
    expect(a).toBe(b);
    expect(FakeAudio.instances).toHaveLength(1);
  });

  it('installAudioUnlock is idempotent and safe to call repeatedly', () => {
    expect(() => {
      installAudioUnlock();
      installAudioUnlock();
      installAudioUnlock();
    }).not.toThrow();
  });

  it('blesses the shared element exactly once on the first gesture', () => {
    installAudioUnlock();
    const element = sharedAudioElement() as unknown as FakeAudio;

    dispatchGesture('pointerdown');
    expect(element.playCount).toBe(1);

    // Further gestures do nothing: the listeners removed themselves after the first bless.
    dispatchGesture('pointerdown');
    dispatchGesture('touchend');
    dispatchGesture('keydown');
    expect(element.playCount).toBe(1);
  });

  it('leaves the element unmuted and reset after blessing (ready for a real line)', () => {
    installAudioUnlock();
    const element = sharedAudioElement() as unknown as FakeAudio;

    dispatchGesture('pointerdown');
    expect(element.muted).toBe(false);
    expect(element.currentTime).toBe(0);
  });

  it('resetAudioUnlockForTest clears the element and re-arms the unlock', () => {
    const first = sharedAudioElement();
    installAudioUnlock();
    dispatchGesture('pointerdown');
    expect((first as unknown as FakeAudio).playCount).toBe(1);

    resetAudioUnlockForTest();

    // A fresh element, and the unlock can be installed + fire again.
    const second = sharedAudioElement();
    expect(second).not.toBe(first);
    installAudioUnlock();
    dispatchGesture('pointerdown');
    expect((second as unknown as FakeAudio).playCount).toBe(1);
  });
});
