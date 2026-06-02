"""SEAM (inert): number-splicing for the variable-number spoken lines — NOT built in v1.

The variable-free bank renders as whole cached clips (``app/tts/batch.py``). The OTHER half of
the avatar's speech — problem restatements, number-specific worked-example steps, any line that
quotes a concrete number — is enumerated by ``app/tts/spoken_bank.enumerate_deferred`` and
flagged here for the "number-splicing" approach (V2_TODO 2.1 open-decisions, the ONE-VOICE
invariant): pre-render the CARRIER phrases (the fixed words around the blanks) plus a small
library of NUMBER / FRACTION clips, all in the SAME Hope voice, then splice carrier + number
clips at build/serve time. This avoids rendering every numeric permutation (combinatorial) while
keeping a single consistent voice (never a second engine mid-sentence).

This module is intentionally INERT — it documents the seam and the data it will need, and
raises if its builder is called, so nothing half-built ships as done (CLAUDE.md §5). No behavior,
no dependency, until the splicing path is scheduled.
"""

from __future__ import annotations

# TODO(slice-A-followup): implement number-splicing for the deferred (number-templated) bank.
# Plan:
#   1. Carrier extraction — turn each templated line (e.g. worked_example step f-strings) into a
#      carrier phrase with typed slots: "Find a common denominator: the smallest is {n}." Render
#      the carrier WITH a short pause/marker where each number goes.
#   2. Number/fraction clip library — render a bounded library of number words ("twelve"),
#      fraction words ("three quarters"), and connectors in the SAME Hope voice
#      (HOPE_VOICE_SETTINGS), content-hashed like the main bank.
#   3. Splice — at build (or serve) time, concatenate carrier + number clips and stitch their
#      word timings (offsetting each spliced clip's wtimes by the running audio duration) into a
#      single lip-sync track TalkingHead can consume.
#   4. Manifest — emit spliced entries keyed by (string_id, locale, slot-values) or assemble on
#      demand from carrier + number-clip ids.
# Until then, ``enumerate_deferred()`` lists exactly which lines wait on this path.

IS_STUB = True


def build_spliced_line(*_args: object, **_kwargs: object) -> object:
    """NOT IMPLEMENTED — the number-splicing builder seam (see module TODO).

    Raises ``NotImplementedError`` so an accidental call fails loudly. v1 renders only the
    variable-free bank; number-templated lines are deferred to this path.
    """
    raise NotImplementedError(
        "number-splicing for variable-number lines is a deferred seam; v1 renders only the "
        "variable-free bank (app/tts/spoken_bank.enumerate_renderable)."
    )


__all__ = ["IS_STUB", "build_spliced_line"]
