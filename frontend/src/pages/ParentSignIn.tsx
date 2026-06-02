import './ParentSignIn.css';

/**
 * Parent sign-in gate (mirrors TeacherSignIn). The warm adult counterpart to the kid landing, in a
 * split-panel register: a cosmic "world" panel on the left — our starfield (public/parent-cosmos.jpg)
 * carrying three floating preview cards (today's focus, skill mastery, practice suggestions),
 * recreated in pure CSS/SVG so they ship no live data — beside a cream sign-in panel on the right.
 * Two ways in: a real Google/OIDC path (wired once parent auth lands) and a demo path that drops
 * straight into the seeded household. Both call `onSignIn`; the container sets the demo token. The
 * brand mark is our own WhollyMath pie, rotating. Unique classes app-wide (`.wm-psignin-*`).
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

/** Card 1: a today's-focus snapshot — an upward accuracy trend with a "doing great" tag + a bar. */
const FocusCard = (): React.JSX.Element => (
  <div className="wm-psignin-card wm-psignin-card-focus" aria-hidden="true">
    <p className="wm-psignin-card-title">Today&rsquo;s Focus</p>
    <svg className="wm-psignin-spark" viewBox="0 0 200 70" preserveAspectRatio="none">
      <defs>
        <linearGradient id="wm-ppv-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--wm-mean-correct)" stopOpacity="0.32" />
          <stop offset="100%" stopColor="var(--wm-mean-correct)" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path
        d="M0 54 L26 46 L52 50 L78 30 L104 40 L130 22 L156 26 L200 8 L200 70 L0 70 Z"
        fill="url(#wm-ppv-fill)"
      />
      <path
        d="M0 54 L26 46 L52 50 L78 30 L104 40 L130 22 L156 26 L200 8"
        fill="none"
        stroke="var(--wm-mean-correct)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
    <p className="wm-psignin-tag">
      <span className="wm-psignin-pip wm-psignin-pip-good" />
      doing great
    </p>
    <span className="wm-psignin-progress">
      <span className="wm-psignin-progress-fill" />
    </span>
  </div>
);

/** Card 2: a skill-mastery donut with a small legend — mastered / on track / needs help. */
const MasteryCard = (): React.JSX.Element => (
  <div className="wm-psignin-card wm-psignin-card-mastery" aria-hidden="true">
    <p className="wm-psignin-card-title">Skill Mastery</p>
    <div className="wm-psignin-mastery-row">
      <span className="wm-psignin-donut" />
      <ul className="wm-psignin-legend">
        <li>
          <span className="wm-psignin-pip wm-psignin-pip-good" />
          Mastered
        </li>
        <li>
          <span className="wm-psignin-pip wm-psignin-pip-mid" />
          On track
        </li>
        <li>
          <span className="wm-psignin-pip wm-psignin-pip-help" />
          Needs help
        </li>
      </ul>
    </div>
  </div>
);

const VideoIcon = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="wm-psignin-chip-icon">
    <rect x="2.5" y="6" width="13" height="12" rx="2.5" fill="currentColor" />
    <path d="M16.5 10 L21.5 7 V17 L16.5 14 Z" fill="currentColor" />
  </svg>
);

/** Card 3: a few practice suggestions, with a quick-video chip. */
const SuggestCard = (): React.JSX.Element => (
  <div className="wm-psignin-card wm-psignin-card-suggest" aria-hidden="true">
    <div className="wm-psignin-suggest-head">
      <p className="wm-psignin-card-title">Practice Suggestions</p>
      <span className="wm-psignin-chip">
        <VideoIcon />
        Quick video
      </span>
    </div>
    <ul className="wm-psignin-suggest-list">
      <li>Fraction-bar warm-up</li>
      <li>Number-line practice</li>
      <li>Ratio jars together</li>
    </ul>
  </div>
);

const ClockIcon = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="wm-psignin-feat-svg">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7.5 V12 L15 14" strokeLinecap="round" />
  </svg>
);

const ProgressIcon = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="wm-psignin-feat-svg">
    <path d="M4 20 V4" strokeLinecap="round" />
    <path d="M4 20 H20" strokeLinecap="round" />
    <path d="M7 16 L11 12 L14 14 L19 8" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M16 8 H19 V11" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const ConnectIcon = (): React.JSX.Element => (
  <svg viewBox="0 0 24 24" aria-hidden="true" className="wm-psignin-feat-svg">
    <circle cx="8.5" cy="8" r="3" />
    <circle cx="16" cy="9.5" r="2.5" />
    <path d="M3.5 19 c0-3 2.2-5 5-5 s5 2 5 5" strokeLinecap="round" />
    <path d="M14.5 19 c0-2.4 1.4-4 3.5-4 s3.5 1.6 3.5 4" strokeLinecap="round" />
  </svg>
);

const FEATURES: { icon: () => React.JSX.Element; title: string; sub: string }[] = [
  { icon: ClockIcon, title: 'Daily Activity Summary', sub: 'What they focused on today' },
  { icon: ProgressIcon, title: 'Progress & Challenges', sub: 'Strengths and areas for practice' },
  { icon: ConnectIcon, title: 'Connect and Practice', sub: 'Fun, curated home exercises' },
];

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
        <div className="wm-psignin-stage">
          <FocusCard />
          <MasteryCard />
          <SuggestCard />
        </div>
      </aside>

      <main className="wm-psignin-panel">
        <div className="wm-psignin-inner">
          <div className="wm-psignin-brand">
            <span className="wm-psignin-mark" aria-hidden="true" />
            <span className="wm-psignin-name">WhollyMath</span>
            <span className="wm-psignin-role">Parent</span>
          </div>

          <div className="wm-psignin-body">
            <h1 className="wm-psignin-headline">
              Unlock Your
              <br />
              Child&rsquo;s <span className="wm-psignin-underline">Success</span>
            </h1>

            <ul className="wm-psignin-features">
              {FEATURES.map(({ icon: Icon, title, sub }) => (
                <li key={title} className="wm-psignin-feature">
                  <span className="wm-psignin-feat-icon">
                    <Icon />
                  </span>
                  <span className="wm-psignin-feat-text">
                    <span className="wm-psignin-feat-title">{title}</span>
                    <span className="wm-psignin-feat-sub">{sub}</span>
                  </span>
                </li>
              ))}
            </ul>

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

            <p className="wm-psignin-note">The demo uses sample children. No real student data.</p>
          </div>
        </div>
      </main>
    </div>
  );
}
