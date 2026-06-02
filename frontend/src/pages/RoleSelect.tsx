import { useNavigate } from 'react-router-dom';

import './RoleSelect.css';

/**
 * Role-select gate at `/welcome` (the "For families →" entry from the landing). A calm cream/navy
 * brand register matching the landing + sign-in. Two big choice cards send an adult to the surface
 * they want: the teacher's class dashboard (`/teacher`) or the parent's child progress (`/parent`).
 * Unique classes app-wide (`.wm-role-*`); reuses the shared brand tokens.
 */

function IconTeacher(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* A presentation board with people — "see your class". */}
      <rect x="3" y="3" width="18" height="12" rx="2" />
      <path d="M7 19a3 3 0 0 1 6 0" />
      <circle cx="10" cy="9" r="2" />
      <path d="M16 19a2.5 2.5 0 0 1 5 0" />
    </svg>
  );
}

function IconParent(): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {/* A larger figure beside a smaller one — "follow your child". */}
      <circle cx="8" cy="7" r="3" />
      <path d="M3 21a5 5 0 0 1 10 0" />
      <circle cx="17.5" cy="10.5" r="2.2" />
      <path d="M14 21a3.5 3.5 0 0 1 7 0" />
    </svg>
  );
}

export function RoleSelect(): React.JSX.Element {
  const navigate = useNavigate();
  return (
    <div className="wm-role">
      <div className="wm-role-inner">
        <div className="wm-role-brand">
          <span className="wm-role-mark" aria-hidden="true" />
          <span className="wm-role-name">WhollyMath</span>
        </div>

        <h1 className="wm-role-headline">Who&rsquo;s signing in?</h1>

        <div className="wm-role-choices">
          <button type="button" className="wm-role-card" onClick={() => navigate('/teacher')}>
            <span className="wm-role-card-ico" aria-hidden="true">
              <IconTeacher />
            </span>
            <span className="wm-role-card-title">I&rsquo;m a teacher</span>
            <span className="wm-role-card-sub">See your class dashboard</span>
          </button>

          <button type="button" className="wm-role-card" onClick={() => navigate('/parent')}>
            <span className="wm-role-card-ico" aria-hidden="true">
              <IconParent />
            </span>
            <span className="wm-role-card-title">I&rsquo;m a parent</span>
            <span className="wm-role-card-sub">Follow your child&rsquo;s progress</span>
          </button>
        </div>

        <button type="button" className="wm-role-back" onClick={() => navigate('/')}>
          <span aria-hidden="true">&larr;</span> back
        </button>
      </div>
    </div>
  );
}
