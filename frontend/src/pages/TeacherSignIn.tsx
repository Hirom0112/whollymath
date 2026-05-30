import './TeacherSignIn.css';

/**
 * Teacher sign-in gate (TODO TCH.F0 / TCH.Q1). A calm, professional entry — the adult
 * counterpart to the kid landing. Two ways in: a real Google/OIDC path (wired to lane T1's
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
      <div className="wm-tsignin-card">
        <div className="wm-tsignin-brand">
          <span className="wm-tsignin-mark" aria-hidden="true" />
          <span className="wm-tsignin-name">WhollyMath</span>
          <span className="wm-tsignin-role">Teacher</span>
        </div>

        <h1 className="wm-tsignin-headline">See your class at a glance.</h1>
        <p className="wm-tsignin-sub">
          Who needs help first, why they’re stuck, and what to assign next, built on the same
          mastery evidence your students earn.
        </p>

        <div className="wm-tsignin-actions">
          <button type="button" className="wm-tsignin-google" onClick={onSignIn} disabled={busy}>
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
        ) : (
          <p className="wm-tsignin-note">The demo class is synthetic. No real student data.</p>
        )}
      </div>
    </div>
  );
}
