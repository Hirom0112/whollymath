import type { CSSProperties } from 'react';

import './ColdStart.css';

// Lets us pass the per-item entrance-stagger delay through a CSS custom property
// without `any`. CSSProperties does not type custom properties; the indexed-record
// shape is the standard React-with-strict TS pattern.
type CSSVarStyle = CSSProperties & Record<`--${string}`, string>;

/**
 * The Turn-0 routing screen (the kid-friendly cold start, locked in PROJECT.md
 * decision 0.D.2). This is the first product surface — the calm, composed register
 * (PRODUCT.md), not the warm landing brand. Three equal-weight KC options + one
 * de-emphasized "I'm not sure" default. NO diagnostic / quiz framing, NO curriculum
 * terms. The kid-friendly prompts mirror the backend source of truth in
 * backend/app/tutor/session.py (RouteOption.prompt) so the surface and the tutor
 * agree on the menu without string drift.
 *
 * The four route keys here ARE the backend's RouteOption.key values:
 *   - 'combine'        → KC_addition_unlike
 *   - 'same_amount'    → KC_equivalence
 *   - 'where_on_line'  → KC_number_line_placement
 *   - 'not_sure'       → de-emphasized default → equivalence (no skill claim)
 */
export type RouteKey = 'combine' | 'same_amount' | 'where_on_line' | 'not_sure';

interface RouteChoice {
  key: RouteKey;
  prompt: string;
}

// The three real KC options. Equal-weight (same visual treatment, in the order the
// backend lists them — combine / same_amount / where_on_line). Copy is verbatim
// from backend/app/tutor/session.py so a kid-friendly copy change happens in one
// place. The "I'm not sure" default is rendered separately, with de-emphasized
// chrome, because 0.D.2 requires it visually distinct.
const KC_CHOICES: readonly RouteChoice[] = [
  {
    key: 'combine',
    prompt: 'Putting two fraction pieces together to see how much you have',
  },
  {
    key: 'same_amount',
    prompt: 'Telling when two different-looking fractions are really the same amount',
  },
  {
    key: 'where_on_line',
    prompt: 'Finding where a fraction sits on a line between 0 and 1',
  },
] as const;

// The de-emphasized default. Copy mirrors the backend's UNSURE_ROUTE.prompt with
// ONE deliberate change: the backend uses an em dash ("I'm not sure — just show
// me something"); the impeccable design law forbids em dashes in copy, so the
// surface renders a comma. Flagged to the director — the backend string should
// likely be updated to match for one source of truth.
const UNSURE_PROMPT = "I'm not sure, just show me something";

export function ColdStart({
  onChoose,
}: {
  onChoose: (route: RouteKey) => void;
}): React.JSX.Element {
  return (
    <main className="wm-coldstart">
      <div className="wm-coldstart-inner">
        <header className="wm-coldstart-head">
          <p className="wm-coldstart-eyebrow">Step 1 of 2</p>
          <h1 className="wm-coldstart-headline">What do you want to work on?</h1>
          <p className="wm-coldstart-subhead">
            Pick what feels closest. You can change later, and nothing here is graded.
          </p>
        </header>

        <ul className="wm-coldstart-list">
          {KC_CHOICES.map((choice, index) => (
            <li key={choice.key} style={{ '--wm-stagger': `${index * 60}ms` } as CSSVarStyle}>
              <button
                type="button"
                className="wm-coldstart-card"
                onClick={() => {
                  onChoose(choice.key);
                }}
              >
                <span className="wm-coldstart-card-index" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="wm-coldstart-card-prompt">{choice.prompt}</span>
              </button>
            </li>
          ))}
        </ul>

        <div
          className="wm-coldstart-unsure-wrap"
          style={{ '--wm-stagger': `${KC_CHOICES.length * 60}ms` } as CSSVarStyle}
        >
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
