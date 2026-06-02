import { useNavigate } from 'react-router-dom';

import { Mascot } from '../components/Mascot';
import './RoleSelect.css';

/**
 * Role-select gate at `/welcome` (the "For teachers & families" entry from the landing). A rendered
 * "desk" scene (assets in /public/welcome): a cream wall with a faded compass watermark, a wooden
 * shelf with a brass abacus prop, and two front-facing ornate portal plaques — the teacher's class
 * dashboard (`/teacher`) and the parent's child progress (`/parent`). Pi rolls in along the shelf.
 *
 * The plaque FRAMES (with their TEACHER / PARENT PORTAL labels baked in) are background images on
 * the cards; the live white window inside each holds the rendered illustration, the CTA, and the
 * copy — so the buttons stay real HTML (clickable, accessible) while the metal frame is the border.
 * Unique classes app-wide (`.wm-role-*`).
 */
export function RoleSelect(): React.JSX.Element {
  const navigate = useNavigate();
  return (
    <div className="wm-role">
      {/* Desk staging — purely decorative, behind the UI. */}
      <img className="wm-role-shelf" src="/welcome/shelf.png" alt="" aria-hidden="true" />
      <div className="wm-role-pi" aria-hidden="true">
        <Mascot />
      </div>

      <div className="wm-role-stage">
        <div className="wm-role-brand">
          <span className="wm-role-mark" aria-hidden="true" />
          <span className="wm-role-name">WhollyMath</span>
        </div>

        <h1 className="wm-role-headline">Who&rsquo;s signing in?</h1>

        <div className="wm-role-choices">
          <button
            type="button"
            className="wm-role-card wm-role-card--teacher"
            onClick={() => navigate('/teacher')}
            aria-label="Teacher portal — access your class dashboard"
          >
            <span className="wm-role-window">
              <img
                className="wm-role-illo"
                src="/welcome/illo-abacus.png"
                alt=""
                aria-hidden="true"
              />
              <span className="wm-role-cta">Access Class Dashboard</span>
              <span className="wm-role-desc">
                Manage your students, view performance data, and create assignments.
              </span>
            </span>
          </button>

          <button
            type="button"
            className="wm-role-card wm-role-card--parent"
            onClick={() => navigate('/parent')}
            aria-label="Parent portal — connect to your child's progress"
          >
            <span className="wm-role-window">
              <img
                className="wm-role-illo"
                src="/welcome/illo-family.png"
                alt=""
                aria-hidden="true"
              />
              <span className="wm-role-cta">Connect to Child&rsquo;s Progress</span>
              <span className="wm-role-desc">
                Follow lesson history, celebrate achievements, and discover parent resources.
              </span>
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
