import { useState } from 'react';

import { addChild } from '../api/parent';
import { ParentShell } from '../components/ParentShell';
import './ParentCreateChild.css';

/**
 * Add-a-child form, rendered inside the parent shell as the `addChild` view. Collects the child's
 * first name, grade, and the login (username + password) the CHILD will use to sign into the learner
 * app. Local validation only; on submit (demo) it appends the child to the in-memory household via
 * `addChild` (parentDemo) so they appear on the household dashboard, then shows a brief confirmation
 * of the login to share before returning home. NO network call. Unique classes (`.wm-pcreate-*`).
 */

const USERNAME_MIN = 4;
const USERNAME_MAX = 20;
const PASSWORD_MIN = 8;
const GRADES = [4, 5, 6, 7, 8] as const;

interface FormErrors {
  name?: string;
  username?: string;
  password?: string;
  confirm?: string;
}

function validate(name: string, username: string, password: string, confirm: string): FormErrors {
  const errors: FormErrors = {};
  if (name.trim() === '') errors.name = 'Please enter your child’s first name.';
  const u = username.trim();
  if (u.length < USERNAME_MIN || u.length > USERNAME_MAX) {
    errors.username = `Username must be ${String(USERNAME_MIN)}–${String(USERNAME_MAX)} characters.`;
  }
  if (password.length < PASSWORD_MIN) {
    errors.password = `Password must be at least ${String(PASSWORD_MIN)} characters.`;
  }
  if (confirm !== password) errors.confirm = 'Passwords don’t match.';
  return errors;
}

export function ParentCreateChild({
  onDone,
  onCancel,
  onExit,
  parentName = null,
  householdLabel = null,
}: {
  // Called after a successful add (the container refreshes the household + returns to it).
  onDone: () => void;
  onCancel: () => void;
  onExit?: () => void;
  parentName?: string | null;
  householdLabel?: string | null;
}): React.JSX.Element {
  const [name, setName] = useState('');
  const [grade, setGrade] = useState(6);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);
  // After a successful add we show the login to share before returning home.
  const [created, setCreated] = useState<{ name: string; username: string } | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (busy) return;
    const found = validate(name, username, password, confirm);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const result = await addChild({ name: name.trim(), grade, username: username.trim() });
      setCreated({ name: name.trim(), username: result.username });
    } finally {
      setBusy(false);
    }
  }

  return (
    <ParentShell
      parentName={parentName}
      householdLabel={householdLabel}
      onHome={onCancel}
      onSignOut={onExit}
    >
      <div className="wm-pcreate-content">
        <button type="button" className="wm-pcreate-back" onClick={onCancel}>
          <span aria-hidden="true" className="wm-pcreate-back-ico">
            <svg viewBox="0 0 24 24" focusable="false">
              <polyline
                points="14,5 7,12 14,19"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          Back to family
        </button>

        {created !== null ? (
          <div className="wm-pcreate-card wm-pcreate-done" role="status">
            <span className="wm-pcreate-done-ico" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false">
                <polyline
                  points="4,13 10,19 20,5"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <h1 className="wm-pcreate-done-head">{created.name} is added</h1>
            <p className="wm-pcreate-done-body">
              Share this login with {created.name}. It&rsquo;s what they&rsquo;ll use to sign into
              the WhollyMath learner app.
            </p>
            <div className="wm-pcreate-done-login">
              <span className="wm-pcreate-done-login-key">Username</span>
              <span className="wm-pcreate-done-login-val">{created.username}</span>
              <span className="wm-pcreate-done-login-key">Password</span>
              <span className="wm-pcreate-done-login-val">the one you just set</span>
            </div>
            <button type="button" className="wm-pcreate-submit" onClick={onDone}>
              Back to family
            </button>
          </div>
        ) : (
          <form className="wm-pcreate-card" onSubmit={(e) => void handleSubmit(e)} noValidate>
            <h1 className="wm-pcreate-title">Add a child</h1>
            <p className="wm-pcreate-sub">
              Create a login for your child. They&rsquo;ll use the username and password below to
              sign into the learner app.
            </p>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Child&rsquo;s first name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="off"
                aria-invalid={errors.name !== undefined}
              />
              {errors.name !== undefined ? (
                <span className="wm-pcreate-err">{errors.name}</span>
              ) : null}
            </label>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Grade</span>
              <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
                {GRADES.map((g) => (
                  <option key={g} value={g}>
                    Grade {g}
                  </option>
                ))}
              </select>
            </label>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Username (the child&rsquo;s login)</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="off"
                aria-invalid={errors.username !== undefined}
              />
              {errors.username !== undefined ? (
                <span className="wm-pcreate-err">{errors.username}</span>
              ) : null}
            </label>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Password</span>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                aria-invalid={errors.password !== undefined}
              />
              {errors.password !== undefined ? (
                <span className="wm-pcreate-err">{errors.password}</span>
              ) : null}
            </label>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Confirm password</span>
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                aria-invalid={errors.confirm !== undefined}
              />
              {errors.confirm !== undefined ? (
                <span className="wm-pcreate-err">{errors.confirm}</span>
              ) : null}
            </label>

            <div className="wm-pcreate-actions">
              <button type="button" className="wm-pcreate-cancel" onClick={onCancel}>
                Cancel
              </button>
              <button type="submit" className="wm-pcreate-submit" disabled={busy}>
                {busy ? 'Adding…' : 'Add child'}
              </button>
            </div>
          </form>
        )}
      </div>
    </ParentShell>
  );
}
