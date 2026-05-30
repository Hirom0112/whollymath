import './TeacherSignIn.css';

/**
 * Teacher sign-in gate (TODO TCH.F0 / TCH.Q1). A calm, professional entry — the adult
 * counterpart to the kid landing. Split-panel layout (redesign, user 2026-05-30, from the
 * approved Gemini mock): a navy "world" panel on the left (geometric brand art + a floating
 * dashboard preview, recreated in pure CSS so it stays crisp and ships no raster asset) and a
 * white sign-in panel on the right. Two ways in: a real Google/OIDC path (wired to lane T1's
 * teacher auth, TCH.B2, once it lands) and a demo-teacher path that drops straight into the
 * seeded class for the pitch. Both call `onSignIn`; the container sets the demo token.
 */

const GoogleG = (): React.JSX.Element => (
  <svg viewBox="0 0 48 48" aria-hidden="true" className="wm-tsignin-gicon">
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

/** The floating dashboard preview that anchors the navy panel — a stylized, non-interactive
 *  abstraction of the real roster (ranked categories + a class-progress trend). Decorative
 *  chrome only, so it carries no live data and is hidden from assistive tech. */
const DashboardPreview = (): React.JSX.Element => {
  const rows: { tone: string; w: number; p: number }[] = [
    { tone: 'struggling', w: 62, p: 28 },
    { tone: 'attention', w: 74, p: 55 },
    { tone: 'attention', w: 54, p: 61 },
    { tone: 'ontrack', w: 70, p: 88 },
  ];
  return (
    <div className="wm-tsignin-preview" aria-hidden="true">
      <div className="wm-tsignin-pv-rail">
        <span className="wm-tsignin-pv-mark" />
        <span />
        <span />
        <span />
      </div>
      <div className="wm-tsignin-pv-body">
        <div className="wm-tsignin-pv-head">
          <span className="wm-tsignin-pv-title">Dashboard</span>
          <span className="wm-tsignin-pv-dot" />
        </div>
        <div className="wm-tsignin-pv-stats">
          <div className="wm-tsignin-pv-stat">
            <span className="wm-tsignin-pv-big">200</span>
            <span className="wm-tsignin-pv-cap" />
          </div>
          <div className="wm-tsignin-pv-stat wm-tsignin-pv-stat-sm">
            <span className="wm-tsignin-pv-mid">13%</span>
            <span className="wm-tsignin-pv-cap" />
          </div>
          <div className="wm-tsignin-pv-stat wm-tsignin-pv-stat-sm">
            <span className="wm-tsignin-pv-mid">15%</span>
            <span className="wm-tsignin-pv-cap" />
          </div>
        </div>
        <svg className="wm-tsignin-pv-chart" viewBox="0 0 200 64" preserveAspectRatio="none">
          <defs>
            <linearGradient id="wm-pv-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--wm-blue-bright)" stopOpacity="0.34" />
              <stop offset="100%" stopColor="var(--wm-blue-bright)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <path
            d="M0 50 L28 44 L56 47 L84 32 L112 36 L140 20 L168 24 L200 10 L200 64 L0 64 Z"
            fill="url(#wm-pv-fill)"
          />
          <path
            d="M0 50 L28 44 L56 47 L84 32 L112 36 L140 20 L168 24 L200 10"
            fill="none"
            stroke="var(--wm-blue-bright)"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <ul className="wm-tsignin-pv-rows">
          {rows.map((r, i) => (
            <li key={i} className="wm-tsignin-pv-row">
              <span className={`wm-tsignin-pv-pip wm-tsignin-pv-pip-${r.tone}`} />
              <span className="wm-tsignin-pv-bar" style={{ width: `${r.w}%` }} />
              <span className="wm-tsignin-pv-prog">
                <span style={{ width: `${r.p}%` }} />
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export function TeacherSignIn({
  onSignIn,
  busy = false,
  error = null,
}: {
  onSignIn: () => void;
  busy?: boolean;
  error?: string | null;
}): React.JSX.Element {
  return (
    <div className="wm-tsignin">
      <aside className="wm-tsignin-art" aria-hidden="true">
        <DashboardPreview />
      </aside>

      <main className="wm-tsignin-panel">
        <div className="wm-tsignin-inner">
          <div className="wm-tsignin-brand">
            <span className="wm-tsignin-mark" aria-hidden="true" />
            <span className="wm-tsignin-name">WhollyMath</span>
            <span className="wm-tsignin-role">Teacher</span>
          </div>

          <div className="wm-tsignin-body">
            <h1 className="wm-tsignin-headline">
              See your class
              <br />
              at a glance.
            </h1>
            <ul className="wm-tsignin-points">
              <li>Who needs help first</li>
              <li>Why they’re stuck</li>
              <li>What to assign next</li>
            </ul>
            <p className="wm-tsignin-sub">
              Straight from your students’ real work
              <br />
              No guesswork
            </p>

            <div className="wm-tsignin-actions">
              <button
                type="button"
                className="wm-tsignin-google"
                onClick={onSignIn}
                disabled={busy}
              >
                <GoogleG />
                Sign in with Google
              </button>
              <button type="button" className="wm-tsignin-demo" onClick={onSignIn} disabled={busy}>
                {busy ? 'Starting…' : 'Continue as a demo teacher'}
              </button>
            </div>

            {error !== null ? (
              <p className="wm-tsignin-error" role="alert">
                {error}
              </p>
            ) : null}
          </div>

          <p className="wm-tsignin-note">The demo class is synthetic. No real student data.</p>
        </div>
      </main>
    </div>
  );
}
