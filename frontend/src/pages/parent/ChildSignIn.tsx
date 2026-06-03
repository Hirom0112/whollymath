import { useState } from 'react';

import { ApiError } from '../../api/index';
import { childLogin } from '../../api/parentAuth';
import './ChildSignIn.css';

/**
 * Independent CHILD sign-in (S5) — for a kid on their own or a school device, signing in without a
 * parent present. Collects the parent's email + the child's username + 4-digit PIN, then calls
 * POST /child/login, which sets a CHILD session cookie. On success we drop them into the learner
 * app (`/units`).
 *
 * Surfaced from the STUDENT /signin page as a toggled view (the single student sign-in surface;
 * the parent portal links here too). No App.tsx route. Handles 401 (wrong details) and 423
 * (locked — too many tries). Unique classes (`.wm-csignin-*`).
 */

const PIN_LENGTH = 4;

export function ChildSignIn({
  onBack,
}: {
  // Return to the student sign-in choices.
  onBack: () => void;
}): React.JSX.Element {
  const [parentEmail, setParentEmail] = useState('');
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (busy) return;
    setError(null);
    if (parentEmail.trim() === '' || username.trim() === '' || !/^\d{4}$/.test(pin)) {
      setError('Please enter the parent email, your username, and your 4-digit PIN.');
      return;
    }
    setBusy(true);
    try {
      await childLogin({
        parent_email: parentEmail.trim(),
        username: username.trim(),
        pin,
      });
      window.location.assign('/units');
    } catch (err) {
      if (err instanceof ApiError && err.status === 423) {
        setError('Too many tries. Ask a parent to reset your PIN, then try again.');
      } else if (err instanceof ApiError && err.status === 401) {
        setError("That didn't match. Check the username and PIN and try again.");
      } else {
        setError('We could not sign you in. Please try again.');
      }
      setBusy(false);
    }
  }

  return (
    <div className="wm-csignin">
      <div className="wm-csignin-panel">
        <div className="wm-csignin-inner">
          <div className="wm-csignin-brand">
            <span className="wm-csignin-mark" aria-hidden="true" />
            <span className="wm-csignin-name">WhollyMath</span>
          </div>

          <form className="wm-csignin-card" onSubmit={(e) => void handleSubmit(e)} noValidate>
            <h1 className="wm-csignin-title">Student sign-in</h1>
            <p className="wm-csignin-sub">
              Use the username and PIN your parent set up for you.
            </p>

            <label className="wm-csignin-field">
              <span className="wm-csignin-label">Parent&rsquo;s email</span>
              <input
                type="email"
                value={parentEmail}
                onChange={(e) => setParentEmail(e.target.value)}
                autoComplete="off"
              />
            </label>

            <label className="wm-csignin-field">
              <span className="wm-csignin-label">Your username</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
              />
            </label>

            <label className="wm-csignin-field">
              <span className="wm-csignin-label">Your 4-digit PIN</span>
              <input
                type="text"
                inputMode="numeric"
                pattern="\d*"
                maxLength={PIN_LENGTH}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, PIN_LENGTH))}
                autoComplete="off"
              />
            </label>

            {error !== null ? (
              <p className="wm-csignin-err" role="alert">
                {error}
              </p>
            ) : null}

            <button type="submit" className="wm-csignin-primary" disabled={busy}>
              {busy ? 'Signing in…' : 'Start practicing'}
            </button>

            <p className="wm-csignin-foot">
              <button type="button" className="wm-csignin-link" onClick={onBack}>
                Back
              </button>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
