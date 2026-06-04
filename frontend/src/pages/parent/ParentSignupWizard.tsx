import { useState } from 'react';

import { ApiError } from '../../api/index';
import {
  createChild,
  parentGoogle,
  parentSignup,
  type CreateChildInput,
} from '../../api/parentAuth';
import { promptGoogleSignIn } from '../../auth/google';
import './ParentSignupWizard.css';

/**
 * The parent SIGN-UP wizard (S4). A multi-step flow on the cream sign-in register: create the
 * account, give COPPA consent, choose how many children, fill each child's login, then a "share
 * these logins" summary before landing on the dashboard. It talks to the REAL backend via
 * `parentAuth.ts` (cookie session + CSRF) — NOT the demo client.
 *
 * Navigation is internal step state (mirrors ParentApp's view machine — no router). On finish it
 * calls `onComplete` so the container can drop the parent on the existing ParentDashboard.
 *
 * COPPA note: the consent checkbox here is informational in the UI; the backend records the parent's
 * consent at child creation (each POST /parent/children). Unique classes app-wide (`.wm-pwiz-*`).
 */

const STEP_LABELS = ['Account', 'Consent', 'Children', 'Logins', 'Share'] as const;
type StepIndex = 0 | 1 | 2 | 3 | 4;

const GRADES = [4, 5, 6, 7, 8] as const;
const MAX_CHILDREN = 6;
const MIN_CHILDREN = 1;
const PIN_LENGTH = 4;
const PASSWORD_MIN = 8;

/** Map an ApiError status to plain-language copy for the account step. */
function signupErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409)
      return 'An account already exists for that email. Try signing in instead.';
    if (err.status === 400) return err.message; // backend explains the weak-password rule
  }
  return 'We could not create your account. Please check your details and try again.';
}

/** One child's in-progress form fields (before the POST). */
interface ChildDraft {
  displayName: string;
  grade: number;
  locale: 'en' | 'es-MX';
  username: string;
  pin: string;
}

function blankChild(): ChildDraft {
  return { displayName: '', grade: 6, locale: 'en', username: '', pin: '' };
}

/** A successfully-created child's shareable login (PIN shown once, on the summary step). */
interface ChildLogin {
  displayName: string;
  username: string;
  pin: string;
}

const GoogleG = (): React.JSX.Element => (
  <svg viewBox="0 0 48 48" aria-hidden="true" className="wm-pwiz-gicon">
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

export function ParentSignupWizard({
  onComplete,
  onBackToSignIn,
}: {
  // Called after the parent finishes (or skips the children step): land on the dashboard.
  onComplete: () => void;
  // Called from the account step's "already have an account?" affordance.
  onBackToSignIn: () => void;
}): React.JSX.Element {
  const [step, setStep] = useState<StepIndex>(0);

  // Step 1 — account
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [accountBusy, setAccountBusy] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [accountCreated, setAccountCreated] = useState(false);

  // Step 2 — consent
  const [consented, setConsented] = useState(false);

  // Step 3 — count
  const [childCount, setChildCount] = useState(1);

  // Step 4 — per-child forms + the running list of created logins
  const [children, setChildren] = useState<ChildDraft[]>([blankChild()]);
  const [activeChild, setActiveChild] = useState(0);
  const [childBusy, setChildBusy] = useState(false);
  const [childError, setChildError] = useState<string | null>(null);

  // Step 5 — shareable logins (PIN shown once)
  const [logins, setLogins] = useState<ChildLogin[]>([]);
  const [copied, setCopied] = useState(false);

  async function handleCreateAccount(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (accountBusy || accountCreated) return;
    setAccountError(null);
    if (!email.trim().includes('@')) {
      setAccountError('Please enter a valid email address.');
      return;
    }
    if (password.length < PASSWORD_MIN) {
      setAccountError(`Password must be at least ${String(PASSWORD_MIN)} characters.`);
      return;
    }
    setAccountBusy(true);
    try {
      await parentSignup({ email: email.trim(), password });
      setAccountCreated(true);
      setStep(1);
    } catch (err) {
      setAccountError(signupErrorText(err));
    } finally {
      setAccountBusy(false);
    }
  }

  async function handleGoogle(): Promise<void> {
    if (accountBusy || accountCreated) return;
    setAccountError(null);
    const idToken = await promptGoogleSignIn();
    if (idToken === null) {
      setAccountError(
        'Google sign-in is not available right now. Please create an account with email instead.',
      );
      return;
    }
    setAccountBusy(true);
    try {
      await parentGoogle(idToken);
      setAccountCreated(true);
      setStep(1);
    } catch {
      setAccountError('We could not sign you in with Google. Please try the email option.');
    } finally {
      setAccountBusy(false);
    }
  }

  function resizeChildren(count: number): void {
    setChildren((prev) => {
      const next = prev.slice(0, count);
      while (next.length < count) next.push(blankChild());
      return next;
    });
  }

  function updateActiveChild(patch: Partial<ChildDraft>): void {
    setChildren((prev) => prev.map((c, i) => (i === activeChild ? { ...c, ...patch } : c)));
  }

  function validateChild(c: ChildDraft): string | null {
    if (c.displayName.trim() === '') return 'Please enter a nickname for this child.';
    if (c.username.trim().length < 4) return 'Username must be at least 4 characters.';
    if (!/^\d{4}$/.test(c.pin)) return 'PIN must be exactly 4 digits.';
    return null;
  }

  async function handleSaveChild(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (childBusy) return;
    const draft = children[activeChild];
    const localError = validateChild(draft);
    if (localError !== null) {
      setChildError(localError);
      return;
    }
    setChildError(null);
    setChildBusy(true);
    const payload: CreateChildInput = {
      display_name: draft.displayName.trim(),
      grade_level: draft.grade,
      locale: draft.locale,
      username: draft.username.trim(),
      pin: draft.pin,
    };
    try {
      const created = await createChild(payload);
      setLogins((prev) => [
        ...prev,
        { displayName: draft.displayName.trim(), username: created.username, pin: draft.pin },
      ]);
      if (activeChild + 1 < childCount) {
        setActiveChild(activeChild + 1);
      } else {
        setStep(4);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setChildError('That username is already taken. Please choose another.');
      } else if (err instanceof ApiError && err.status === 400) {
        setChildError(err.message || 'That PIN is not valid — use exactly 4 digits.');
      } else {
        setChildError('We could not create this login. Please try again.');
      }
    } finally {
      setChildBusy(false);
    }
  }

  function loginsAsText(): string {
    return logins
      .map((l) => `${l.displayName}\n  Username: ${l.username}\n  PIN: ${l.pin}`)
      .join('\n\n');
  }

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(loginsAsText());
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="wm-pwiz">
      <div className="wm-pwiz-panel">
        <div className="wm-pwiz-inner">
          <div className="wm-pwiz-brand">
            <span className="wm-pwiz-mark" aria-hidden="true" />
            <span className="wm-pwiz-name">WhollyMath</span>
            <span className="wm-pwiz-role">Parent</span>
          </div>

          <ol className="wm-pwiz-steps" aria-label="Sign-up progress">
            {STEP_LABELS.map((label, i) => (
              <li
                key={label}
                className={
                  'wm-pwiz-step' +
                  (i === step ? ' wm-pwiz-step--active' : '') +
                  (i < step ? ' wm-pwiz-step--done' : '')
                }
                aria-current={i === step ? 'step' : undefined}
              >
                <span className="wm-pwiz-step-dot">{i + 1}</span>
                <span className="wm-pwiz-step-label">{label}</span>
              </li>
            ))}
          </ol>

          <div className="wm-pwiz-body">
            {step === 0 ? (
              <form
                className="wm-pwiz-card"
                onSubmit={(e) => void handleCreateAccount(e)}
                noValidate
              >
                <h1 className="wm-pwiz-title">Create your parent account</h1>
                <p className="wm-pwiz-sub">
                  One account for your whole family. You&rsquo;ll add each child&rsquo;s login in a
                  moment.
                </p>

                <button
                  type="button"
                  className="wm-pwiz-google"
                  onClick={() => void handleGoogle()}
                  disabled={accountBusy}
                >
                  <GoogleG />
                  Sign up with Google
                </button>

                <div className="wm-pwiz-or">
                  <span>or</span>
                </div>

                <label className="wm-pwiz-field">
                  <span className="wm-pwiz-label">Email</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    aria-invalid={accountError !== null}
                  />
                </label>

                <label className="wm-pwiz-field">
                  <span className="wm-pwiz-label">Password</span>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="new-password"
                    aria-invalid={accountError !== null}
                  />
                </label>

                {accountError !== null ? (
                  <p className="wm-pwiz-err" role="alert">
                    {accountError}
                  </p>
                ) : null}

                <button type="submit" className="wm-pwiz-primary" disabled={accountBusy}>
                  {accountBusy ? 'Creating…' : 'Create account'}
                </button>

                <p className="wm-pwiz-foot">
                  Already have an account?{' '}
                  <button type="button" className="wm-pwiz-link" onClick={onBackToSignIn}>
                    Sign in
                  </button>
                </p>
              </form>
            ) : null}

            {step === 1 ? (
              <div className="wm-pwiz-card">
                <h1 className="wm-pwiz-title">A quick note for parents</h1>
                <p className="wm-pwiz-sub">
                  WhollyMath is for kids, so we keep things simple and ask for your okay first.
                </p>

                <div className="wm-pwiz-consent">
                  <p className="wm-pwiz-consent-head">What we collect about your child</p>
                  <ul className="wm-pwiz-consent-list">
                    <li>A nickname (not their real name) and their grade.</li>
                    <li>A username and 4-digit PIN they&rsquo;ll use to sign in.</li>
                    <li>Their learning progress — what they practice and how they do.</li>
                  </ul>
                  <p className="wm-pwiz-consent-why">
                    We use this only to personalize their practice and show you their progress. You
                    can review or delete your child&rsquo;s information anytime from your dashboard.
                  </p>
                </div>

                <label className="wm-pwiz-check">
                  <input
                    type="checkbox"
                    checked={consented}
                    onChange={(e) => setConsented(e.target.checked)}
                  />
                  <span>I&rsquo;m the parent or guardian and I consent.</span>
                </label>

                <div className="wm-pwiz-actions">
                  <button type="button" className="wm-pwiz-back" onClick={() => setStep(0)}>
                    Back
                  </button>
                  <button
                    type="button"
                    className="wm-pwiz-primary"
                    disabled={!consented}
                    onClick={() => setStep(2)}
                  >
                    Continue
                  </button>
                </div>
              </div>
            ) : null}

            {step === 2 ? (
              <div className="wm-pwiz-card">
                <h1 className="wm-pwiz-title">How many children?</h1>
                <p className="wm-pwiz-sub">
                  You can add up to {MAX_CHILDREN}. You&rsquo;ll set up a login for each one next.
                </p>

                <div className="wm-pwiz-stepper" role="group" aria-label="Number of children">
                  <button
                    type="button"
                    className="wm-pwiz-stepper-btn"
                    aria-label="Fewer children"
                    disabled={childCount <= MIN_CHILDREN}
                    onClick={() => {
                      const next = Math.max(MIN_CHILDREN, childCount - 1);
                      setChildCount(next);
                      resizeChildren(next);
                    }}
                  >
                    −
                  </button>
                  <span className="wm-pwiz-stepper-value" aria-live="polite">
                    {childCount}
                  </span>
                  <button
                    type="button"
                    className="wm-pwiz-stepper-btn"
                    aria-label="More children"
                    disabled={childCount >= MAX_CHILDREN}
                    onClick={() => {
                      const next = Math.min(MAX_CHILDREN, childCount + 1);
                      setChildCount(next);
                      resizeChildren(next);
                    }}
                  >
                    +
                  </button>
                </div>

                <div className="wm-pwiz-actions">
                  <button type="button" className="wm-pwiz-back" onClick={() => setStep(1)}>
                    Back
                  </button>
                  <button
                    type="button"
                    className="wm-pwiz-primary"
                    onClick={() => {
                      resizeChildren(childCount);
                      setActiveChild(0);
                      setLogins([]);
                      setStep(3);
                    }}
                  >
                    Continue
                  </button>
                </div>
              </div>
            ) : null}

            {step === 3 ? (
              <form className="wm-pwiz-card" onSubmit={(e) => void handleSaveChild(e)} noValidate>
                <h1 className="wm-pwiz-title">
                  Set up child {activeChild + 1} of {childCount}
                </h1>
                <p className="wm-pwiz-sub">
                  This creates the login your child will use on their own to sign in.
                </p>

                <label className="wm-pwiz-field">
                  <span className="wm-pwiz-label">Nickname</span>
                  <input
                    type="text"
                    value={children[activeChild].displayName}
                    onChange={(e) => updateActiveChild({ displayName: e.target.value })}
                    autoComplete="off"
                  />
                  <span className="wm-pwiz-hint">
                    Use a nickname, not their real name — it&rsquo;s what they&rsquo;ll see on
                    screen.
                  </span>
                </label>

                <div className="wm-pwiz-row">
                  <label className="wm-pwiz-field">
                    <span className="wm-pwiz-label">Grade</span>
                    <select
                      value={children[activeChild].grade}
                      onChange={(e) => updateActiveChild({ grade: Number(e.target.value) })}
                    >
                      {GRADES.map((g) => (
                        <option key={g} value={g}>
                          Grade {g}
                        </option>
                      ))}
                    </select>
                  </label>

                  <div className="wm-pwiz-field">
                    <span className="wm-pwiz-label">Language</span>
                    <div className="wm-pwiz-toggle" role="group" aria-label="Help language">
                      <button
                        type="button"
                        className={
                          'wm-pwiz-toggle-btn' +
                          (children[activeChild].locale === 'en' ? ' wm-pwiz-toggle-btn--on' : '')
                        }
                        aria-pressed={children[activeChild].locale === 'en'}
                        onClick={() => updateActiveChild({ locale: 'en' })}
                      >
                        English
                      </button>
                      <button
                        type="button"
                        className={
                          'wm-pwiz-toggle-btn' +
                          (children[activeChild].locale === 'es-MX'
                            ? ' wm-pwiz-toggle-btn--on'
                            : '')
                        }
                        aria-pressed={children[activeChild].locale === 'es-MX'}
                        onClick={() => updateActiveChild({ locale: 'es-MX' })}
                      >
                        Español
                      </button>
                    </div>
                  </div>
                </div>

                <label className="wm-pwiz-field">
                  <span className="wm-pwiz-label">Username (the child&rsquo;s login)</span>
                  <input
                    type="text"
                    value={children[activeChild].username}
                    onChange={(e) => updateActiveChild({ username: e.target.value })}
                    autoComplete="off"
                  />
                </label>

                <label className="wm-pwiz-field">
                  <span className="wm-pwiz-label">4-digit PIN</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="\d*"
                    maxLength={PIN_LENGTH}
                    value={children[activeChild].pin}
                    onChange={(e) =>
                      updateActiveChild({
                        pin: e.target.value.replace(/\D/g, '').slice(0, PIN_LENGTH),
                      })
                    }
                    autoComplete="off"
                  />
                </label>

                {childError !== null ? (
                  <p className="wm-pwiz-err" role="alert">
                    {childError}
                  </p>
                ) : null}

                <div className="wm-pwiz-actions">
                  <button
                    type="button"
                    className="wm-pwiz-back"
                    onClick={() => setStep(2)}
                    disabled={childBusy}
                  >
                    Back
                  </button>
                  <button type="submit" className="wm-pwiz-primary" disabled={childBusy}>
                    {childBusy
                      ? 'Saving…'
                      : activeChild + 1 < childCount
                        ? 'Save & next child'
                        : 'Save & finish'}
                  </button>
                </div>
              </form>
            ) : null}

            {step === 4 ? (
              <div className="wm-pwiz-card">
                <h1 className="wm-pwiz-title">Share these logins</h1>
                <p className="wm-pwiz-sub">
                  Give each child their username and PIN. For their safety, the PIN won&rsquo;t be
                  shown again — copy or print it now.
                </p>

                <div className="wm-pwiz-logins">
                  {logins.map((l) => (
                    <div key={l.username} className="wm-pwiz-login">
                      <span className="wm-pwiz-login-name">{l.displayName}</span>
                      <div className="wm-pwiz-login-grid">
                        <span className="wm-pwiz-login-key">Username</span>
                        <span className="wm-pwiz-login-val">{l.username}</span>
                        <span className="wm-pwiz-login-key">PIN</span>
                        <span className="wm-pwiz-login-val">{l.pin}</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="wm-pwiz-share-actions">
                  <button type="button" className="wm-pwiz-ghost" onClick={() => void handleCopy()}>
                    {copied ? 'Copied' : 'Copy logins'}
                  </button>
                  <button type="button" className="wm-pwiz-ghost" onClick={() => window.print()}>
                    Print
                  </button>
                </div>

                <button type="button" className="wm-pwiz-primary" onClick={onComplete}>
                  Go to dashboard
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
