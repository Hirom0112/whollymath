import { useEffect, useState } from 'react';

import { isParentDemo } from '../../api/parent';
import { listChildren, startChildSession, type ChildAccount } from '../../api/parentAuth';
import { demoHousehold } from '../../api/parentDemo';
import { ParentShell } from '../../components/ParentShell';
import './ParentChildPicker.css';

// The demo household's children, shaped as the picker's `ChildAccount` rows. In the login-free demo
// bypass there is no real backend session, so the picker reads the same seeded household the rest of
// the parent surface does and "Start practice" drops into the anonymous learner app (like the
// student demo) rather than minting a child session.
function demoPickerChildren(): ChildAccount[] {
  return demoHousehold().children.map((c) => ({
    public_id: c.child_id,
    display_name: c.name,
    grade_level: c.grade,
    locale: 'en',
  }));
}

/**
 * "Who's practicing?" profile picker (S5). Shown when a parent is signed in and wants to hand a
 * device to one of their kids. Each child is a big tappable card; tapping it calls
 * POST /parent/children/{id}/start-session, which switches the session cookie to a CHILD session.
 * On success we send the child into the learner app (the existing student home, `/units`).
 *
 * Rendered inside the parent shell as a reachable view from the dashboard. Unique classes
 * (`.wm-ppick-*`).
 */

const GRADE_TINTS = [
  'var(--wm-card-sky)',
  'var(--wm-card-mint)',
  'var(--wm-card-butter)',
  'var(--wm-card-lavender)',
  'var(--wm-card-warm)',
] as const;

export function ParentChildPicker({
  onBack,
  onExit,
  parentName = null,
  householdLabel = null,
}: {
  onBack: () => void;
  onExit?: () => void;
  parentName?: string | null;
  householdLabel?: string | null;
}): React.JSX.Element {
  const [children, setChildren] = useState<ChildAccount[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startingId, setStartingId] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    if (isParentDemo()) {
      setChildren(demoPickerChildren());
      return;
    }
    listChildren()
      .then((rows) => {
        if (live) setChildren(rows);
      })
      .catch(() => {
        if (live) setError('We could not load your children. Please try again.');
      });
    return () => {
      live = false;
    };
  }, []);

  async function handleStart(child: ChildAccount): Promise<void> {
    if (startingId !== null) return;
    setStartingId(child.public_id);
    setError(null);
    if (isParentDemo()) {
      // No real child session in the demo bypass — drop into the anonymous learner app.
      window.location.assign('/units');
      return;
    }
    try {
      await startChildSession(child.public_id);
      // The cookie is now a child session — send them into the learner app.
      window.location.assign('/units');
    } catch {
      setError(`We could not start a session for ${child.display_name}. Please try again.`);
      setStartingId(null);
    }
  }

  return (
    <ParentShell
      parentName={parentName}
      householdLabel={householdLabel}
      onHome={onBack}
      onSignOut={onExit}
    >
      <div className="wm-ppick-content">
        <button type="button" className="wm-ppick-back" onClick={onBack}>
          <span aria-hidden="true" className="wm-ppick-back-ico">
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

        <h1 className="wm-ppick-title">Who&rsquo;s practicing?</h1>
        <p className="wm-ppick-sub">
          Tap a child to start their practice on this device. You can come back here anytime.
        </p>

        {error !== null ? (
          <p className="wm-ppick-error" role="alert">
            {error}
          </p>
        ) : null}

        {children === null && error === null ? (
          <p className="wm-ppick-loading">Loading your children…</p>
        ) : null}

        {children !== null && children.length === 0 ? (
          <p className="wm-ppick-empty">
            No children yet. Add one from your dashboard to get started.
          </p>
        ) : null}

        {children !== null && children.length > 0 ? (
          <div className="wm-ppick-grid">
            {children.map((child, i) => (
              <button
                key={child.public_id}
                type="button"
                className="wm-ppick-card"
                style={{ ['--wm-ppick-tint' as string]: GRADE_TINTS[i % GRADE_TINTS.length] }}
                onClick={() => void handleStart(child)}
                disabled={startingId !== null}
              >
                <span className="wm-ppick-avatar" aria-hidden="true">
                  {child.display_name.trim().charAt(0).toUpperCase() || '?'}
                </span>
                <span className="wm-ppick-name">{child.display_name}</span>
                <span className="wm-ppick-meta">
                  Grade {child.grade_level}
                  {child.locale === 'es-MX' ? ' · Español' : ''}
                </span>
                <span className="wm-ppick-cta">
                  {startingId === child.public_id ? 'Starting…' : 'Start practice'}
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </ParentShell>
  );
}
