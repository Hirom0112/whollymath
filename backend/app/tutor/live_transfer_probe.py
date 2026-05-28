"""Building the S5 transfer-probe steps for a REAL learner (live confirm-gate).

PROJECT.md §3.4/§3.9: declared mastery is PROVISIONAL until the S5 transfer probe is
passed. ``tutor.transfer_probe`` runs the probe against a *simulated persona* (the eval
harness); this module builds the same §3.9 items as ordinary ``Problem`` steps the LIVE
turn loop can present to a real learner and judge with the SymPy verifier — the same
oracle everything else uses (CLAUDE.md §8.2). The service orchestrates the steps and the
confirm/demote decision; this module only assembles them.

The steps, in order:

  1. **Representation transfer** — the SAME KC in a different LIVE-renderable representation
     than recent work (so the surface can actually present and answer it). Catches a
     format-tied grip. PASS = the verifier says the answer is correct.
  2. **Error-finding (two steps)**, only for KCs with a modeled wrong-claim (addition /
     subtraction — the operation KCs, via ``build_error_finding_transfer_item``):
       a. *Reject* — "Tim says a/b + c/d = <wrong>. Is that right?" as a yes/no judgment
          whose truth is ``claimed == correct`` (so the right answer is NO). Catches a
          learner who endorses a wrong claim.
       b. *Supply* — "What is a/b + c/d, really?" a numeric item the learner must solve.
          The two-step pair operationalizes §3.9's "reject AND can justify" for a real
          learner without grading free text (a 2026-05-28 product decision): you can't
          supply the right value if you only pattern-matched the rejection.

Equivalence / number-line placement have no modeled wrong-claim, so their probe is the
representation item alone — an honest representation-transfer confirm gate.

Pure/deterministic, NO LLM/DB/SymPy here (it builds ``Problem``s and reuses the §3.9
item builders; the verifier judges, the service decides). PROJECT.md §4.1: fixed seeds.
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.policy.scheduler import live_representations
from app.tutor.transfer_probe import build_error_finding_transfer_item

# Fixed seeds keep the probe deterministic for a given KC (PROJECT.md §4.1); the probe is
# a one-shot confirm gate, so it does not need the per-turn variety the practice walk has.
_REPRESENTATION_SEED = 7
_ERROR_FINDING_SEED = 7


def _representation_transfer_format(
    kc: KnowledgeComponentId, recent_format: Representation
) -> Representation:
    """A LIVE-renderable representation of ``kc`` different from ``recent_format``.

    The §3.9 representation transfer must be a format the learner has NOT just worked, AND
    one the live surface can present and answer (every masterable KC advertises two such
    live representations — ``policy.scheduler``). Falls back to the KC's first live rep if
    ``recent_format`` is somehow not among them."""
    live = live_representations(kc)
    for representation in live:
        if representation != recent_format:
            return representation
    return live[0]


def build_live_probe_steps(
    kc: KnowledgeComponentId, *, recent_format: Representation
) -> list[Problem]:
    """The ordered probe steps for ``kc`` as ``Problem``s the live loop serves and the
    SymPy verifier judges. Representation transfer first; then, for the operation KCs, the
    two-step error-finding. All steps are judged uniformly by ``verify(step, answer)``."""
    steps: list[Problem] = []

    transfer_format = _representation_transfer_format(kc, recent_format)
    steps.append(generate_problem(kc, seed=_REPRESENTATION_SEED, surface_format=transfer_format))

    try:
        error_item = build_error_finding_transfer_item(kc, seed=_ERROR_FINDING_SEED)
    except ValueError:
        return steps  # no modeled wrong-claim for this KC → representation-only probe

    claimed = error_item.claimed_answer
    assert claimed is not None  # an error-finding item always carries its claim
    correct = error_item.problem.correct_value
    operands = error_item.problem.operands
    assert operands is not None and len(operands) == 2
    first, second = operands
    op = "+" if kc is KnowledgeComponentId.ADDITION_UNLIKE else "-"

    # Reject step: "Is the claim right?" — yes/no truth is claimed == correct (NO for a
    # wrong claim). Operands carry (claimed, correct) so the yes/no verifier compares them.
    reject = Problem(
        problem_id=f"PROBE-REJECT-{kc.value}",
        kc=kc,
        surface_format=Representation.SYMBOLIC,
        statement=(
            f"Tim says {first.p}/{first.q} {op} {second.p}/{second.q} "
            f"= {claimed.p}/{claimed.q}. Is that right?"
        ),
        correct_value=correct,
        representations_available=get_kc(kc).representations,
        operands=(claimed, correct),
        answer_kind=AnswerKind.YES_NO,
    )
    steps.append(reject)

    # Supply step: "What is it, really?" — a numeric item judged against the true value.
    supply = Problem(
        problem_id=f"PROBE-SUPPLY-{kc.value}",
        kc=kc,
        surface_format=Representation.SYMBOLIC,
        statement=f"What does {first.p}/{first.q} {op} {second.p}/{second.q} really equal?",
        correct_value=correct,
        representations_available=get_kc(kc).representations,
        operands=(first, second),
    )
    steps.append(supply)
    return steps


__all__ = ["build_live_probe_steps"]
