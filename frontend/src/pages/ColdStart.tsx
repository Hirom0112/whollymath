import './ColdStart.css';

/**
 * The Turn-0 routing screen (the kid-friendly cold start, locked in PROJECT.md
 * decision 0.D.2). Sits inside a "world" — a stylized fantasy-landscape backdrop
 * with a centered cream panel holding three chunky side-by-side option cards
 * and a de-emphasized "I'm not sure" link below. The polymath-card pattern
 * (icon + label, soft per-card tints) gives the screen a warm, game-feel
 * register that follows naturally from the landing.
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
  /** Inline SVG icon (~44px) representing the KC concept. */
  icon: React.JSX.Element;
}

const ICON_COMBINE = (
  <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false">
    <rect x="6" y="10" width="14" height="28" rx="2.5" stroke="currentColor" strokeWidth="2.5" />
    <rect x="28" y="10" width="14" height="28" rx="2.5" stroke="currentColor" strokeWidth="2.5" />
    <line
      x1="22"
      y1="24"
      x2="26"
      y2="24"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
    <line
      x1="24"
      y1="22"
      x2="24"
      y2="26"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
  </svg>
);

const ICON_SAME_AMOUNT = (
  <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false">
    <circle cx="12" cy="24" r="9" stroke="currentColor" strokeWidth="2.5" />
    <line x1="12" y1="15" x2="12" y2="33" stroke="currentColor" strokeWidth="2.5" />
    <circle cx="36" cy="24" r="9" stroke="currentColor" strokeWidth="2.5" />
    <line x1="27" y1="24" x2="45" y2="24" stroke="currentColor" strokeWidth="2.5" />
    <line
      x1="19"
      y1="22"
      x2="29"
      y2="22"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
    <line
      x1="19"
      y1="26"
      x2="29"
      y2="26"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
  </svg>
);

const ICON_WHERE_ON_LINE = (
  <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false">
    <line
      x1="6"
      y1="32"
      x2="42"
      y2="32"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
    <line x1="10" y1="28" x2="10" y2="36" stroke="currentColor" strokeWidth="2.2" />
    <line x1="20" y1="28" x2="20" y2="36" stroke="currentColor" strokeWidth="2.2" />
    <line x1="30" y1="28" x2="30" y2="36" stroke="currentColor" strokeWidth="2.2" />
    <line x1="40" y1="28" x2="40" y2="36" stroke="currentColor" strokeWidth="2.2" />
    <path d="M28 14 L34 22 L22 22 Z" fill="currentColor" />
    <line
      x1="28"
      y1="22"
      x2="28"
      y2="30"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
    />
  </svg>
);

const KC_CHOICES: readonly RouteChoice[] = [
  {
    key: 'combine',
    prompt: 'Putting two fraction pieces together to see how much you have',
    tint: 'combine',
    icon: ICON_COMBINE,
  },
  {
    key: 'same_amount',
    prompt: 'Telling when two different-looking fractions are really the same amount',
    tint: 'same_amount',
    icon: ICON_SAME_AMOUNT,
  },
  {
    key: 'where_on_line',
    prompt: 'Finding where a fraction sits on a line between 0 and 1',
    tint: 'where_on_line',
    icon: ICON_WHERE_ON_LINE,
  },
] as const;

// Mirrors backend/app/tutor/session.py UNSURE_ROUTE.prompt verbatim (the
// previous commit fixed the em dash so the strings match byte-for-byte).
const UNSURE_PROMPT = "I'm not sure, just show me something";

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
                <span className="wm-coldstart-icon">{choice.icon}</span>
                <span className="wm-coldstart-card-text">{choice.prompt}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="wm-coldstart-unsure-wrap">
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
