// PHASE-1 SPIKE — unit tests for the dev opt-in flag. Default MUST be OFF; opt-in via either the
// localStorage key or the URL query param. This is the pure half of the isolation guarantee.

import { afterEach, describe, expect, it } from 'vitest';

import { AVATAR_3D_FLAG_KEY, isAvatar3DEnabled } from './avatar3dFlag';

afterEach(() => {
  window.localStorage.clear();
  // Reset the URL so a query-param test can't leak into the next case.
  window.history.replaceState({}, '', '/');
});

describe('isAvatar3DEnabled', () => {
  it('is OFF by default (no flag, no query param)', () => {
    expect(isAvatar3DEnabled()).toBe(false);
  });

  it('is ON when localStorage wm-avatar-3d === "1"', () => {
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, '1');
    expect(isAvatar3DEnabled()).toBe(true);
  });

  it('stays OFF for any other localStorage value', () => {
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, '0');
    expect(isAvatar3DEnabled()).toBe(false);
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, 'true');
    expect(isAvatar3DEnabled()).toBe(false);
  });

  it('is ON when the URL has ?avatar3d=1', () => {
    window.history.replaceState({}, '', '/?avatar3d=1');
    expect(isAvatar3DEnabled()).toBe(true);
  });

  it('stays OFF for ?avatar3d=0', () => {
    window.history.replaceState({}, '', '/?avatar3d=0');
    expect(isAvatar3DEnabled()).toBe(false);
  });
});
