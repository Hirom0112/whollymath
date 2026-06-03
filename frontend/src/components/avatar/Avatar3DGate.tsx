// PHASE-1 SPIKE — the GATE that decides whether the 3D avatar may mount. This is the isolation
// boundary that keeps the spike safe to merge: it renders the 3D surface ONLY when BOTH conditions
// hold, and renders NOTHING otherwise (the host page's existing 2D Mascot is untouched).
//
//   (a) the device capability probe says the device is strong (`capability === '3d'`), AND
//   (b) the developer explicitly opted in (the `wm-avatar-3d` flag / `?avatar3d=1` — see avatar3dFlag).
//
// Default OFF: in Phase 0 the probe always returns '2d' AND the flag defaults false, so this gate
// renders nothing by default — the production 2D path is byte-for-byte unaffected whether or not this
// component exists in the tree. The owner mounts `<Avatar3DGate>` manually for the perf test.
//
// LAZY-LOADED: the 3D component (and the whole three.js/r3f/drei bundle) is behind `React.lazy` +
// dynamic import, so the deps land in their OWN chunk and never bloat the main bundle. A device that
// stays 2D never downloads the 3D code. (CLAUDE.md §8.6 simplicity / the spike must not tax the demo.)

import { Suspense, lazy } from 'react';

import { useGuide } from '../../state/GuideContext';

import type { Avatar3DProps } from './Avatar3D';
import { isAvatar3DEnabled } from './avatar3dFlag';

// Dynamic import → the three.js/r3f/drei bundle is split into its own lazy chunk. This import
// expression is the ONLY static reference to Avatar3D, so a build that never reaches the gate's
// enabled branch never evaluates it.
const Avatar3D = lazy(() => import('./Avatar3D'));

export interface Avatar3DGateProps extends Avatar3DProps {
  /**
   * Force-enable the 3D path regardless of the capability probe, for the owner's perf test on a
   * device the Phase-0 probe still reports as '2d' (the real WebGL2/perf probe is not wired yet —
   * `capabilityProbe` returns '2d' unconditionally in Phase 0). The dev opt-in flag is STILL
   * required, so this can never turn the 3D path on for a default user. Defaults false.
   */
  forceCapable?: boolean;
}

/**
 * Render the 3D avatar spike iff (capability-strong OR `forceCapable`) AND the dev opt-in flag is set.
 * Otherwise render `null` — the host keeps showing its existing 2D Mascot, unchanged.
 *
 * The 3D surface is wrapped in `<Suspense>` with a null fallback (the lazy chunk loads async); the
 * host page shows nothing extra while it streams in, never the 2D mascot flickering.
 */
export function Avatar3DGate({
  forceCapable = false,
  ...props
}: Avatar3DGateProps): React.JSX.Element | null {
  const { capability } = useGuide();

  const capable = forceCapable || capability === '3d';
  const optedIn = isAvatar3DEnabled();

  // The isolation guarantee: default-OFF unless BOTH gates pass. Either failing → render nothing new.
  if (!capable || !optedIn) return null;

  return (
    <div className="wm-avatar3d-spike-container" data-testid="wm-avatar3d-container">
      <Suspense fallback={null}>
        <Avatar3D {...props} />
      </Suspense>
    </div>
  );
}
