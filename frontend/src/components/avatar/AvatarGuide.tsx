// The public guide component the app mounts (Avatar Phase 0).
//
// `AvatarGuide` is the single seam the rest of the app talks to. It reads the device capability
// from `GuideContext` and renders the right runtime. Phase 0 has exactly one runtime — the existing
// CSS `Mascot` — and the capability is always "2d", so this always renders the 2D fallback. The
// branch is here NOW so that when Phase 1 lands a 3D surface, the only change is filling the seam:
// the app keeps mounting `<AvatarGuide>` and nothing else moves.
//
// It forwards the live `{ emotion, intensity }` payload straight to the chosen runtime via the
// shared contract, so a future 3D guide reflects the same emotion the mascot does today.

import type { Emotion } from '@whollymath/shared-types';

import { useGuide } from '../../state/GuideContext';
import { Mascot } from '../Mascot';

export interface AvatarGuideProps {
  /** A short line for the guide to speak; omit for a silent figure. */
  speech?: string;
  /** Tints the speech bubble by intent (same semantics as `Mascot`). */
  speechKind?: 'correct' | 'neutral' | 'say';
  /** The live backend emotion to reflect (slice 1.3); omit to leave the guide unstyled. */
  emotion?: Emotion;
  /** How strongly to play `emotion`, a [0,1] scalar. */
  intensity?: number;
}

export function AvatarGuide(props: AvatarGuideProps): React.JSX.Element {
  // `capability` is read so the Phase-1 branch has a real signal to switch on. In Phase 0 it is
  // always "2d", so every user gets the CSS mascot fallback below.
  const { capability } = useGuide();

  // TODO(P1): React.lazy the 3D surface and render it when `capability === '3d'` (only reachable
  // once `capabilityProbe` ships the WebGL2 + perf probe). The 3D surface MUST consume the same
  // `emotionToGuide` contract (mood/gesture/weight) so the two runtimes stay in lock-step.
  void capability;

  return <Mascot {...props} />;
}
