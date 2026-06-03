import { useState } from 'react';

import { ApiError } from '../api/index';
import { addChild } from '../api/parent';
import { ParentShell } from '../components/ParentShell';

import './parent/ParentCreateChildAuth.css';
import './ParentCreateChild.css';

/**
 * Add-a-child form, rendered inside the parent shell as the `addChild` view. Collects the child's
 * nickname, grade, help language, and the login (username + 4-digit PIN) the CHILD uses to sign into
 * the learner app. On submit it calls the REAL `addChild` (POST /parent/children via parentAuth.ts),
 * creating a live child account, then shows the login to share before returning home. Handles 409
 * (username taken) and 400 (bad PIN) inline. Unique classes (`.wm-pcreate-*`).
 */

const USERNAME_MIN = 4;
const USERNAME_MAX = 20;
const GRADES = [4, 5, 6, 7, 8] as const;

interface FormErrors {
  name?: string;
  username?: string;
  pin?: string;
}

function validate(name: string, username: string, pin: string): FormErrors {
  const errors: FormErrors = {};
  if (name.trim() === '') errors.name = 'Please enter a nickname for your child.';
  const u = username.trim();
  if (u.length < USERNAME_MIN || u.length > USERNAME_MAX) {
    errors.username = `Username must be ${String(USERNAME_MIN)}–${String(USERNAME_MAX)} characters.`;
  }
  if (!/^\d{4}$/.test(pin)) errors.pin = 'PIN must be exactly 4 digits.';
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
  const [locale, setLocale] = useState<'en' | 'es-MX'>('en');
  const [username, setUsername] = useState('');
  const [pin, setPin] = useState('');
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);
  // After a successful add we show the login to share before returning home.
  const [created, setCreated] = useState<{ name: string; username: string; pin: string } | null>(
    null,
  );

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (busy) return;
    const found = validate(name, username, pin);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      const result = await addChild({
        name: name.trim(),
        grade,
        locale,
        username: username.trim(),
        pin,
      });
      setCreated({ name: name.trim(), username: result.username, pin });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors({ username: 'That username is already taken. Please choose another.' });
      } else if (err instanceof ApiError && err.status === 400) {
        setErrors({ pin: err.message || 'That PIN is not valid — use exactly 4 digits.' });
      } else {
        setErrors({ name: 'We could not create this login. Please try again.' });
      }
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
              the WhollyMath learner app. The PIN won&rsquo;t be shown again — note it now.
            </p>
            <div className="wm-pcreate-done-login">
              <span className="wm-pcreate-done-login-key">Username</span>
              <span className="wm-pcreate-done-login-val">{created.username}</span>
              <span className="wm-pcreate-done-login-key">PIN</span>
              <span className="wm-pcreate-done-login-val">{created.pin}</span>
            </div>
            <button type="button" className="wm-pcreate-submit" onClick={onDone}>
              Back to family
            </button>
          </div>
        ) : (
          <form className="wm-pcreate-card" onSubmit={(e) => void handleSubmit(e)} noValidate>
            <h1 className="wm-pcreate-title">Add a child</h1>
            <p className="wm-pcreate-sub">
              Create a login for your child. They&rsquo;ll use the username and 4-digit PIN below to
              sign into the learner app.
            </p>

            <label className="wm-pcreate-field">
              <span className="wm-pcreate-label">Child&rsquo;s nickname</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="off"
                aria-invalid={errors.name !== undefined}
              />
              <span className="wm-pcreate-hint">
                Use a nickname, not their real name — it&rsquo;s what they&rsquo;ll see on screen.
              </span>
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

            <div className="wm-pcreate-field">
              <span className="wm-pcreate-label">Language</span>
              <div className="wm-pcreate-langtoggle" role="group" aria-label="Help language">
                <button
                  type="button"
                  className={
                    'wm-pcreate-langbtn' + (locale === 'en' ? ' wm-pcreate-langbtn--on' : '')
                  }
                  aria-pressed={locale === 'en'}
                  onClick={() => setLocale('en')}
                >
                  English
                </button>
                <button
                  type="button"
                  className={
                    'wm-pcreate-langbtn' + (locale === 'es-MX' ? ' wm-pcreate-langbtn--on' : '')
                  }
                  aria-pressed={locale === 'es-MX'}
                  onClick={() => setLocale('es-MX')}
                >
                  Español
                </button>
              </div>
            </div>

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
              <span className="wm-pcreate-label">4-digit PIN</span>
              <input
                type="text"
                inputMode="numeric"
                pattern="\d*"
                maxLength={4}
                value={pin}
                onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                autoComplete="off"
                aria-invalid={errors.pin !== undefined}
              />
              {errors.pin !== undefined ? (
                <span className="wm-pcreate-err">{errors.pin}</span>
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
