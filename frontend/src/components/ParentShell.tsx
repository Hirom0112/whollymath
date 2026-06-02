// The parent-surface app frame (mirrors TeacherShell). A persistent deep-navy/blue chrome shared by
// the household dashboard, the child drill-in, and the add-child form: a top bar (brand + role +
// parent avatar) and a left side-nav (household block + sections + sign out). The page content
// renders in <main>.
//
// Landmark discipline (mirrors TeacherShell): the shell contributes a <header> (banner), an <aside>
// (complementary), a <nav> (navigation), and a <main> (main) — none are role="region", so each page
// owns its own aria-labelled <section> regions. Side-nav links are <button>s. Class names are unique
// app-wide (`.wm-pshell-*`); the shell reuses the generic `--wm-tshell-*` chrome tokens so dark mode
// works for free. The theme toggle is replicated here (the teacher's isn't exported) using the same
// `--wm-tshell-toggle-*` tokens, and it drives the shared ThemeContext, so the toggle is real.

import { useTheme } from '../state/ThemeContext';

import './ParentShell.css';

function IconSun(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function IconMoon(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  );
}

/** Sun/moon control in the top bar. Shows the icon for the theme you'd switch TO. */
function ThemeToggle(): React.JSX.Element {
  const { theme, toggle } = useTheme();
  const goingDark = theme === 'light';
  return (
    <button
      type="button"
      className="wm-pshell-theme-toggle"
      onClick={toggle}
      aria-label={goingDark ? 'Switch to dark theme' : 'Switch to light theme'}
      aria-pressed={theme === 'dark'}
    >
      {goingDark ? <IconMoon /> : <IconSun />}
    </button>
  );
}

function IconHome(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5 10v10h14V10" />
    </svg>
  );
}

function IconSettings(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 13a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
    </svg>
  );
}

// Genuinely-planned future section, shown as an honest "Soon" item so the nav maps to a real tool.
// Home (the household dashboard) is the active item above — we don't list it twice. We deliberately
// do NOT add fake/locked items (the lesson learned on the teacher nav: no redundant/dead nav).
const SECONDARY_NAV: { label: string; icon: React.JSX.Element }[] = [
  { label: 'Settings', icon: <IconSettings /> },
];

function IconSignOut(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

export function ParentShell({
  parentName = null,
  householdLabel = null,
  onHome,
  onSignOut,
  children,
}: {
  parentName?: string | null;
  householdLabel?: string | null;
  // Home navigation. When absent, the current page IS Home (the household dashboard), so the link
  // reads as the active page and is inert; when present (child detail / add-child), it returns home.
  onHome?: () => void;
  // Sign out. Optional: rendered only where the surface can actually end the session.
  onSignOut?: () => void;
  children: React.ReactNode;
}): React.JSX.Element {
  const initial = (parentName ?? 'P').trim().charAt(0).toUpperCase() || 'P';
  const homeIsActive = onHome === undefined;
  return (
    <div className="wm-pshell">
      <header className="wm-pshell-topbar">
        <span className="wm-pshell-brand">
          <span className="wm-pshell-pie" aria-hidden="true" />
          <span className="wm-pshell-brand-name">WhollyMath</span>
          <span className="wm-pshell-role">Parent</span>
        </span>
        <span className="wm-pshell-spacer" />
        <ThemeToggle />
        <span className="wm-pshell-avatar" aria-hidden="true">
          {initial}
        </span>
      </header>

      <div className="wm-pshell-body">
        <aside className="wm-pshell-side" aria-label="Parent navigation">
          <div className="wm-pshell-household">
            <span className="wm-pshell-household-avatar" aria-hidden="true">
              {initial}
            </span>
            <span className="wm-pshell-household-text">
              <span className="wm-pshell-household-name">{householdLabel ?? 'Your family'}</span>
              {parentName !== null ? (
                <span className="wm-pshell-household-meta">{parentName}</span>
              ) : null}
            </span>
          </div>

          <nav className="wm-pshell-nav" aria-label="Sections">
            <button
              type="button"
              className={`wm-pshell-link${homeIsActive ? ' wm-pshell-link--active' : ''}`}
              aria-current={homeIsActive ? 'page' : undefined}
              onClick={onHome}
              disabled={homeIsActive}
            >
              <IconHome />
              Home
            </button>
            {SECONDARY_NAV.map((item) => (
              <button
                key={item.label}
                type="button"
                className="wm-pshell-link wm-pshell-link--soon"
                disabled
                aria-disabled="true"
                title="Coming soon"
              >
                {item.icon}
                {item.label}
                <span className="wm-pshell-link-soon-tag">Soon</span>
              </button>
            ))}
          </nav>

          {onSignOut !== undefined ? (
            <div className="wm-pshell-nav wm-pshell-nav--footer">
              <button type="button" className="wm-pshell-link" onClick={onSignOut}>
                <IconSignOut />
                Sign out
              </button>
            </div>
          ) : null}
        </aside>

        <main className="wm-pshell-main">{children}</main>
      </div>
    </div>
  );
}
