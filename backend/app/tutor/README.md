# app/tutor/

The session loop: problem presentation, turn orchestration, hints, worked examples,
and the **S5 transfer probe** (both the live-learner build and the persona-eval build).

Carries fraction values via `sympy.Rational` but does **no** verification here — math
correctness is decided only in `domain/` (invariant 5). Hint text is rendered via
validated templates in `llm/`, always after the verdict.
