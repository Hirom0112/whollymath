"""Homework — the take-home, scanned practice set that gates the SECOND mastery star.

PROJECT.md §3.4 "Two-star model" / TODO RD.0.9: the in-lesson transfer probe is the mastery
GATE (★, unlocks the next lesson). Homework is a SEPARATE, non-gating reinforcement layer that
earns the SECOND star (★★): an engine-generated set (the just-learned skill, anchored, plus
spaced review of earlier spine skills), done on paper, photographed, read by a scanner, and
graded by the SAME SymPy verifier the live tutor uses. A target-skill score ≥ 0.8 earns ★★;
below that loops the learner back through the lesson with a fresh set.

What lives here (one canonical home per concern, CLAUDE.md §7):
  - ``assignment``  build the per-skill homework set + hold its expected answers.
  - ``grading``     grade scanned answers against the set via ``domain.verifier`` (SymPy).
  - ``scanner``     read answers off a photo — a swappable ``HomeworkScanner`` (mock now,
                    Mathpix-class math-OCR later); the 1-on-1 review is the misread safety valve.

Boundaries (CLAUDE.md §7, §8.2): correctness is the domain verifier's job (SymPy) — homework
never re-implements it; the OCR/scan path is OFF the latency-critical turn loop, so a vision
model MAY back the scanner there, but it only TRANSCRIBES — SymPy still decides correctness.
"""
