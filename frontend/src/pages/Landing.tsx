import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Mascot } from '../components/Mascot';
import './Landing.css';

const ROLL_MS = 900;
const ROLL_MS_REDUCED = 320;

function prefersReducedMotion(): boolean {
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  return mq?.matches ?? false;
}

const Sparkle = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
  </svg>
);

/**
 * The WhollyMath landing / hero (brand register). A faithful React port of the
 * approved hero mock: the brand pie turns slowly, the pie mascot idle-bobs, and
 * either entry — the "Start learning" student CTA or the quiet "For teachers &
 * families" link — makes the mascot crouch, jump, and roll off-screen before
 * handing off ({@link onStart} into the tutor, or /welcome for the role-select).
 * Honors prefers-reduced-motion.
 */
export function Landing({ onStart }: { onStart: () => void }): React.JSX.Element {
  const [starting, setStarting] = useState(false);
  const firedRef = useRef(false);
  const navigate = useNavigate();

  // Roll the mascot off-screen, then run `action` (the hand-off). Shared by BOTH entries — the
  // student "Start learning" CTA and the quiet "For teachers & families" link — so either one
  // gets the same crouch-jump-roll send-off before navigating. `starting`/`firedRef` guard against
  // a double trigger, so whichever entry is pressed first wins and the other is inert.
  function rollOffThen(action: () => void): void {
    if (starting) {
      return;
    }
    setStarting(true);
    const delay = prefersReducedMotion() ? ROLL_MS_REDUCED : ROLL_MS;
    window.setTimeout(() => {
      if (firedRef.current) {
        return;
      }
      firedRef.current = true;
      action();
    }, delay);
  }

  return (
    <div className={`wm-landing${starting ? ' wm-landing--starting' : ''}`}>
      <div className="wm-hero">
        <div className="wm-brand">
          <div className="wm-brand-mark" aria-hidden="true" />
          <div className="wm-brand-name">WhollyMath</div>
        </div>

        <div className="wm-sparkle wm-s1">
          <Sparkle />
        </div>
        <div className="wm-sparkle wm-s2">
          <Sparkle />
        </div>
        <div className="wm-sparkle wm-s3">
          <Sparkle />
        </div>

        <div className="wm-copy">
          <h1 className="wm-headline">
            Math, made <em>whole.</em>
          </h1>
          <p className="wm-subhead">
            A tutor for 6th graders!
            <br />
            The workspace adapts to how your child is thinking.
          </p>

          <div className="wm-cta-card">
            <div className="wm-cta-title">
              Student access
              <br />
              starts here.
            </div>
            <button
              type="button"
              className="wm-cta-btn"
              onClick={() => {
                rollOffThen(onStart);
              }}
            >
              Start learning as a student
            </button>
          </div>

          {/* Secondary entry for adults — a quiet link (not a second CTA), so the student path
              stays the hero. Points at the /welcome role-select; the label names BOTH audiences
              the role-select splits into (teacher vs parent) so neither feels excluded. */}
          <Link
            className="wm-teacher-link"
            to="/welcome"
            onClick={(e) => {
              // Keep the href for middle-click / open-in-new-tab, but on a normal click roll the
              // mascot off first (matching the student CTA) before navigating to the role-select.
              e.preventDefault();
              rollOffThen(() => {
                navigate('/welcome');
              });
            }}
          >
            For teachers &amp; families
            <span aria-hidden="true"> →</span>
          </Link>
        </div>

        <div className="wm-numberline" aria-hidden="true">
          <svg viewBox="0 0 480 120">
            <line
              x1="10"
              y1="80"
              x2="470"
              y2="80"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            <polyline
              points="20,72 10,80 20,88"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <polyline
              points="460,72 470,80 460,88"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            <g stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="70" y1="74" x2="70" y2="86" />
              <line x1="150" y1="74" x2="150" y2="86" />
              <line x1="230" y1="74" x2="230" y2="86" />
              <line x1="310" y1="74" x2="310" y2="86" />
              <line x1="390" y1="74" x2="390" y2="86" />
              <line x1="450" y1="74" x2="450" y2="86" />
            </g>
            <g fill="currentColor" fontSize="22" textAnchor="middle">
              <text x="70" y="112">
                0
              </text>
              <text x="150" y="112">
                1
              </text>
              <text x="230" y="112">
                2
              </text>
              <text x="310" y="112">
                3
              </text>
              <text x="390" y="112">
                4
              </text>
              <text x="450" y="112">
                5
              </text>
            </g>
            <g fill="currentColor" fontSize="22" textAnchor="middle">
              <text x="90" y="44">
                1
              </text>
              <line x1="80" y1="50" x2="100" y2="50" stroke="currentColor" strokeWidth="2" />
              <text x="90" y="70">
                4
              </text>
              <text x="130" y="36">
                3
              </text>
              <line x1="120" y1="42" x2="140" y2="42" stroke="currentColor" strokeWidth="2" />
              <text x="130" y="62">
                4
              </text>
            </g>
          </svg>
        </div>

        <div className="wm-tiles" aria-hidden="true">
          <div className="wm-tiles-box">
            <div className="wm-tile wm-t1">
              <span className="wm-frac">
                <span className="wm-num">1</span>
                <span className="wm-den">4</span>
              </span>
            </div>
            <div className="wm-tile wm-t2">
              <span className="wm-frac">
                <span className="wm-num">1</span>
                <span className="wm-den">4</span>
              </span>
            </div>
            <div className="wm-tile wm-t3">
              <span className="wm-frac">
                <span className="wm-num">3</span>
                <span className="wm-den">4</span>
              </span>
            </div>
          </div>
        </div>

        <div className={`wm-mascot${starting ? ' wm-mascot--rolling' : ''}`} aria-hidden="true">
          <div className="wm-speech">
            No more
            <br />
            guess and check!
          </div>
          <Mascot />
        </div>
      </div>
    </div>
  );
}
