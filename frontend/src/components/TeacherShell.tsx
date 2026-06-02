// The teacher-surface app frame (TODO TCH.F4 shell). A persistent deep-navy/blue chrome shared by
// the roster (TCH.F2) and the student drill-in (TCH.F3): a top bar (brand + role + teacher avatar)
// and a left side-nav (active class + sections + sign out). The page content renders in <main>.
//
// Landmark discipline (the page tests pin this): the shell contributes a <header> (banner), an
// <aside> (complementary), a <nav> (navigation), and a <main> (main) — NONE are role="region", so
// each page still owns exactly its own aria-labelled <section> regions. The side-nav links are
// <button>s whose names never contain "class", so they don't collide with a page's "Back to class"
// control. Class names are unique app-wide (`.wm-tshell-*`). Color is paired with icon + word.

import { useTheme } from '../state/ThemeContext';

import './TeacherShell.css';

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
      className="wm-tshell-theme-toggle"
      onClick={toggle}
      aria-label={goingDark ? 'Switch to dark theme' : 'Switch to light theme'}
      aria-pressed={theme === 'dark'}
    >
      {goingDark ? <IconMoon /> : <IconSun />}
    </button>
  );
}

function IconDashboard(): React.JSX.Element {
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
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  );
}

function IconLessons(): React.JSX.Element {
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
      <path d="M4 5a2 2 0 0 1 2-2h6v18H6a2 2 0 0 0-2 2Z" />
      <path d="M20 5a2 2 0 0 0-2-2h-6v18h6a2 2 0 0 1 2 2Z" />
    </svg>
  );
}

function IconReports(): React.JSX.Element {
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
      <path d="M5 3h9l5 5v13a0 0 0 0 1 0 0H5a0 0 0 0 1 0 0Z" />
      <path d="M14 3v5h5" />
      <path d="M8 13v4M12 11v6M16 14v3" />
    </svg>
  );
}

// Genuinely-planned future sections (NOT yet built), shown as honest "Soon" items so the nav maps
// to real tools. The dashboard/roster is the active Home item above — we don't list it again here
// (those were redundant duplicates of the page you're already on).
const SECONDARY_NAV: { label: string; icon: React.JSX.Element }[] = [
  { label: 'Lessons', icon: <IconLessons /> },
  { label: 'Reports', icon: <IconReports /> },
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

export function TeacherShell({
  teacherName = null,
  klassName = null,
  onHome,
  onSignOut,
  children,
}: {
  teacherName?: string | null;
  klassName?: string | null;
  // Home navigation. When absent, the current page IS Home (the roster), so the link reads as the
  // active page and is inert; when present (the drill-in), clicking it returns to the roster.
  onHome?: () => void;
  // Sign out. Optional: rendered only where the surface can actually end the session.
  onSignOut?: () => void;
  children: React.ReactNode;
}): React.JSX.Element {
  const initial = (teacherName ?? 'T').trim().charAt(0).toUpperCase() || 'T';
  const homeIsActive = onHome === undefined;
  return (
    <div className="wm-tshell">
      <header className="wm-tshell-topbar">
        <span className="wm-tshell-brand">
          <span className="wm-tshell-pie" aria-hidden="true" />
          <span className="wm-tshell-brand-name">WhollyMath</span>
          <span className="wm-tshell-role">Teacher</span>
        </span>
        <span className="wm-tshell-spacer" />
        <ThemeToggle />
        <span className="wm-tshell-avatar" aria-hidden="true">
          {initial}
        </span>
      </header>

      <div className="wm-tshell-body">
        <aside className="wm-tshell-side" aria-label="Teacher navigation">
          <div className="wm-tshell-class">
            <span className="wm-tshell-class-avatar" aria-hidden="true">
              {initial}
            </span>
            <span className="wm-tshell-class-text">
              <span className="wm-tshell-class-name">{klassName ?? 'Your class'}</span>
              {teacherName !== null ? (
                <span className="wm-tshell-class-meta">{teacherName}</span>
              ) : null}
            </span>
          </div>

          <nav className="wm-tshell-nav" aria-label="Sections">
            <button
              type="button"
              className={`wm-tshell-link${homeIsActive ? ' wm-tshell-link--active' : ''}`}
              aria-current={homeIsActive ? 'page' : undefined}
              onClick={onHome}
              disabled={homeIsActive}
            >
              <IconDashboard />
              Dashboard
            </button>
            {SECONDARY_NAV.map((item) => (
              <button
                key={item.label}
                type="button"
                className="wm-tshell-link wm-tshell-link--soon"
                disabled
                aria-disabled="true"
                title="Coming soon"
              >
                {item.icon}
                {item.label}
                <span className="wm-tshell-link-soon-tag">Soon</span>
              </button>
            ))}
          </nav>

          {onSignOut !== undefined ? (
            <div className="wm-tshell-nav wm-tshell-nav--footer">
              <button type="button" className="wm-tshell-link" onClick={onSignOut}>
                <IconSignOut />
                Sign out
              </button>
            </div>
          ) : null}
        </aside>

        <main className="wm-tshell-main">{children}</main>
      </div>
    </div>
  );
}
