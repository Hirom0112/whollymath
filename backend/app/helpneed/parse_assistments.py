"""ASSISTments-2009 Skill-Builder parser — DECISION-GATED STUB (Slice 0.1, V2_TODO WAVE 0).

**STATUS: INERT. This module raises ``NotImplementedError``. It contains NO parsing and produces
NO data.** It is a deliberately-empty placeholder marking a planned external-augmentation source
that is BLOCKED on a commercial-license decision the owner must make. It exists so the seam is named
and the blocker is documented in the decision log — not so anything runs.

────────────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS WOULD DO (when unblocked)
────────────────────────────────────────────────────────────────────────────────────────────────
The intended augmentation (V2_TODO Slice 0.1 "Data strategy") is to add the **ASSISTments 2009
Skill-Builder** dataset alongside the existing ``parse_edmcup.py`` corpus, because it adds real
**fraction** coverage and a clean help-need proxy the EDM Cup data is thinner on. It would parse the
raw ASSISTments columns and map them onto the SAME abstract per-turn signals ``parse_edmcup`` emits
(``EdmCupTurn``), so the two corpora merge into one training set the v2 pipeline already consumes:

    ASSISTments column      →   our abstract signal (EdmCupTurn / labels.is_unproductive input)
    ──────────────────────      ───────────────────────────────────────────────────────────────
    ``bottom_hint``         →   requested_answer  (reached the bottom-out "show me the answer" hint
                                — the §3.4 give-up arm; mirrors EDM Cup's requested-answer signal)
    ``hint_count``          →   hint_count        (hint-dependence arm: >= the hint threshold)
    ``ms_first_response``   →   latency_ms_to_first_response  (the response-latency feature source)
    ``attempt_count``       →   attempt_count     (wrong-tries arm: >= WRONG_ATTEMPT_THRESHOLD)
    ``correct``             →   correct / first_attempt_correct (the §3.4 never-solved-it arm)
    ``skill_name`` (CCSS)   →   KnowledgeComponentId via the CCSS→KC map (parse_edmcup precedent)

Mapping to the SAME ``EdmCupTurn`` is the whole point: once parsed, ASSISTments turns flow through
``features.build_examples`` + ``labels.is_unproductive`` unchanged, exactly like EDM Cup turns, so
the merge is "more rows," not a second pipeline.

────────────────────────────────────────────────────────────────────────────────────────────────
WHY IT IS BLOCKED (the decision gate — owner sign-off required)
────────────────────────────────────────────────────────────────────────────────────────────────
Per V2_TODO open-decisions (line "Training-data license (HelpNeed 0.1)"): **no open
knowledge-tracing dataset (ASSISTments 2009/2012, EDM Cup 2023, Junyi) has a CONFIRMED commercial
license** — they
ship under unspecified "Terms of Use," and the one explicitly-licensed modern release,
**FoundationalASSIST (2026), is CC-BY-NC** — non-commercial, which DISQUALIFIES it for a commercial
product. This same risk already applies to the SHIPPED v1 EDM-Cup model; expanding the corpus with
another unconfirmed-license source widens, not narrows, that exposure (CLAUDE.md §1 source
hierarchy, §8.7 dependency/data justification). A commercial product needs **legal sign-off on the
training
corpus** before this source is used.

The project's lower-risk alternative is the SYNTHETIC persona traces (``synthetic_traces.py``),
which carry NO licensing risk and stamp a ground-truth label no real dataset has — V2_TODO says
to FAVOR them. This stub is therefore left inert ON PURPOSE: implementing it would either (a) commit
us to an unlicensed corpus, or (b) require silently fabricating data, which would violate the
"no silent fake data" / production-grade bar (CLAUDE.md §5). Neither is acceptable without the
owner's license decision.

DO NOT implement this without recording the owner's commercial-license decision in the commit
message and in PROJECT.md / V2_TODO open-decisions (the §8.4 decision-log rule).

No LLM, no SymPy, no DB, no network here — and, deliberately, no parsing either.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from app.helpneed.parse_edmcup import EdmCupTurn

# The block reason, surfaced verbatim in the raised error so a caller (or a future implementer) sees
# exactly why this is inert and where the gate is recorded — not a vague "TODO".
_BLOCKED_REASON = (
    "parse_assistments is an INERT, decision-gated stub: the ASSISTments-2009 Skill-Builder "
    "augmentation is BLOCKED on a commercial-license decision. No open KT dataset (ASSISTments "
    "2009/2012, EDM Cup 2023, Junyi) has a confirmed commercial license; FoundationalASSIST is "
    "CC-BY-NC (disqualified). See V2_TODO open-decisions 'Training-data license (HelpNeed 0.1)'. "
    "Owner legal sign-off on the training corpus is required before implementing this; until then "
    "the synthetic persona traces (synthetic_traces.py) are the favored, license-clean source. "
    "Implementing this stub WITHOUT that decision would mean committing to an unlicensed corpus or "
    "fabricating data — both barred (CLAUDE.md §5, §8.7)."
)


def parse_assistments_skill_builder(
    csv_path: Path,
    *,
    row_limit: int | None = None,
) -> Iterable[EdmCupTurn]:
    """INERT STUB — raises ``NotImplementedError`` with the block reason. Parses nothing.

    When unblocked (owner commercial-license sign-off), this would stream the ASSISTments-2009
    Skill-Builder CSV at ``csv_path`` and yield one ``EdmCupTurn`` per (student, problem) attempt
    sequence, mapping the ASSISTments columns onto the SAME abstract signals ``parse_edmcup`` emits
    (see the module docstring's column map) so the corpora merge through the existing feature/label
    pipeline. ``row_limit`` would cap the rows scanned for a fast pass, mirroring ``parse_edmcup``.

    It deliberately raises rather than returning empty so the blocker can NEVER be mistaken for
    "no data found" — an inert gate, not a silent no-op (CLAUDE.md §5, §8.5).
    """
    raise NotImplementedError(_BLOCKED_REASON)


__all__ = ["parse_assistments_skill_builder"]
