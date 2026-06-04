import type { Emotion } from '@whollymath/shared-types';
import { useEffect, useId, useRef, useState } from 'react';

import type { Viseme } from './avatar/visemes';
import { Mascot } from './Mascot';
import './PiMenu.css';

/**
 * Pi's tap-to-open navigation menu — the global "home button" the reference mocks show
 * (the colorful pie mascot fans out a small set of nav choices). Tapping Pi opens a neat
 * stacked popover of speech-bubble buttons beside the mascot; tapping again, Escape, or a
 * click outside closes it, and choosing an item closes it and runs the item's action.
 *
 * Reusable across the Tutor header and the CourseMap header: the caller passes the items it
 * wants (Dashboard / Homework / Save & exit), so the same affordance carries every surface's
 * nav without each page re-implementing it. Pure nav — it owns no app state beyond open/closed.
 *
 * Presentation: a real <button> wraps the shared <Mascot> as the trigger (aria-haspopup="menu"
 * + aria-expanded); the popover is a role="menu" of role="menuitem" buttons. The mascot stays
 * the shared figure (so Landing/CourseMap/Tutor keep one character); only the wrapper is the
 * tappable trigger. Each item shows a small drawn (never emoji) glyph so color is never the
 * only cue. Motion is a short fade/rise that collapses to instant under prefers-reduced-motion.
 */

export interface PiMenuItem {
  /** Stable id for the React key + aria wiring. */
  id: string;
  /** The visible label (e.g. "Dashboard"). */
  label: string;
  /** Which drawn glyph to show beside the label. */
  icon: 'dashboard' | 'homework' | 'exit';
  /** Run when the item is chosen; the menu closes first. */
  onSelect: () => void;
}

// Drawn glyphs (never an emoji) — simple navy line marks that read at the bubble size and
// match the app's 2px-navy outline language. Decorative; the label carries the meaning.
function ItemIcon({ icon }: { icon: PiMenuItem['icon'] }): React.JSX.Element {
  const common = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  };
  if (icon === 'dashboard') {
    // a little house
    return (
      <svg {...common}>
        <path d="M4 11 L12 4 L20 11" />
        <path d="M6 10 V20 H18 V10" />
      </svg>
    );
  }
  if (icon === 'homework') {
    // a camera (the "scan paper" affordance)
    return (
      <svg {...common}>
        <path d="M4 8 H7 L8.5 6 H15.5 L17 8 H20 V18 H4 Z" />
        <circle cx="12" cy="13" r="3" />
      </svg>
    );
  }
  // exit — a door with an out-arrow
  return (
    <svg {...common}>
      <path d="M13 4 H6 V20 H13" />
      <path d="M10 12 H20" />
      <path d="M16 8 L20 12 L16 16" />
    </svg>
  );
}

export function PiMenu({
  items,
  label = 'Open the menu',
  onOpenChange,
  emotion,
  intensity,
  speaking = false,
  viseme = 'rest',
}: {
  /** The nav choices to fan out, in display order. An empty list renders no trigger. */
  items: PiMenuItem[];
  /** Accessible name for the trigger button (what tapping Pi does). */
  label?: string;
  /**
   * Notifies the caller when the menu opens/closes. The Tutor uses this to keep Pi's
   * help-speech bubble and this nav menu mutually exclusive (they share the mascot).
   */
  onOpenChange?: (open: boolean) => void;
  /** Live emotion to reflect on the shared mascot figure (Avatar Phase 0); omit for none. */
  emotion?: Emotion;
  /** How strongly to play `emotion`, a [0,1] scalar. */
  intensity?: number;
  /** True while the shared mascot is SPEAKING cached audio (Slice AR.3); drives the talking mouth. */
  speaking?: boolean;
  /** Current phoneme mouth shape for the shared mascot's lip-sync (from `useGuideSpeech`). */
  viseme?: Viseme;
}): React.JSX.Element | null {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const firstItemRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  // Click-outside closes; we listen only while open so the rest of the app pays nothing.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent): void {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  // When the menu opens, move focus to the first item (keyboard users land in the menu);
  // it returns to the trigger on close below.
  useEffect(() => {
    if (open) firstItemRef.current?.focus();
  }, [open]);

  // Surface open/closed to the caller (mutual exclusivity with the Tutor's help bubble).
  useEffect(() => {
    onOpenChange?.(open);
  }, [open, onOpenChange]);

  if (items.length === 0) return null;

  function close(focusTrigger: boolean): void {
    setOpen(false);
    if (focusTrigger) triggerRef.current?.focus();
  }

  function choose(item: PiMenuItem): void {
    close(false);
    item.onSelect();
  }

  return (
    <div
      className={`wm-pimenu ${open ? 'wm-pimenu--open' : ''}`}
      ref={rootRef}
      onKeyDown={(event) => {
        if (event.key === 'Escape' && open) {
          event.stopPropagation();
          close(true);
        }
      }}
    >
      <button
        type="button"
        ref={triggerRef}
        className="wm-pimenu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        aria-label={label}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="wm-pimenu-fig" aria-hidden="true">
          <Mascot emotion={emotion} intensity={intensity} speaking={speaking} viseme={viseme} />
        </span>
      </button>

      {open ? (
        <div className="wm-pimenu-pop" id={menuId} role="menu" aria-label={label}>
          {items.map((item, i) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              ref={i === 0 ? firstItemRef : undefined}
              className="wm-pimenu-item"
              onClick={() => choose(item)}
            >
              <span className="wm-pimenu-item-icon" aria-hidden="true">
                <ItemIcon icon={item.icon} />
              </span>
              <span className="wm-pimenu-item-label">{item.label}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
