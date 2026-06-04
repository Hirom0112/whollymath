// The bilingual HELP-language toggle (Slice 3.6 bilingual scaffold, V2_TODO §0.3).
//
// A single bottom-left control in the Tutor lesson view that flips the avatar's HINTS/NUDGES
// between English and Spanish (es-MX). Flipping it writes the choice through LocaleContext
// (persisted in localStorage), and because that locale rides every subsequent /turn request, the
// next hint/nudge comes back localized with NO page reload and NO session restart.
//
// SCOPE — what this DOES and DEFERS:
//   IN  : flip 'en' <-> 'es-MX', persist, so HINTS/NUDGES render in Spanish (CAPTIONS — es-MX
//         audio is not rendered yet, the intended v1 state).
//   OUT : "the avatar reads the whole PROBLEM aloud in Spanish" (Rung-0). That needs Spanish
//         problem-statement translation (Slice 3.2b, not built) and es-MX audio rendering
//         (Slice 3.5, not done). The on-screen PROBLEM stays English; only the help text
//         localizes. This component intentionally does NOT touch the problem statement.
//
// Accessibility: a real <button> with aria-pressed (pressed = Spanish active) and an aria-label,
// keyboard-operable by default, with a visible EN / ES label. Motion honors prefers-reduced-motion
// (the slide is disabled there, via the CSS).

import { useHelpLocale } from '../state/LocaleContext';
import './HelpLanguageToggle.css';

export function HelpLanguageToggle(): React.JSX.Element {
  const { locale, setLocale } = useHelpLocale();
  const spanish = locale === 'es-MX';

  return (
    <div className="wm-help-lang-toggle">
      <button
        type="button"
        className="wm-help-lang-toggle-btn"
        // pressed = Spanish is the active help-language (the non-default state).
        aria-pressed={spanish}
        aria-label={
          spanish
            ? 'Hint language: Spanish. Switch hints to English.'
            : 'Hint language: English. Switch hints to Spanish.'
        }
        onClick={() => {
          setLocale(spanish ? 'en' : 'es-MX');
        }}
      >
        <span
          className={`wm-help-lang-toggle-opt ${spanish ? '' : 'wm-help-lang-toggle-opt--on'}`}
          aria-hidden="true"
        >
          EN
        </span>
        <span className="wm-help-lang-toggle-sep" aria-hidden="true">
          /
        </span>
        <span
          className={`wm-help-lang-toggle-opt ${spanish ? 'wm-help-lang-toggle-opt--on' : ''}`}
          aria-hidden="true"
        >
          ES
        </span>
      </button>
      {/* The caption-only reality of v1: Spanish help is text. Stated plainly so the demo audience
          knows audio is the deferred rung, not a bug. */}
      <span className="wm-help-lang-toggle-note">
        {spanish ? 'Ayuda en español (texto)' : 'Help in English'}
      </span>
    </div>
  );
}
