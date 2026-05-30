"""Teacher-surface read/write services (Slices TCH.B3–B7).

The teacher dashboard's diagnostics, assembled from existing engine state — the course map,
unit progress, persisted mastery, and the raw ``Turn`` history — with NO new mastery logic and
NO LLM (CLAUDE.md §8.1/§8.2). Every module here is PURE: it takes already-loaded domain inputs
and returns the wire views (``app.api.schemas``); the DB reads + assembly live one layer up in
``app.api.teacher_service`` (CLAUDE.md §7), and the routes are thinner still.

Why a package and not methods on ``SessionStore``: the teacher surface is a distinct concern
(reading OTHER learners' evidence as a teacher), and keeping it pure makes the diagnostics — the
matched misconception, the alert rules, the ranking — unit-testable without a DB. Role gates this
surface only; none of it ever reaches the turn decision (ARCHITECTURE.md §14 invariant 8).
"""
