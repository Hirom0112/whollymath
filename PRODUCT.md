# Product

> Strategic design context for the WhollyMath frontend (impeccable `PRODUCT.md`).
> Grounds every design decision in who/what/why. The visual "how" lives in `DESIGN.md`.
> Derived from the planning docs (`PROJECT.md`, `ARCHITECTURE.md`, `TECH_STACK.md`,
> `Nerdy.md`) plus the confirmed design-direction interview (2026-05-27).

## Register

product

## Users

**Primary — the learner.** 6th–7th graders (≈11–13) working through fraction
equivalence, addition/subtraction with unlike denominators, and number-line
placement. They use the tutor mid-session, one problem at a time, on a laptop or
tablet (mouse *and* touch both first-class). Old enough to read fluently; young
enough that fractions are actively being taught and natural-number-bias
misconceptions are live. Not always confident. The surface must treat them as
capable without condescending, protect productive struggle, and make a wrong
answer feel like useful information, never failure.

**Secondary — the reviewer (a viewer, not an operator).** Nerdy / Varsity Tutors
evaluators judging this as a pitch. They watch the surface adapt in a short demo
and decide whether it's something they should be building. We win them by being a
genuinely excellent learning surface, not by demo theater (product-first,
pitch-grade).

## Product Purpose

WhollyMath is an adaptive, multimodal tutor whose interface reshapes itself around
what the learner *demonstrably* understands. It teaches one tightly scoped goal —
reason about fraction equivalence, add/subtract unlike denominators, resist
natural-number bias — across five surface states: **S1** symbolic focus, **S2**
number-line primary, **S3** fraction-bars primary, **S4** worked example with
"why?" prompts, **S5** transfer probe. A defensible mastery model declares mastery
only when it is *earned* (correct across ≥2 representations, ≥1 unscaffolded
correct, on interleaved not blocked practice, above an engagement floor); the
transfer probe is the moment of truth. Success: the learner experiences a surface
that adapts with restraint and clarity, and a reviewer sees an adaptive UI that
visibly outclasses a static walkthrough or a chat box.

## Brand Personality

**Calm and confident.** Three words: *composed, credible, encouraging.* Voice:
steady, plain, never hype, never babyish, never condescending. Emotional goal: the
learner feels capable and unhurried. The interface is quiet by default *precisely
so that when it changes, the change is legible* — the adaptive morph is the
centerpiece, and a noisy base would drown it out.

**Register arc (onboarding vs. working surfaces).** The *onboarding* surfaces — the
brand landing (mascot, warm) and the Turn-0 "world" cold start (a fantasy-landscape
backdrop with chunky, illustrated option cards) — run deliberately warmer and more
playful: they *invite*. The *working* in-problem surfaces (S1–S5) settle into the
calm register above. The warmth is a bridge into the tutor, not the working tone;
the kid is welcomed, then focused. (Decision 2026-05-27 — the cold start moved from
an earlier flat/editorial treatment to the world-card design at the team's
direction.)

## Anti-references

- **Varsity Tutors "Homework Help"** — a static, linear worked-example walkthrough.
  We are the live, manipulable, adaptive opposite.
- **Generic "AI Tutor" chat boxes** — tutoring as a wall of chat text. Our math
  lives in a workspace, not a transcript.
- **Chaotic morphing UIs** — `PROJECT.md §7.7`: "a chaotic interface that constantly
  morphs is not a good result." Restraint is the feature.
- **Cheesy / gamified kids' math apps** — mascots, confetti, points-and-badges
  loops, baby colors. We respect the learner.
- The shared **absolute bans**: gradient text, side-stripe accents, default
  glassmorphism, the hero-metric template, identical card grids, modal-first.

## Design Principles

1. **Color means something.** Hue and emphasis are reserved for meaning — magnitude,
   error kind (magnitude→number line, operation→bars), correctness, the current
   surface state — never decoration. A reviewer should be able to read the learner's
   state off the screen.
2. **Adapt with restraint, always labeled.** Five states, no more. Transitions happen
   between problems, never mid-problem, never on a pause; every change carries a
   one-line reason. The refuse-rules (`PROJECT.md §3.8`) are visible discipline.
3. **The manipulative is the hero.** The workspace (number line, fraction bars,
   symbolic editor) is the crafted center of every screen; chrome recedes. Direct
   manipulation, not passive components (a PRD-required feature).
4. **Protect productive struggle.** No auto-help in the first 60 s; nudges, not
   interruptions; preserve the learner's own work when the surface changes. Never
   rush the kid.
5. **Honest progress.** Mastery is shown only when earned; the surface never fakes
   confidence it has not measured. What the learner sees matches what the mastery
   model actually knows.

## Accessibility & Inclusion

- **Colorblind-safe:** never encode meaning by hue alone — pair color with shape,
  position, label, or icon (load-bearing here, since color carries meaning).
- **Mouse + touch parity:** drag / slide / click all work with either; large,
  forgiving hit targets for the age band.
- **Reduced motion:** honor `prefers-reduced-motion` — the adaptive transitions are
  meaningful, so the reduced-motion fallback still communicates the change (label +
  cross-fade / instant) without large movement.
- **Contrast:** target WCAG 2.1 AA for text and meaningful UI.
- **Out of v1 scope** (named in the limitations memo, `PROJECT.md §9`): full
  screen-reader support — architected not to preclude it, but not implemented.
