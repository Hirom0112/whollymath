import { useEffect, useState } from 'react';

import { fetchChild, type ChildDetail } from '../api/parent';
import type { ActivityEventView, KcMasteryView } from '../api/teacher';
import { AreaChart } from '../components/AreaChart';
import { ParentShell } from '../components/ParentShell';
import { CategoryChip } from '../components/TeacherSignals';
import './ParentChildView.css';

/**
 * One child's progress drill-in for the parent (mirrors TeacherStudentView, reframed in plain-parent
 * language). The child detail is the SAME wire shape as the teacher's student view; this page just
 * translates the clinical fields (misconception jargon, raw BKT percentages) into things a parent
 * can act on. Sections top-to-bottom (the spec): status hero → accuracy over time → skills map →
 * recent activity → practice at home → celebrations → what's coming next. Read-only (no assign).
 *
 * Data: `fetchChild` — demo-backed (parentDemo.ts) until a real backend lands; the page does not
 * change at the swap.
 */

type ChildCategory = ChildDetail['category'];

// The hero's plain-parent summary by status — the "How [name] is doing" headline tone.
const STATUS_HERO: Record<ChildCategory, { eyebrow: string; tone: 'help' | 'nudge' | 'great' }> = {
  struggling: { eyebrow: 'Could use a hand', tone: 'help' },
  needs_attention: { eyebrow: 'Doing well, one thing to watch', tone: 'nudge' },
  on_track: { eyebrow: 'On track', tone: 'great' },
};

// Plain-parent translations of the named misconceptions the verifier computes. The teacher surface
// shows the clinical label; a parent gets a concrete, blame-free sentence (keyed by the exact
// `matched_misconception` strings the demo + verifier produce). `[name]` is filled per child.
const MISCONCEPTION_PLAIN: Record<string, (name: string) => string> = {
  'Natural-number bias': (name) =>
    `When comparing fractions like 3/8 and 1/2, ${name} picks the bigger-looking numbers instead ` +
    `of thinking about size — a normal step in learning fractions.`,
  'Add-across denominators': (name) =>
    `When adding fractions like 1/4 + 1/6, ${name} adds the bottom numbers together instead of ` +
    `finding a common denominator first — a very common mix-up at this stage.`,
  'Tick-counting (ignores the whole)': (name) =>
    `On the number line, ${name} counts tick marks instead of thinking about how big each step ` +
    `is, so the answer changes when the line is drawn differently.`,
};

// "Practice at home" — ONE concrete activity per skill/struggle, a small lookup table (no LLM).
// Keyed first by the named misconception (most specific), then by the current-skill KC id as a
// fallback, then a gentle generic. Each returns a title + a short, parent-doable instruction.
interface HomeActivity {
  title: string;
  body: (name: string) => string;
}

const ACTIVITY_BY_MISCONCEPTION: Record<string, HomeActivity> = {
  'Natural-number bias': {
    title: 'Fold paper to compare fractions',
    body: (name) =>
      `Fold one sheet of paper into 8 equal parts and another into 2. Shade 3/8 on the first and ` +
      `1/2 on the second, then lay them side by side. Ask ${name} which shaded part is bigger — ` +
      `seeing the pieces makes the size obvious, not the numbers.`,
  },
  'Add-across denominators': {
    title: 'Make the pieces match with paper strips',
    body: (name) =>
      `Cut two paper strips the same length. Fold one into 4 parts (for 1/4) and one into 6 (for ` +
      `1/6). Ask ${name}: "Can we add these as-is?" Then re-fold both into 12 parts so the pieces ` +
      `are the same size — that's exactly what a common denominator does.`,
  },
  'Tick-counting (ignores the whole)': {
    title: 'Draw your own number lines',
    body: (name) =>
      `Draw a line from 0 to 1, then another from 0 to 2, both the same width. Ask ${name} to put ` +
      `1/2 on each. The mark lands in a different spot — a great way to show that the whole line ` +
      `matters, not just counting ticks.`,
  },
};

const ACTIVITY_BY_KC: Record<string, HomeActivity> = {
  KC_number_line_placement: {
    title: 'Spot fractions on a ruler',
    body: (name) =>
      `Grab a ruler and ask ${name} to point to where 1/2, 1/4, and 3/4 of an inch land. A ruler ` +
      `is a number line they can hold — it makes placement feel real.`,
  },
  KC_equivalence: {
    title: 'Find equal fractions in the kitchen',
    body: (name) =>
      `Use measuring cups: ask ${name} how many 1/4 cups fill a 1/2 cup, or a whole cup. Seeing ` +
      `2/4 = 1/2 with real cups makes equivalent fractions click.`,
  },
  KC_common_denominator: {
    title: 'Share snacks fairly',
    body: (name) =>
      `Cut a snack so two different-sized groups get equal shares — ${name} has to find pieces ` +
      `that work for both, which is the idea behind a common denominator.`,
  },
  KC_addition_unlike: {
    title: 'Combine recipe amounts',
    body: (name) =>
      `Cooking together, ask ${name} to add amounts like 1/3 cup + 1/4 cup. Working it out with ` +
      `real measuring cups turns adding fractions into something hands-on.`,
  },
  KC_subtraction_unlike: {
    title: 'How much is left?',
    body: (name) =>
      `When something is partly used — say 3/4 of a carton, and you use 1/3 — ask ${name} how much ` +
      `is left. Subtracting fractions is easier when it's about something real.`,
  },
};

const ACTIVITY_GENERIC: HomeActivity = {
  title: 'Talk through one problem together',
  body: (name) =>
    `Sit with ${name} for one problem and ask them to explain their thinking out loud. You don't ` +
    `need the answer — just hearing how they reason tells you (and them) a lot.`,
};

// Skill-status thresholds for the parent skills map — NO raw BKT percentages shown.
function skillLabel(p: number): { text: string; tone: 'mastered' | 'getting' | 'learning' } {
  if (p >= 0.8) return { text: 'Mastered', tone: 'mastered' };
  if (p >= 0.5) return { text: 'Getting there', tone: 'getting' };
  return { text: 'Still learning', tone: 'learning' };
}

export function ParentChildView({
  childId,
  onBack,
  onExit,
  parentName = null,
  householdLabel = null,
}: {
  childId: string;
  onBack: () => void;
  onExit?: () => void;
  parentName?: string | null;
  householdLabel?: string | null;
}): React.JSX.Element {
  const [child, setChild] = useState<ChildDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setChild(null);
    setError(null);
    fetchChild(childId)
      .then((c) => {
        if (live) setChild(c);
      })
      .catch(() => {
        if (live) setError('We could not load this child. They may not be in your family.');
      });
    return () => {
      live = false;
    };
  }, [childId]);

  return (
    <ParentShell
      parentName={parentName}
      householdLabel={householdLabel}
      onHome={onBack}
      onSignOut={onExit}
    >
      <div className="wm-pchild-content">
        <button type="button" className="wm-pchild-back" onClick={onBack}>
          <span aria-hidden="true" className="wm-pchild-back-ico">
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

        {error !== null ? (
          <p className="wm-pchild-error" role="alert">
            {error}
          </p>
        ) : null}

        {child === null && error === null ? <p className="wm-pchild-loading">Loading…</p> : null}

        {child !== null ? <ChildBody child={child} /> : null}
      </div>
    </ParentShell>
  );
}

function ChildBody({ child }: { child: ChildDetail }): React.JSX.Element {
  const name = child.name;
  return (
    <div className="wm-pchild-main">
      {/* (1) Identity + one-line plain status. */}
      <div className="wm-pchild-identity">
        <h1 className="wm-pchild-name">{name}</h1>
        <CategoryChip category={child.category} />
      </div>
      <p className="wm-pchild-reason">{child.category_reason}</p>

      {/* (2) "How [name] is doing" hero. */}
      <StatusHero child={child} />

      {/* (3) Accuracy over time. */}
      <section className="wm-pchild-card" aria-label="Accuracy over time">
        <h2 className="wm-pchild-h2">Accuracy over time</h2>
        {(child.accuracy_history ?? []).length > 0 ? (
          <>
            <p className="wm-pchild-card-sub">
              Each point is one practice session, oldest to newest.
            </p>
            <AreaChart
              data={(child.accuracy_history ?? []).map((a) => Math.round(a * 100))}
              tone={
                child.category === 'on_track'
                  ? 'green'
                  : child.category === 'struggling'
                    ? 'red'
                    : 'amber'
              }
              height={100}
              ariaLabel={`${name} accuracy over time`}
            />
          </>
        ) : (
          <p className="wm-pchild-empty">
            No practice history yet — this fills in once {name} starts working.
          </p>
        )}
      </section>

      {/* (4) Skills map: Getting it / Working on it. */}
      <SkillsMap child={child} />

      {/* (5) Recent activity. */}
      <section className="wm-pchild-card" aria-label="Recent activity">
        <h2 className="wm-pchild-h2">Recent activity</h2>
        <Timeline events={child.activity ?? []} name={name} />
      </section>

      {/* (6) Practice at home. */}
      <PracticeAtHome child={child} />

      {/* (7) Celebrations. */}
      <Celebrations events={child.activity ?? []} name={name} />

      {/* (8) What's coming next (display-only). */}
      <ComingNext child={child} />
    </div>
  );
}

function StatusHero({ child }: { child: ChildDetail }): React.JSX.Element {
  const meta = STATUS_HERO[child.category];
  const name = child.name;
  // Translate misconception jargon to plain parent English when one is named; otherwise use the
  // child's own plain-language headline (already parent-readable in the demo data).
  const named = child.struggle.matched_misconception ?? null;
  const plain =
    named !== null ? (MISCONCEPTION_PLAIN[named]?.(name) ?? child.struggle.headline) : null;
  return (
    <section
      className={`wm-pchild-hero wm-pchild-hero--${meta.tone}`}
      aria-label={`How ${name} is doing`}
    >
      <p className="wm-pchild-hero-eyebrow">{meta.eyebrow}</p>
      <h2 className="wm-pchild-hero-head">How {name} is doing</h2>
      <p className="wm-pchild-hero-headline">{child.struggle.headline}</p>
      {plain !== null ? (
        <p className="wm-pchild-hero-detail">{plain}</p>
      ) : (
        <p className="wm-pchild-hero-detail">{child.struggle.detail}</p>
      )}
    </section>
  );
}

function SkillsMap({ child }: { child: ChildDetail }): React.JSX.Element {
  // The teacher view splits strengths/weaknesses; the parent view re-buckets ALL known skills by a
  // friendly threshold so a parent sees "Getting it" vs "Working on it" without any raw BKT number.
  const all: KcMasteryView[] = [...(child.strengths ?? []), ...(child.weaknesses ?? [])];
  const gettingIt = all.filter((s) => s.probability >= 0.8);
  const workingOn = all.filter((s) => s.probability < 0.8);
  return (
    <section className="wm-pchild-card" aria-label="Skills map">
      <h2 className="wm-pchild-h2">Skills</h2>
      <div className="wm-pchild-skills">
        <SkillColumn
          title="Getting it"
          tone="good"
          skills={gettingIt}
          emptyText="Nothing here yet."
        />
        <SkillColumn
          title="Working on it"
          tone="work"
          skills={workingOn}
          emptyText="All caught up!"
        />
      </div>
    </section>
  );
}

function SkillColumn({
  title,
  tone,
  skills,
  emptyText,
}: {
  title: string;
  tone: 'good' | 'work';
  skills: KcMasteryView[];
  emptyText: string;
}): React.JSX.Element {
  return (
    <div className={`wm-pchild-skillcol wm-pchild-skillcol--${tone}`}>
      <h3 className="wm-pchild-skillcol-title">{title}</h3>
      {skills.length === 0 ? (
        <p className="wm-pchild-skillcol-empty">{emptyText}</p>
      ) : (
        <ul className="wm-pchild-skilllist">
          {skills.map((skill) => {
            const label = skillLabel(skill.probability);
            return (
              <li key={skill.kc_id} className="wm-pchild-skill">
                <span className="wm-pchild-skill-name">{skill.skill_name}</span>
                <span className={`wm-pchild-skill-tag wm-pchild-skill-tag--${label.tone}`}>
                  {label.text}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

const OUTCOME_DOT: Record<ActivityEventView['outcome'], string> = {
  correct: 'correct',
  incorrect: 'incorrect',
  neutral: 'neutral',
};

function Timeline({
  events,
  name,
}: {
  events: ActivityEventView[];
  name: string;
}): React.JSX.Element {
  if (events.length === 0) {
    return (
      <p className="wm-pchild-empty">
        No activity yet — it&rsquo;ll show here once {name} practices.
      </p>
    );
  }
  return (
    <ol className="wm-pchild-timeline">
      {events.map((ev, i) => (
        <li key={`${ev.at}-${String(i)}`} className="wm-pchild-tl-item">
          <span
            className={`wm-pchild-tl-dot wm-pchild-tl-dot--${OUTCOME_DOT[ev.outcome]}`}
            aria-hidden="true"
          />
          <span className="wm-pchild-tl-body">
            <span className="wm-pchild-tl-label">{ev.label}</span>
            <span className="wm-pchild-tl-time">{ev.at}</span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** Pick ONE concrete home activity: by named misconception, else current-skill KC, else generic. */
function pickActivity(child: ChildDetail): HomeActivity {
  const named = child.struggle.matched_misconception ?? null;
  if (named !== null && ACTIVITY_BY_MISCONCEPTION[named] !== undefined) {
    return ACTIVITY_BY_MISCONCEPTION[named];
  }
  // The current skill is the first weakness (what they're working on), else the first strength.
  const current = (child.weaknesses ?? [])[0] ?? (child.strengths ?? [])[0] ?? null;
  if (current !== null && ACTIVITY_BY_KC[current.kc_id] !== undefined) {
    return ACTIVITY_BY_KC[current.kc_id];
  }
  return ACTIVITY_GENERIC;
}

function PracticeAtHome({ child }: { child: ChildDetail }): React.JSX.Element {
  const activity = pickActivity(child);
  return (
    <section className="wm-pchild-card wm-pchild-practice" aria-label="Practice at home">
      <h2 className="wm-pchild-h2">Practice at home</h2>
      <p className="wm-pchild-practice-title">{activity.title}</p>
      <p className="wm-pchild-practice-body">{activity.body(child.name)}</p>
    </section>
  );
}

function StarIcon(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d="M12 0 L14 10 L24 12 L14 14 L12 24 L10 14 L0 12 L10 10 Z" />
    </svg>
  );
}

function Celebrations({
  events,
  name,
}: {
  events: ActivityEventView[];
  name: string;
}): React.JSX.Element {
  // A milestone is a "Mastered ..." or "streak" line in the recent activity — the good news worth
  // surfacing to a parent. (The activity labels are templated, NO LLM, so this match is stable.)
  const milestones = events.filter((ev) => /mastered/i.test(ev.label) || /streak/i.test(ev.label));
  return (
    <section className="wm-pchild-card wm-pchild-celebrate" aria-label="Celebrations">
      <h2 className="wm-pchild-h2">
        <span className="wm-pchild-celebrate-ico" aria-hidden="true">
          <StarIcon />
        </span>
        Celebrations
      </h2>
      {milestones.length === 0 ? (
        <p className="wm-pchild-empty">
          No milestones yet — they&rsquo;re coming. Every problem {name} tries is progress.
        </p>
      ) : (
        <ul className="wm-pchild-celebrate-list">
          {milestones.map((ev, i) => (
            <li key={`${ev.at}-${String(i)}`} className="wm-pchild-celebrate-item">
              <span className="wm-pchild-celebrate-star" aria-hidden="true">
                <StarIcon />
              </span>
              <span className="wm-pchild-celebrate-text">
                <span className="wm-pchild-celebrate-label">{ev.label}</span>
                <span className="wm-pchild-celebrate-time">{ev.at}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ComingNext({ child }: { child: ChildDetail }): React.JSX.Element {
  const lesson = child.current_lesson_title ?? 'their current lesson';
  // The next thing is the first AVAILABLE assignable unit (the parent only reads this — no assign).
  const next = (child.assignable_units ?? []).find((u) => u.available) ?? null;
  return (
    <section className="wm-pchild-card wm-pchild-next" aria-label="What's coming next">
      <h2 className="wm-pchild-h2">What&rsquo;s coming next</h2>
      {next !== null ? (
        <p className="wm-pchild-next-body">
          After <strong>{lesson}</strong>, {child.name} will start <strong>{next.title}</strong>.
        </p>
      ) : (
        <p className="wm-pchild-empty">
          {child.name} is working through their current lessons — more is on the way.
        </p>
      )}
    </section>
  );
}
