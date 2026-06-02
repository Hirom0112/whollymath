import type { ProblemView, SetModelStimulusView } from '@whollymath/shared-types';

import './SetModelStimulus.css';

/**
 * A DISPLAY-ONLY set-model stimulus for KC_ratio_language (CCSS 6.RP.A.1): the jar of counters the
 * prompt names, drawn as the visual anchor at the top of the problem card so a 6th grader SEES the
 * collection they're comparing.
 *
 * Hybrid by design (the team's chosen approach): the storybook GLASS JAR — cork lid, warm ink
 * outline, glass sheen — is a fixed, reusable SVG frame, while the COUNTERS inside it are laid out
 * programmatically from the problem's data (`set_model.groups`). So the picture always matches the
 * exact counts and colours of THIS problem, with no image model in the turn loop (CLAUDE.md §8.1).
 * It shows only the QUESTION INPUT (the counts), never the answer — the correct fraction is graded
 * server-side by SymPy (§8.2). The prompt text stays the accessible fallback.
 *
 * The counters are MIXED (deterministically shuffled) so the jar looks real, not sorted. The mix is
 * a pure function of the colour sequence, so the same problem always renders identically (no
 * `Math.random`, reproducible — PROJECT.md §4.1) and the layout is stable across re-renders.
 *
 * Accessibility: the whole jar is one labeled region (role="img") whose aria-label reads the counts
 * and colours. The individual marbles are decorative. Static (no animation) → reduced-motion safe.
 *
 * Custom SVG, no asset/charting lib (TECH_STACK §2). Class names unique app-wide (prefix
 * `wm-setmodel-`). SVG gradient/clip ids are namespaced per problem so two jars never collide.
 */

// Per-colour marble shading. White/yellow get a darker stroke so they stay visible on the glass.
interface Shade {
  fill: string;
  dark: string;
  light: string;
  stroke: string;
}
const PALETTE: Record<string, Shade> = {
  green: { fill: '#8ec96f', dark: '#5f9a45', light: '#c3e7ad', stroke: '#3a2c1c' },
  yellow: { fill: '#f5cf5b', dark: '#d6a92f', light: '#fbe9a6', stroke: '#7a5a16' },
  red: { fill: '#e0593f', dark: '#b03622', light: '#f3a08c', stroke: '#3a2c1c' },
  blue: { fill: '#4a6cf0', dark: '#2f4dc9', light: '#9db3f7', stroke: '#3a2c1c' },
  black: { fill: '#33323a', dark: '#19181d', light: '#6b6975', stroke: '#19181d' },
  white: { fill: '#fbf7ee', dark: '#d8cfba', light: '#ffffff', stroke: '#7a6b50' },
  orange: { fill: '#efa24e', dark: '#cd7a26', light: '#f9cf9b', stroke: '#3a2c1c' },
  purple: { fill: '#8a63c8', dark: '#653f9f', light: '#c1a4e6', stroke: '#3a2c1c' },
};
const FALLBACK: Shade = PALETTE.blue;

// Jar geometry (the SVG coordinate space; CSS scales it). Mirrors the chosen storybook design.
const VB_W = 260;
const VB_H = 318;
const CAVITY = { x: 64, y: 116, w: 132, h: 150 }; // inner glass the counters must stay within
const PREF_R = 17; // preferred marble radius (shrinks if the jar would overflow)
const GAP = 7;

// Jar silhouette (shoulders → body → rounded base) and the slightly-inset interior clip.
const BODY_PATH =
  'M 84 112 C 70 118, 62 132, 62 150 L 60 232 C 60 256, 78 272, 130 272 ' +
  'C 182 272, 200 256, 200 232 L 198 150 C 198 132, 190 118, 176 112 Z';
const CAVITY_PATH =
  'M 88 116 C 76 122, 70 134, 70 150 L 68 230 C 68 252, 84 266, 130 266 ' +
  'C 176 266, 192 252, 192 230 L 190 150 C 190 134, 184 122, 172 116 Z';

interface Placement {
  cx: number;
  cy: number;
  r: number;
  colour: string;
}

/** A tiny deterministic PRNG (mulberry32) so the "real jar" mix is stable for a given problem. */
function seededRng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The colour sequence, shuffled deterministically so the jar reads as mixed, not sorted. */
function mixedColours(groups: SetModelStimulusView['groups']): string[] {
  const seq = groups.flatMap((g) => Array.from({ length: g.count }, () => g.colour));
  // Seed from the sequence itself → same problem mixes identically every render.
  const seed = seq.reduce((acc, c, i) => acc + (c.charCodeAt(0) + 1) * (i + 7), seq.length * 131);
  const rng = seededRng(seed);
  for (let i = seq.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [seq[i], seq[j]] = [seq[j], seq[i]];
  }
  return seq;
}

/** Pack `colours` into tidy rows that settle bottom-up inside the cavity, like marbles in a jar. */
function packCounters(colours: string[]): Placement[] {
  const total = colours.length;
  let r = PREF_R;
  let cols = 1;
  for (;;) {
    const cell = 2 * r + GAP;
    cols = Math.max(1, Math.floor((CAVITY.w + GAP) / cell));
    const rows = Math.ceil(total / cols);
    if (rows * cell <= CAVITY.h + GAP || r <= 8) break;
    r -= 0.6;
  }
  const cell = 2 * r + GAP;
  const usedRows = Math.ceil(total / cols);
  return colours.map((colour, i) => {
    const rowFromBottom = Math.floor(i / cols);
    const idxInRow = i % cols;
    const countInRow = rowFromBottom === usedRows - 1 ? total - rowFromBottom * cols : cols;
    const rowWidth = countInRow * cell - GAP;
    const rowLeft = CAVITY.x + (CAVITY.w - rowWidth) / 2;
    const cx = rowLeft + idxInRow * cell + r;
    const cy = CAVITY.y + CAVITY.h - (rowFromBottom * cell + r + 4);
    // Tiny deterministic jitter so the pile feels hand-placed, not gridded.
    const sd = (i * 2654435761) % 1000;
    const jx = ((sd % 7) - 3) * 0.5;
    const jy = (((sd >> 3) % 7) - 3) * 0.4;
    return { cx: cx + jx, cy: cy + jy, r, colour };
  });
}

function describe(stimulus: SetModelStimulusView): string {
  const groups = stimulus.groups.map((g) => `${String(g.count)} ${g.colour}`).join(' and ');
  return `A jar of counters: ${groups}.`;
}

function Marble({ p, idp }: { p: Placement; idp: string }): React.JSX.Element {
  const c = PALETTE[p.colour] ?? FALLBACK;
  return (
    <g data-colour={p.colour}>
      {/* contact shadow */}
      <ellipse cx={p.cx} cy={p.cy + p.r * 0.78} rx={p.r * 0.78} ry={p.r * 0.26} fill="rgba(58,44,28,0.16)" />
      {/* marble body, painted with a per-colour radial gradient */}
      <circle
        className="wm-setmodel-counter"
        cx={p.cx}
        cy={p.cy}
        r={p.r}
        fill={`url(#${idp}-cg-${p.colour})`}
        stroke={c.stroke}
        strokeWidth={1.6}
        strokeOpacity={0.85}
      />
      {/* glossy highlight */}
      <ellipse
        cx={p.cx - p.r * 0.32}
        cy={p.cy - p.r * 0.38}
        rx={p.r * 0.34}
        ry={p.r * 0.24}
        fill="rgba(255,255,255,0.72)"
        transform={`rotate(-22 ${String(p.cx - p.r * 0.32)} ${String(p.cy - p.r * 0.38)})`}
      />
    </g>
  );
}

export function SetModelStimulus({ problem }: { problem: ProblemView }): React.JSX.Element | null {
  const stimulus = problem.set_model;
  if (stimulus == null) return null;
  // Namespace gradient/clip ids per problem so two jars on a page never collide.
  const idp = `sm-${problem.problem_id.replace(/[^a-zA-Z0-9_-]/g, '')}`;
  const placements = packCounters(mixedColours(stimulus.groups));
  const distinctColours = [...new Set(stimulus.groups.map((g) => g.colour))];
  return (
    <figure className="wm-setmodel">
      <svg
        className="wm-setmodel-svg"
        viewBox={`0 0 ${String(VB_W)} ${String(VB_H)}`}
        role="img"
        aria-label={describe(stimulus)}
      >
        <defs>
          <linearGradient id={`${idp}-glass`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="rgba(255,255,255,0.55)" />
            <stop offset="0.18" stopColor="rgba(255,255,255,0.16)" />
            <stop offset="0.55" stopColor="rgba(214,236,247,0.10)" />
            <stop offset="0.85" stopColor="rgba(120,150,200,0.14)" />
            <stop offset="1" stopColor="rgba(80,100,150,0.20)" />
          </linearGradient>
          <linearGradient id={`${idp}-cork`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#d9a86a" />
            <stop offset="0.5" stopColor="#c08a48" />
            <stop offset="1" stopColor="#9c6a30" />
          </linearGradient>
          <linearGradient id={`${idp}-rim`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fbf5e6" />
            <stop offset="1" stopColor="#e7dcc1" />
          </linearGradient>
          {distinctColours.map((colour) => {
            const c = PALETTE[colour] ?? FALLBACK;
            return (
              <radialGradient key={colour} id={`${idp}-cg-${colour}`} cx="0.36" cy="0.30" r="0.85">
                <stop offset="0" stopColor={c.light} />
                <stop offset="0.45" stopColor={c.fill} />
                <stop offset="1" stopColor={c.dark} />
              </radialGradient>
            );
          })}
          <clipPath id={`${idp}-clip`}>
            <path d={CAVITY_PATH} />
          </clipPath>
        </defs>

        {/* ground shadow under the jar */}
        <ellipse cx={VB_W / 2} cy={290} rx={76} ry={12} fill="rgba(58,44,28,0.16)" />

        {/* glass body — warm ink outline on a faint glass fill, then a tint/sheen on top */}
        <path d={BODY_PATH} className="wm-setmodel-glass" />
        <path d={BODY_PATH} fill={`url(#${idp}-glass)`} />

        {/* counters, clipped to the interior so none spills past the glass walls */}
        <g clipPath={`url(#${idp}-clip)`}>
          {placements.map((p, i) => (
            <Marble key={`${p.colour}-${String(i)}`} p={p} idp={idp} />
          ))}
        </g>

        {/* neck rim + cork lid on top of everything */}
        <rect
          x={78}
          y={96}
          width={104}
          height={18}
          rx={8}
          fill={`url(#${idp}-rim)`}
          className="wm-setmodel-ink"
          strokeWidth={3}
          strokeLinejoin="round"
        />
        <path
          d="M 96 96 q 0 -30 34 -30 q 34 0 34 30 Z"
          fill={`url(#${idp}-cork)`}
          className="wm-setmodel-ink"
          strokeWidth={3.2}
          strokeLinejoin="round"
        />
        <path
          d="M 104 78 q 26 -14 52 0"
          fill="none"
          stroke="rgba(255,240,210,0.6)"
          strokeWidth={2.4}
          strokeLinecap="round"
        />
      </svg>
      <figcaption className="wm-setmodel-caption">
        {stimulus.groups.map((g) => `${String(g.count)} ${g.colour}`).join(' · ')}
      </figcaption>
    </figure>
  );
}
