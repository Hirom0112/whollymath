import './WoodBanner.css';

/**
 * A storybook wooden banner frame. Renders a pre-made carved-wood PNG as a CSS 9-slice
 * (`border-image`) so the ornamental corners + rope trim stay sharp while only the plain
 * wood centre stretches to fit. The frame is purely decorative chrome — `children` (title,
 * icons, trackers) are layered on top of the recessed centre panel as live DOM, never baked
 * into the image (CLAUDE.md §8.5: clarity, and the meaning/text must stay real text).
 *
 * Two source assets (in `public/`, served at the root):
 *   - "wide"  banner_wide_transparent.png (1792×592) — flexible-width banners (default).
 *   - "long"  banner_long_transparent.png (2544×416) — the longer, thinner top header.
 *
 * The 9-slice numbers (border-width in render px, border-image-slice in image px) live in
 * WoodBanner.css per variant; `repeat: stretch` (NOT round — the grain is organic and tiling
 * seams) and the `fill` keyword (so the centre wood shows behind the content) are required.
 *
 * Plain global CSS + a `wm-`-prefixed class per the project convention (no CSS modules /
 * Tailwind / styled-components). Passes through `className`/`style` so callers can size and
 * position the banner without the component owning layout.
 */
export function WoodBanner({
  children,
  variant = 'wide',
  className = '',
  style,
}: {
  /** Content rendered on top of the wood centre (title, icons, tracker). */
  children: React.ReactNode;
  /** Which wood asset + 9-slice preset to use. Defaults to the flexible "wide" banner. */
  variant?: 'wide' | 'long';
  /** Merged onto the frame's class list (sizing / positioning by the caller). */
  className?: string;
  /** Merged onto the frame element. */
  style?: React.CSSProperties;
}): React.JSX.Element {
  return (
    <div className={`wm-woodbanner wm-woodbanner--${variant} ${className}`.trim()} style={style}>
      <div className="wm-woodbanner-content">{children}</div>
    </div>
  );
}
