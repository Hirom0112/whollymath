import './Mascot.css';

/**
 * The WhollyMath pie mascot — the reusable character figure (conic-gradient pie
 * face with eyes, smile, arms, legs). Pure presentation, no animation or
 * positioning of its own: callers wrap it and animate the wrapper (the landing's
 * idle-bob → roll-off, the cold-start's roll-in). Rendered at a base 130×100 box;
 * scale it via a transform on the wrapper. Decorative — always aria-hidden by the
 * caller's container.
 */
export function Mascot(): React.JSX.Element {
  return (
    <div className="wm-mascot-figure">
      <div className="wm-mascot-pie">
        <div className="wm-mascot-smile" />
      </div>
      <div className="wm-mascot-arm-l" />
      <div className="wm-mascot-arm-r" />
      <div className="wm-mascot-leg-l" />
      <div className="wm-mascot-leg-r" />
    </div>
  );
}
