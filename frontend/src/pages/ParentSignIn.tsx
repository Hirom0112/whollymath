import './ParentSignIn.css';

/**
 * Parent sign-in gate (mirrors TeacherSignIn). The warm adult counterpart to the kid landing, in
 * the same split-panel register: a navy "world" panel on the left (a single warm child-progress
 * preview, recreated in pure CSS so it ships no raster asset) beside a cream sign-in panel on the
 * right. Two ways in: a real Google/OIDC path (wired once parent auth lands) and a demo path that
 * drops straight into the seeded household. Both call `onSignIn`; the container sets the demo token.
 * Unique classes app-wide (`.wm-psignin-*`); reuses the shared brand tokens.
 */

const GoogleG = (): React.JSX.Element => (
  <svg viewBox="0 0 48 48" aria-hidden="true" className="wm-psignin-gicon">
    <path
      fill="#4285F4"
      d="M45.12 24.5c0-1.56-.14-3.06-.4-4.5H24v8.51h11.84c-.51 2.75-2.06 5.08-4.39 6.64v5.52h7.11c4.16-3.83 6.56-9.47 6.56-16.17z"
    />
    <path
      fill="#34A853"
      d="M24 46c5.94 0 10.92-1.97 14.56-5.33l-7.11-5.52c-1.97 1.32-4.49 2.1-7.45 2.1-5.73 0-10.58-3.87-12.31-9.07H4.34v5.7C7.96 41.07 15.4 46 24 46z"
    />
    <path
      fill="#FBBC05"
      d="M11.69 28.18C11.25 26.86 11 25.45 11 24s.25-2.86.69-4.18v-5.7H4.34A21.99 21.99 0 0 0 2 24c0 3.55.85 6.91 2.34 9.88l7.35-5.7z"
    />
    <path
      fill="#EA4335"
      d="M24 10.75c3.23 0 6.13 1.11 8.41 3.29l6.31-6.31C34.91 4.18 29.93 2 24 2 15.4 2 7.96 6.93 4.34 14.12l7.35 5.7C13.42 14.62 18.27 10.75 24 10.75z"
    />
  </svg>
);

/** The floating child-progress preview that anchors the navy panel — a stylized, non-interactive
 *  abstraction of one child's card (name + accuracy trend + a "doing great" / "needs help" split).
 *  Decorative chrome only, so it carries no live data and is hidden from assistive tech. */
const ChildPreview = (): React.JSX.Element => (
  <div className="wm-psignin-preview" aria-hidden="true">
    <div className="wm-psignin-pv-head">
      <span className="wm-psignin-pv-avatar" />
      <span className="wm-psignin-pv-headtext">
        <span className="wm-psignin-pv-name" />
        <span className="wm-psignin-pv-grade" />
      </span>
      <span className="wm-psignin-pv-badge" />
    </div>
    <svg className="wm-psignin-pv-chart" viewBox="0 0 200 64" preserveAspectRatio="none">
      <defs>
        <linearGradient id="wm-ppv-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--wm-mean-correct)" stopOpacity="0.34" />
          <stop offset="100%" stopColor="var(--wm-mean-correct)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0 48 L28 44 L56 38 L84 40 L112 30 L140 24 L168 18 L200 10 L200 64 L0 64 Z"
        fill="url(#wm-ppv-fill)"
      />
      <path
        d="M0 48 L28 44 L56 38 L84 40 L112 30 L140 24 L168 18 L200 10"
        fill="none"
        stroke="var(--wm-mean-correct)"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
    <ul className="wm-psignin-pv-rows">
      <li className="wm-psignin-pv-row">
        <span className="wm-psignin-pv-pip wm-psignin-pv-pip-good" />
        <span className="wm-psignin-pv-bar" style={{ width: '70%' }} />
      </li>
      <li className="wm-psignin-pv-row">
        <span className="wm-psignin-pv-pip wm-psignin-pv-pip-help" />
        <span className="wm-psignin-pv-bar" style={{ width: '46%' }} />
      </li>
    </ul>
  </div>
);

export function ParentSignIn({
  onSignIn,
  busy = false,
  error = null,
}: {
  onSignIn: () => void;
  busy?: boolean;
  error?: string | null;
}): React.JSX.Element {
  return (
    <div className="wm-psignin">
      <aside className="wm-psignin-art" aria-hidden="true">
        <ChildPreview />
      </aside>

      <main className="wm-psignin-panel">
        <div className="wm-psignin-inner">
          <div className="wm-psignin-brand">
            <span className="wm-psignin-mark" aria-hidden="true" />
            <span className="wm-psignin-name">WhollyMath</span>
            <span className="wm-psignin-role">Parent</span>
          </div>

          <div className="wm-psignin-body">
            <div className="wm-psignin-lead">
              <h1 className="wm-psignin-headline">
                See your child&rsquo;s
                <br />
                <span className="wm-psignin-accent">progress</span> at a glance.
              </h1>
              <ul className="wm-psignin-points">
                <li>What they worked on today</li>
                <li>Where they&rsquo;re doing great &mdash; and where they need help</li>
                <li>Simple ideas to practice together at home</li>
              </ul>
            </div>

            <div className="wm-psignin-actions">
              <button
                type="button"
                className="wm-psignin-google"
                onClick={onSignIn}
                disabled={busy}
              >
                <GoogleG />
                Sign in with Google
              </button>
              <button type="button" className="wm-psignin-demo" onClick={onSignIn} disabled={busy}>
                {busy ? 'Starting…' : 'Try a parent demo'}
              </button>
            </div>

            {error !== null ? (
              <p className="wm-psignin-error" role="alert">
                {error}
              </p>
            ) : null}
          </div>

          <p className="wm-psignin-note">The demo uses sample children. No real student data.</p>
        </div>
      </main>
    </div>
  );
}
