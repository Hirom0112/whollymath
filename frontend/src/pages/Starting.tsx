import './Starting.css';

/**
 * The hand-off seam after the landing mascot rolls away. A brief, honest interstitial
 * on the navy field where the tutor's cold-start routing screen (Turn 0) will mount.
 * Intentionally minimal: this is a placeholder for the next build, not a faked tutor.
 */
export function Starting(): React.JSX.Element {
  return (
    <div className="wm-starting">
      <div className="wm-starting-mark" aria-hidden="true" />
      <p className="wm-starting-text">Setting up your workspace…</p>
    </div>
  );
}
