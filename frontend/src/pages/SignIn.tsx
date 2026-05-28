import { useEffect, useRef, useState } from 'react';

import { Mascot } from '../components/Mascot';
import './SignIn.css';

/** How the learner chose to enter. Google is the real account path (OIDC, slice PL.3);
 * "demo" is the no-account guest path. For now both just advance to the decision page —
 * actual Google auth lands with PL.3. */
export type SignInMethod = 'google' | 'demo';

const ROLL_IN_MS = 1800;
const ROLL_OUT_MS = 2000;
const REDUCED_MS = 280;

function prefersReducedMotion(): boolean {
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  return mq?.matches ?? false;
}

const Sparkle = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
  </svg>
);

// The official Google "G" mark (four-colour), inlined so the button needs no asset.
const GoogleG = (): React.JSX.Element => (
  <svg viewBox="0 0 48 48" aria-hidden="true" className="wm-signin-gicon">
    <path
      fill="#4285F4"
      d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z"
    />
    <path
      fill="#34A853"
      d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z"
    />
    <path
      fill="#FBBC05"
      d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34A21.99 21.99 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z"
    />
    <path
      fill="#EA4335"
      d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7C13.42 14.62 18.27 10.75 24 10.75z"
    />
  </svg>
);

// A single running/jumping child for the number line — a little cartoon runner
// (filled body + coloured shirt + peach head), mid-stride, not a bare stick figure.
const RunningKid = ({
  x,
  y,
  shirt,
}: {
  x: number;
  y: number;
  shirt: string;
}): React.JSX.Element => (
  <g transform={`translate(${String(x)},${String(y)})`}>
    <g stroke="var(--wm-cream)" strokeWidth="3" strokeLinecap="round">
      <line x1="0" y1="-2" x2="-6" y2="11" />
      <line x1="0" y1="-2" x2="8" y2="9" />
      <line x1="0" y1="-13" x2="-9" y2="-17" />
      <line x1="0" y1="-13" x2="9" y2="-10" />
    </g>
    <rect x="-5.5" y="-16" width="11" height="15" rx="4.5" fill={shirt} />
    <circle cx="0" cy="-21" r="5.2" fill="#f6cda1" />
  </g>
);

/**
 * The sign-in / welcome page (brand register). Shown after "Start learning as a student"
 * on the landing, before the cold-start decision page. Recreates the approved welcome mock:
 * a cream hero with a white card offering two ways in (Google account or a free demo), over
 * a navy band with a number line of running children and the fraction tiles.
 *
 * The mascot rolls IN on mount and offers a one-line nudge to help the learner choose, then
 * rolls OUT when they pick an option, handing off to {@link onContinue} (→ the decision page).
 * Honors prefers-reduced-motion. Google is the real account path (OIDC) once slice PL.3 lands;
 * for now both options simply advance.
 */
export function SignIn({
  onContinue,
}: {
  onContinue: (method: SignInMethod) => void;
}): React.JSX.Element {
  const [entering, setEntering] = useState(true);
  const [leaving, setLeaving] = useState(false);
  const firedRef = useRef(false);

  useEffect(() => {
    const delay = prefersReducedMotion() ? REDUCED_MS : ROLL_IN_MS;
    const id = window.setTimeout(() => {
      setEntering(false);
    }, delay);
    return () => {
      window.clearTimeout(id);
    };
  }, []);

  function handleChoose(method: SignInMethod): void {
    if (leaving) {
      return;
    }
    setLeaving(true);
    const delay = prefersReducedMotion() ? REDUCED_MS : ROLL_OUT_MS;
    window.setTimeout(() => {
      if (firedRef.current) {
        return;
      }
      firedRef.current = true;
      onContinue(method);
    }, delay);
  }

  const mascotState = leaving
    ? ' wm-signin-mascot--leaving'
    : entering
      ? ' wm-signin-mascot--entering'
      : '';

  return (
    <div className={`wm-signin${leaving ? ' wm-signin--leaving' : ''}`}>
      <div className="wm-signin-stage">
        <div className="wm-signin-brand">
          <div className="wm-signin-mark" aria-hidden="true" />
          <div className="wm-signin-brandname">WhollyMath</div>
        </div>

        <div className="wm-signin-spark wm-signin-spark1">
          <Sparkle />
        </div>
        <div className="wm-signin-spark wm-signin-spark2">
          <Sparkle />
        </div>
        <div className="wm-signin-spark wm-signin-spark3">
          <Sparkle />
        </div>

        <div className="wm-signin-copy">
          <h1 className="wm-signin-headline">
            Welcome back, <em>explorer!</em>
          </h1>
          <p className="wm-signin-subhead">How would you like to sign in today?</p>

          <div className="wm-signin-card">
            <button
              type="button"
              className="wm-signin-google"
              onClick={() => {
                handleChoose('google');
              }}
            >
              Sign in with Google
              <GoogleG />
            </button>
            <button
              type="button"
              className="wm-signin-demo"
              onClick={() => {
                handleChoose('demo');
              }}
            >
              Student Demo Free
              <span className="wm-signin-tag" aria-hidden="true">
                ✦
              </span>
            </button>
          </div>
        </div>

        <div className="wm-signin-numberline" aria-hidden="true">
          <svg viewBox="0 0 480 140">
            <line
              x1="14"
              y1="100"
              x2="466"
              y2="100"
              stroke="var(--wm-blue-soft)"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <polyline
              points="24,92 14,100 24,108"
              fill="none"
              stroke="var(--wm-blue-soft)"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <polyline
              points="456,92 466,100 456,108"
              fill="none"
              stroke="var(--wm-blue-soft)"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <g
              stroke="var(--wm-blue-soft)"
              strokeWidth="2"
              strokeDasharray="4 5"
              strokeLinecap="round"
              fill="none"
            >
              <path d="M70 100 Q110 44 150 100" />
              <path d="M150 100 Q190 40 230 100" />
              <path d="M230 100 Q270 44 310 100" />
            </g>
            <g stroke="var(--wm-blue-soft)" strokeWidth="2.5" strokeLinecap="round">
              <line x1="70" y1="94" x2="70" y2="106" />
              <line x1="150" y1="94" x2="150" y2="106" />
              <line x1="230" y1="94" x2="230" y2="106" />
              <line x1="310" y1="94" x2="310" y2="106" />
              <line x1="390" y1="94" x2="390" y2="106" />
            </g>
            <g
              fill="var(--wm-blue-soft)"
              fontSize="20"
              textAnchor="middle"
              fontFamily="var(--wm-font-hand)"
            >
              <text x="70" y="128">
                0
              </text>
              <text x="150" y="128">
                ¼
              </text>
              <text x="230" y="128">
                ½
              </text>
              <text x="310" y="128">
                ¾
              </text>
              <text x="390" y="128">
                1
              </text>
            </g>
            <RunningKid x={110} y={62} shirt="var(--wm-coral)" />
            <RunningKid x={190} y={58} shirt="var(--wm-yellow)" />
            <RunningKid x={270} y={62} shirt="var(--wm-pink)" />
          </svg>
        </div>

        <div className="wm-signin-tiles" aria-hidden="true">
          <div className="wm-signin-tiles-box">
            <div className="wm-signin-tile wm-signin-tile1">
              <span className="wm-signin-frac">
                <span className="wm-signin-num">1</span>
                <span className="wm-signin-den">4</span>
              </span>
            </div>
            <div className="wm-signin-tile wm-signin-tile2">
              <span className="wm-signin-frac">
                <span className="wm-signin-num">1</span>
                <span className="wm-signin-den">2</span>
              </span>
            </div>
            <div className="wm-signin-tile wm-signin-tile3">
              <span className="wm-signin-frac">
                <span className="wm-signin-num">3</span>
                <span className="wm-signin-den">4</span>
              </span>
            </div>
          </div>
        </div>

        <div className={`wm-signin-mascot${mascotState}`} aria-hidden="true">
          <div className="wm-signin-speech">
            Sign in to save
            <br />
            your spot — or jump in free!
          </div>
          <Mascot />
        </div>
      </div>
    </div>
  );
}
