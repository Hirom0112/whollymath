// The teacher-surface app frame (TODO TCH.F4 shell). A persistent deep-navy/blue chrome shared by
// the roster (TCH.F2) and the student drill-in (TCH.F3): a top bar (brand + role + teacher avatar)
// and a left side-nav (active class + sections + sign out). The page content renders in <main>.
//
// Landmark discipline (the page tests pin this): the shell contributes a <header> (banner), an
// <aside> (complementary), a <nav> (navigation), and a <main> (main) — NONE are role="region", so
// each page still owns exactly its own aria-labelled <section> regions. The side-nav links are
// <button>s whose names never contain "class", so they don't collide with a page's "Back to class"
// control. Class names are unique app-wide (`.wm-tshell-*`). Color is paired with icon + word.

import './TeacherShell.css';

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
      <path d="M3 9.5 12 3l9 6.5V20a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
      <path d="M9 22V12h6v10" />
    </svg>
  );
}

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
              <IconHome />
              Home
            </button>
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
