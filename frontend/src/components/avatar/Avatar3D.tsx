// PHASE-1 SPIKE — a representative 3D guide character for the perf acceptance test.
//
// PURPOSE (and ONLY purpose): give the owner ONE animated 3D character to run the hard acceptance
// gate from V2_TODO "AVATAR DIRECTION" — "does a single 3D character hold ~30fps on a low-end
// Chromebook?". This is capability-gated and behind a dev opt-in flag (see Avatar3DGate); it does
// NOT touch the 2D Mascot path, which remains every user's default.
//
// WHAT THIS IS HONESTLY NOT: the real guide. The real roster (V2_TODO) is a rigged CC0 VRM driven by
// TalkingHead.js / @pixiv/three-vrm with face/jaw morph targets. Sourcing + rigging that model is
// out of scope for THIS spike, so the character below is a drei/three primitive placeholder. It
// UNDER-represents a rigged VRM's GPU load (no skinned mesh, no morph targets, far fewer triangles,
// no texture sampling) — a "strong" 30fps reading here is necessary-but-not-sufficient evidence that
// the real model will hold frame rate. The TalkingHead/VRM layer is a clearly-marked seam below.
//
// DRIVEN BY THE EXISTING CONTRACT: it consumes the same `{ emotion, intensity }` payload (slice 1.3)
// through the shared `emotionToGuide` mapping, and the same word-timing the 2D guide uses
// (`GuideSpeech.wordIndex` from `useGuideSpeech`) to drive a first-pass jaw/mouth movement. No new
// emotion mapping is invented here (CLAUDE.md anti-pattern 8.3 / the single-contract rule).

import { OrbitControls, Stats } from '@react-three/drei';
import { Canvas, useFrame } from '@react-three/fiber';
import type { Emotion } from '@whollymath/shared-types';
import { useRef } from 'react';
import type { Group, Mesh } from 'three';
import { Color } from 'three';

import { emotionToGuide } from './emotionToGuide';

/** A visible, deterministic color per `mood` so the emotion contract is observably driving the 3D
 * surface in the spike. Maps the abstract `mood` (from `emotionToGuide`) to an RGB hex — this is a
 * SPIKE stand-in for a VRM expression morph, not the production face channel. */
const MOOD_COLOR: Record<string, string> = {
  warm: '#f59e0b', // encourage
  joyful: '#22c55e', // celebrate
  curious: '#6366f1', // think
  calm: '#38bdf8', // reassure
  attentive: '#94a3b8', // neutral
};

const DEFAULT_MOOD_COLOR = '#94a3b8';

export interface Avatar3DProps {
  /** The live backend emotion to reflect (slice 1.3). Defaults to neutral. */
  emotion?: Emotion;
  /** How strongly to play `emotion`, a [0,1] scalar (clamped by the shared contract). */
  intensity?: number;
  /**
   * The live spoken-word index from `useGuideSpeech` (-1 when not speaking). Drives the first-pass
   * jaw movement: any value >= 0 means "a word is being spoken now", so the mouth opens. A richer
   * viseme mapping (per-phoneme morphs) is the VRM seam — see `LIPSYNC SEAM` below.
   */
  wordIndex?: number;
  /** Show the drei FPS meter overlay (the whole point of the spike). Defaults true here. */
  showStats?: boolean;
}

/**
 * The animated character body. Lives INSIDE the <Canvas> (it uses r3f hooks), so it is kept separate
 * from the Canvas wrapper that `Avatar3D` exports.
 *
 * Idle animation: a continuous gentle bob + sway driven by `useFrame` (the render loop), so the
 * perf test exercises a real per-frame update, not a static scene.
 *
 * Emotion: the body color is set from the shared `emotionToGuide` mood (SPIKE stand-in for a VRM
 * expression). `weight` (intensity) scales the bob amplitude — the same [0,1] amplitude semantics
 * the 2D mascot uses.
 *
 * Lip-sync (FIRST PASS): the "mouth" sphere scales open while `wordIndex >= 0` (a word is being
 * spoken). This wires the EXISTING word-timing to visible jaw motion. See the LIPSYNC SEAM note.
 */
function GuideBody({
  emotion = 'neutral',
  intensity = 0,
  wordIndex = -1,
}: Pick<Avatar3DProps, 'emotion' | 'intensity' | 'wordIndex'>): React.JSX.Element {
  const groupRef = useRef<Group>(null);
  const mouthRef = useRef<Mesh>(null);

  const presentation = emotionToGuide(emotion, intensity);
  const bodyColor = MOOD_COLOR[presentation.mood] ?? DEFAULT_MOOD_COLOR;
  // Bob amplitude scales with intensity weight (min floor so idle is always visibly alive).
  const bobAmplitude = 0.05 + 0.15 * presentation.weight;

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const group = groupRef.current;
    if (group) {
      // Idle: vertical bob + a slow sway. A real per-frame transform so the perf reading is honest.
      group.position.y = Math.sin(t * 1.5) * bobAmplitude;
      group.rotation.y = Math.sin(t * 0.4) * 0.25;
    }

    // LIPSYNC SEAM (first pass): drive the jaw from the EXISTING word-timing. `wordIndex >= 0` means
    // `useGuideSpeech` reports a word is being spoken right now, so open the mouth; a small sinusoid
    // on top gives it life. This is a deliberately coarse open/closed jaw — NOT viseme-accurate.
    //
    // TODO(P2, VRM): replace this scale hack with real viseme morph targets. The production path maps
    // each `audio.words[wordIndex]` (+ `wdurations`) to phoneme visemes and drives the rigged VRM's
    // mouth blendshapes via @pixiv/three-vrm / TalkingHead.js. That layer is intentionally STUBBED in
    // this spike (no rigged model to drive); this scale is the placeholder for it.
    const mouth = mouthRef.current;
    if (mouth) {
      const speaking = wordIndex >= 0;
      const openness = speaking ? 0.6 + 0.4 * Math.abs(Math.sin(t * 12)) : 0.05;
      mouth.scale.set(1, openness, 1);
    }
  });

  return (
    <group ref={groupRef}>
      {/* Head */}
      <mesh position={[0, 1.1, 0]} castShadow>
        <sphereGeometry args={[0.7, 32, 32]} />
        <meshStandardMaterial color={bodyColor} roughness={0.4} metalness={0.1} />
      </mesh>
      {/* Eyes (decorative; give the perf scene a couple more draw calls) */}
      <mesh position={[-0.25, 1.25, 0.6]}>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshStandardMaterial color="#0f172a" />
      </mesh>
      <mesh position={[0.25, 1.25, 0.6]}>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshStandardMaterial color="#0f172a" />
      </mesh>
      {/* Mouth — the lip-sync target (scaled by `wordIndex` in useFrame). */}
      <mesh ref={mouthRef} position={[0, 0.85, 0.62]}>
        <sphereGeometry args={[0.18, 16, 16]} />
        <meshStandardMaterial color="#7f1d1d" />
      </mesh>
      {/* Body */}
      <mesh position={[0, -0.2, 0]} castShadow>
        <capsuleGeometry args={[0.55, 0.8, 8, 24]} />
        <meshStandardMaterial color={bodyColor} roughness={0.5} metalness={0.1} />
      </mesh>
    </group>
  );
}

/**
 * The exported 3D guide surface: an r3f `<Canvas>` with lighting, the animated `GuideBody`, ground,
 * orbit controls (so the owner can inspect the model during the test), and the FPS meter overlay.
 *
 * It is a self-contained scene; the caller (`Avatar3DGate`) only mounts it when the device is
 * capability-strong AND the dev opt-in flag is set. It is lazy-loaded (React.lazy in the gate) so the
 * three.js bundle never lands in the main chunk — the 2D default pays no 3D bundle cost.
 */
export default function Avatar3D({
  emotion = 'neutral',
  intensity = 0,
  wordIndex = -1,
  showStats = true,
}: Avatar3DProps): React.JSX.Element {
  return (
    <Canvas
      camera={{ position: [0, 0.8, 4], fov: 45 }}
      shadows
      dpr={[1, 2]}
      // A note for the reader: `gl` defaults are fine for the spike; the perf test reads the meter.
    >
      {/* The FPS meter — the whole point of the spike. drei `<Stats/>` renders an overlay panel. */}
      {showStats ? <Stats /> : null}

      <color attach="background" args={[new Color('#0b1020')]} />
      <ambientLight intensity={0.6} />
      <directionalLight position={[3, 5, 2]} intensity={1.1} castShadow />

      <GuideBody emotion={emotion} intensity={intensity} wordIndex={wordIndex} />

      {/* Ground plane to receive the shadow (a little more GPU work, closer to a real scene). */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.4, 0]} receiveShadow>
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial color="#111827" />
      </mesh>

      <OrbitControls enablePan={false} />
    </Canvas>
  );
}
