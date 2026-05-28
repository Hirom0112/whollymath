import { Mascot } from '../components/Mascot';
import './ColdStart.css';

/**
 * The Turn-0 routing screen (the kid-friendly cold start, locked in PROJECT.md
 * decision 0.D.2). Sits inside a "world" — a stylized fantasy-landscape backdrop
 * with a centered cream panel holding three big, chunky option cards. Each card
 * carries an illustration that SHOWS the concept (shaded fraction pies, a marker
 * on a number line) above the verbatim kid-friendly prompt, plus a friendly,
 * de-emphasized "get me started" button below.
 *
 * The four route keys here ARE the backend's RouteOption.key values
 * (backend/app/tutor/session.py); the prompts are mirrored verbatim from there
 * so the surface and the tutor agree on the menu without string drift.
 *
 *   - 'combine'        → KC_addition_unlike
 *   - 'same_amount'    → KC_equivalence
 *   - 'where_on_line'  → KC_number_line_placement
 *   - 'not_sure'       → de-emphasized default → equivalence (no skill claim)
 */
export type RouteKey = 'combine' | 'same_amount' | 'where_on_line' | 'not_sure';

interface RouteChoice {
  key: Exclude<RouteKey, 'not_sure'>;
  prompt: string;
  /** Per-card soft tint class — peach / mint / sky from tokens.css. */
  tint: 'combine' | 'same_amount' | 'where_on_line';
  /** Inline SVG illustration depicting the KC concept. */
  art: React.JSX.Element;
}

const NAVY = 'var(--wm-navy-deep)';

// "Combining": two pies each with a quarter shaded, joined by a plus — you put
// fraction pieces together.
const ART_COMBINE = (
  <svg viewBox="0 0 116 64" fill="none" aria-hidden="true" focusable="false">
    <circle cx="24" cy="32" r="19" fill="var(--wm-cream)" stroke={NAVY} strokeWidth="2.5" />
    <path
      d="M24 32 L24 13 A19 19 0 0 1 43 32 Z"
      fill="var(--wm-orange)"
      stroke={NAVY}
      strokeWidth="2.5"
      strokeLinejoin="round"
    />
    <line x1="52" y1="32" x2="64" y2="32" stroke={NAVY} strokeWidth="3.5" strokeLinecap="round" />
    <line x1="58" y1="26" x2="58" y2="38" stroke={NAVY} strokeWidth="3.5" strokeLinecap="round" />
    <circle cx="92" cy="32" r="19" fill="var(--wm-cream)" stroke={NAVY} strokeWidth="2.5" />
    <path
      d="M92 32 L92 13 A19 19 0 0 1 111 32 Z"
      fill="var(--wm-orange)"
      stroke={NAVY}
      strokeWidth="2.5"
      strokeLinejoin="round"
    />
  </svg>
);

// "Same amount": a half-pie equals a 2/4-pie — different splits, same shaded
// amount. The right pie carries both diameter lines so it reads as 4 pieces.
const ART_SAME_AMOUNT = (
  <svg viewBox="0 0 116 64" fill="none" aria-hidden="true" focusable="false">
    <circle cx="24" cy="32" r="19" fill="var(--wm-cream)" stroke={NAVY} strokeWidth="2.5" />
    <path
      d="M5 32 A19 19 0 0 1 43 32 Z"
      fill="var(--wm-pink)"
      stroke={NAVY}
      strokeWidth="2.5"
      strokeLinejoin="round"
    />
    <line x1="5" y1="32" x2="43" y2="32" stroke={NAVY} strokeWidth="2" />
    <line x1="52" y1="27" x2="64" y2="27" stroke={NAVY} strokeWidth="3.5" strokeLinecap="round" />
    <line x1="52" y1="37" x2="64" y2="37" stroke={NAVY} strokeWidth="3.5" strokeLinecap="round" />
    <circle cx="92" cy="32" r="19" fill="var(--wm-cream)" stroke={NAVY} strokeWidth="2.5" />
    <path
      d="M73 32 A19 19 0 0 1 111 32 Z"
      fill="var(--wm-pink)"
      stroke={NAVY}
      strokeWidth="2.5"
      strokeLinejoin="round"
    />
    <line x1="73" y1="32" x2="111" y2="32" stroke={NAVY} strokeWidth="2" />
    <line x1="92" y1="13" x2="92" y2="51" stroke={NAVY} strokeWidth="2" />
  </svg>
);

// "On the line": a 0-to-1 number line with quarter ticks and a placed marker pin.
const ART_WHERE_ON_LINE = (
  <svg viewBox="0 0 116 64" fill="none" aria-hidden="true" focusable="false">
    <line x1="14" y1="42" x2="102" y2="42" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
    <line x1="14" y1="36" x2="14" y2="48" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
    <line x1="102" y1="36" x2="102" y2="48" stroke={NAVY} strokeWidth="2.5" strokeLinecap="round" />
    <line x1="36" y1="38" x2="36" y2="46" stroke={NAVY} strokeWidth="1.8" />
    <line x1="58" y1="38" x2="58" y2="46" stroke={NAVY} strokeWidth="1.8" />
    <line x1="80" y1="38" x2="80" y2="46" stroke={NAVY} strokeWidth="1.8" />
    <text
      x="14"
      y="60"
      fontSize="11"
      fontFamily="var(--wm-font-sans)"
      fill={NAVY}
      textAnchor="middle"
    >
      0
    </text>
    <text
      x="102"
      y="60"
      fontSize="11"
      fontFamily="var(--wm-font-sans)"
      fill={NAVY}
      textAnchor="middle"
    >
      1
    </text>
    <path
      d="M80 42 L73 31 L87 31 Z"
      fill="var(--wm-blue-bright)"
      stroke={NAVY}
      strokeWidth="2.5"
      strokeLinejoin="round"
    />
    <circle cx="80" cy="22" r="10" fill="var(--wm-blue-bright)" stroke={NAVY} strokeWidth="2.5" />
  </svg>
);

const KC_CHOICES: readonly RouteChoice[] = [
  {
    key: 'combine',
    prompt: 'Putting two fraction pieces together to see how much you have',
    tint: 'combine',
    art: ART_COMBINE,
  },
  {
    key: 'same_amount',
    prompt: 'Telling when two different-looking fractions are really the same amount',
    tint: 'same_amount',
    art: ART_SAME_AMOUNT,
  },
  {
    key: 'where_on_line',
    prompt: 'Finding where a fraction sits on a line between 0 and 1',
    tint: 'where_on_line',
    art: ART_WHERE_ON_LINE,
  },
] as const;

// Mirrors backend/app/tutor/session.py UNSURE_ROUTE.prompt verbatim — friendly,
// low-pressure, and kept in sync so the surface and tutor agree byte-for-byte.
const UNSURE_PROMPT = 'Not sure yet? Just get me started!';

export function ColdStart({
  onChoose,
}: {
  onChoose: (route: RouteKey) => void;
}): React.JSX.Element {
  return (
    <main className="wm-coldstart">
      <div className="wm-coldstart-panel">
        <header className="wm-coldstart-head">
          <h1 className="wm-coldstart-headline">Where do you want to start?</h1>
          <p className="wm-coldstart-subhead">
            Pick a path. You can change later, and nothing here is graded.
          </p>
        </header>

        <ul className="wm-coldstart-list">
          {KC_CHOICES.map((choice) => (
            <li key={choice.key}>
              <button
                type="button"
                className={`wm-coldstart-card wm-coldstart-card--${choice.tint}`}
                onClick={() => {
                  onChoose(choice.key);
                }}
              >
                <span className="wm-coldstart-art">{choice.art}</span>
                <span className="wm-coldstart-card-text">{choice.prompt}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="wm-coldstart-unsure-wrap">
          <div className="wm-coldstart-mascot" aria-hidden="true">
            <Mascot />
          </div>
          <button
            type="button"
            className="wm-coldstart-unsure"
            onClick={() => {
              onChoose('not_sure');
            }}
          >
            {UNSURE_PROMPT}
          </button>
        </div>
      </div>
    </main>
  );
}
