// PHASE-1 SPIKE — the critical isolation tests for the 3D gate.
//
// The load-bearing assertion is the FIRST one: with the dev opt-in flag OFF (the default), the 3D
// path does NOT mount — the gate renders nothing, so the host's existing 2D experience is untouched.
// This is the test that proves the spike is safe to merge.
//
// The 3D component is mocked (a plain div) so jsdom never attempts real WebGL — these tests assert
// the GATE DECISION and that the container mounts, not any GL output. `@react-three/fiber` and
// `@react-three/drei` are never imported here because `./Avatar3D` is mocked at the module boundary.

import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GuideProvider } from '../../state/GuideContext';

import { AVATAR_3D_FLAG_KEY } from './avatar3dFlag';
import { Avatar3DGate } from './Avatar3DGate';
import { probeCapability } from './capabilityProbe';

// Mock the lazy-loaded 3D surface so no WebGL is touched in jsdom. The gate's dynamic
// `import('./Avatar3D')` resolves to this stub.
vi.mock('./Avatar3D', () => ({
  default: ({ emotion }: { emotion?: string }) => (
    <div data-testid="wm-avatar3d-stub" data-emotion={emotion ?? 'neutral'}>
      3D avatar mounted
    </div>
  ),
}));

// Mock the capability probe so we can drive the '3d' branch without the Phase-0 hard-coded '2d'.
vi.mock('./capabilityProbe', () => ({
  probeCapability: vi.fn((): '2d' | '3d' => '2d'),
}));

const mockedProbe = vi.mocked(probeCapability);

afterEach(() => {
  window.localStorage.clear();
  mockedProbe.mockReturnValue('2d');
  vi.clearAllMocks();
});

describe('Avatar3DGate isolation (default OFF)', () => {
  it('renders NOTHING when the dev flag is OFF, even on a capable device', () => {
    // Capable device...
    mockedProbe.mockReturnValue('3d');
    // ...but no opt-in flag set (the default).
    const { container } = render(
      <GuideProvider>
        <Avatar3DGate emotion="celebrate" intensity={1} />
      </GuideProvider>,
    );
    // The gate renders null → no container, no 3D stub. The host's 2D path is untouched.
    expect(container.querySelector('.wm-avatar3d-spike-container')).toBeNull();
    expect(screen.queryByTestId('wm-avatar3d-stub')).toBeNull();
  });

  it('renders NOTHING when the flag is ON but the device is NOT capable (probe 2d)', () => {
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, '1');
    mockedProbe.mockReturnValue('2d');
    const { container } = render(
      <GuideProvider>
        <Avatar3DGate emotion="celebrate" intensity={1} />
      </GuideProvider>,
    );
    expect(container.querySelector('.wm-avatar3d-spike-container')).toBeNull();
    expect(screen.queryByTestId('wm-avatar3d-stub')).toBeNull();
  });
});

describe('Avatar3DGate enabled (flag ON + capable)', () => {
  it('mounts the 3D container + component when flag ON and probe reports 3d', async () => {
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, '1');
    mockedProbe.mockReturnValue('3d');
    render(
      <GuideProvider>
        <Avatar3DGate emotion="celebrate" intensity={1} />
      </GuideProvider>,
    );
    // The lazy chunk resolves async → wait for the mocked 3D stub to appear.
    await waitFor(() => {
      expect(screen.getByTestId('wm-avatar3d-stub')).toBeInTheDocument();
    });
    expect(screen.getByTestId('wm-avatar3d-container')).toBeInTheDocument();
    // The shared emotion contract is forwarded through to the 3D surface.
    expect(screen.getByTestId('wm-avatar3d-stub').getAttribute('data-emotion')).toBe('celebrate');
  });

  it('mounts via forceCapable + flag even when the Phase-0 probe still reports 2d', async () => {
    window.localStorage.setItem(AVATAR_3D_FLAG_KEY, '1');
    mockedProbe.mockReturnValue('2d');
    render(
      <GuideProvider>
        <Avatar3DGate emotion="think" forceCapable />
      </GuideProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('wm-avatar3d-stub')).toBeInTheDocument();
    });
  });

  it('still renders NOTHING with forceCapable but NO flag (flag is mandatory)', () => {
    mockedProbe.mockReturnValue('2d');
    const { container } = render(
      <GuideProvider>
        <Avatar3DGate forceCapable />
      </GuideProvider>,
    );
    expect(container.querySelector('.wm-avatar3d-spike-container')).toBeNull();
  });
});
