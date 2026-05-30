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

Equivalence / number-line placement have no modeled wrong-claim, so they cannot use the
error-finding pair. They get a SECOND representation-transfer item instead, in a third
distinct live representation, so their probe is still a genuine multi-representation gate
(≥2 items across ≥2 representations) — a single lucky item can never confirm mastery
(AUDIT.md §7, §3 cap 5; the research panel's "single item ≠ transfer" finding; PROJECT.md
§3.4 rule 2). For number-line placement that means the line's mark-on-a-line placement
item AND the symbolic magnitude comparison both appear, keeping the placement honest.

A per-step AUDIT TRAIL makes the verdict reconstructable: each entry records the item, the
representation, the submitted answer, and whether it was correct, so a confirm/demote
decision can be reconstructed from the trail alone (``build_probe_audit_trail``). The
service does not have to call it — the trail is reconstructable from the steps it already
serves plus the verifier's per-step verdict — but it is the first-class, tested artifact
that pins the "≥2 representations correct, not one lucky item" rule.

Pure/deterministic, NO LLM/DB/SymPy here (it builds ``Problem``s and reuses the §3.9
item builders; the verifier judges, the service decides). PROJECT.md §4.1: fixed seeds.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.lesson_spec import get_lesson_spec
from app.domain.problem_generators import AnswerKind, Problem, generate_problem
from app.policy.scheduler import live_representations
from app.tutor.transfer_probe import build_error_finding_transfer_item

# Fixed seeds keep the probe deterministic for a given KC (PROJECT.md §4.1); the probe is
# a one-shot confirm gate, so it does not need the per-turn variety the practice walk has.
# A SECOND seed for the second representation-transfer item keeps the two items distinct
# even when they happen to share a representation pool.
_REPRESENTATION_SEED = 7
_REPRESENTATION_SEED_2 = 11
_ERROR_FINDING_SEED = 7


def _representation_transfer_formats(
    kc: KnowledgeComponentId, recent_format: Representation
) -> list[Representation]:
    """LIVE-renderable representations of ``kc``, ordered so a format the learner has NOT
    just worked comes first.

    The §3.9 representation transfer must be a format the learner has NOT just worked, AND
    one the live surface can present and answer (every masterable KC advertises ≥2 such
    live representations — ``policy.scheduler``). We return ALL live representations with the
    not-recently-worked ones first, so a caller can take the first as the transfer item and a
    later distinct one as a second item — keeping the probe spanning ≥2 representations even
    for KCs with no modeled wrong-claim (AUDIT.md §7). Order is deterministic."""
    live = live_representations(kc)
    not_recent = [rep for rep in live if rep != recent_format]
    recent = [rep for rep in live if rep == recent_format]
    return not_recent + recent


def build_live_probe_steps(
    kc: KnowledgeComponentId, *, recent_format: Representation
) -> list[Problem]:
    """The ordered probe steps for ``kc`` as ``Problem``s the live loop serves and the
    SymPy verifier judges. Representation transfer first; then, for the operation KCs, the
    two-step error-finding. All steps are judged uniformly by ``verify(step, answer)``."""
    steps: list[Problem] = []

    transfer_formats = _representation_transfer_formats(kc, recent_format)

    # The error-finding reject/supply pair (operation KCs) is inherently SYMBOLIC, so the
    # representation-transfer item must contribute a DIFFERENT representation or the whole probe
    # would collapse to symbolic-only and fail the ≥2-representations gate (AUDIT.md §7,
    # PROJECT.md §3.4 rule 2). Prefer the first not-recently-worked NON-symbolic live format;
    # only fall back to symbolic if the KC has no other live representation.
    # Spec-driven (HR.A4): whether this lesson can pose a "reject this claim" error-finding item
    # is declared on its LessonSpec, not a hard-coded KC tuple — a new lesson opts in via its spec.
    has_error_finding = get_lesson_spec(kc).transfer_probe.has_error_finding
    if has_error_finding:
        transfer_format = next(
            (rep for rep in transfer_formats if rep is not Representation.SYMBOLIC),
            transfer_formats[0],
        )
    else:
        transfer_format = transfer_formats[0]
    steps.append(generate_problem(kc, seed=_REPRESENTATION_SEED, surface_format=transfer_format))

    try:
        error_item = build_error_finding_transfer_item(kc, seed=_ERROR_FINDING_SEED)
    except ValueError:
        # No modeled wrong-claim (equivalence / number-line placement): a single representation
        # item would let one lucky answer confirm mastery. Add a SECOND transfer item in a
        # DISTINCT live representation so the probe still spans ≥2 representations (AUDIT.md §7,
        # PROJECT.md §3.4 rule 2). For number-line placement this keeps both the line's
        # placement item and the symbolic comparison present, so the placement stays honest.
        second_format = next(
            (rep for rep in transfer_formats if rep != transfer_format),
            transfer_format,
        )
        steps.append(
            generate_problem(kc, seed=_REPRESENTATION_SEED_2, surface_format=second_format)
        )
        return steps

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


@dataclass(frozen=True)
class ProbeAuditEntry:
    """One reconstructable record of a single answered probe step (AUDIT.md §7).

    Each entry carries everything needed to reconstruct WHY a step passed or failed without
    consulting any other state: the item (``problem_id`` + the exact ``statement`` shown), the
    ``representation`` it was presented in, the learner's ``submitted_answer``, and the
    verifier's ``is_correct`` verdict for it. Frozen because an audit record is a fact, not
    mutable state (CLAUDE.md §8.4)."""

    problem_id: str
    kc: KnowledgeComponentId
    representation: Representation
    statement: str
    submitted_answer: str
    is_correct: bool


@dataclass(frozen=True)
class ProbeAuditTrail:
    """The per-step audit trail for one probe attempt, from which the verdict is fully
    reconstructable (AUDIT.md §7; the research panel's "single item ≠ transfer" finding).

    ``passed`` is true ONLY when EVERY step was correct — so getting one lucky item right can
    never confirm mastery — and ``representations_covered`` is the set of distinct
    representations the attempt actually answered. Both are derived purely from ``entries``,
    so a reviewer can recompute the verdict from the trail alone."""

    entries: tuple[ProbeAuditEntry, ...]

    @property
    def passed(self) -> bool:
        """Confirm only if every step is correct AND the attempt spanned ≥2 distinct
        representations — the ≥2-items-across-≥2-representations gate (PROJECT.md §3.4 rule 2,
        AUDIT.md §7). A one-item attempt (or an all-correct attempt that never left a single
        representation) does not pass."""
        return (
            len(self.entries) >= 2
            and len(self.representations_covered) >= 2
            and all(entry.is_correct for entry in self.entries)
        )

    @property
    def representations_covered(self) -> set[Representation]:
        """The distinct representations the attempt answered, recomputed from the entries."""
        return {entry.representation for entry in self.entries}


def build_probe_audit_trail(
    steps: list[Problem],
    *,
    submitted_answers: list[str],
    corrects: list[bool],
) -> ProbeAuditTrail:
    """Assemble the reconstructable per-step audit trail for one probe attempt.

    ``steps`` are the items from ``build_live_probe_steps``; ``submitted_answers`` and
    ``corrects`` are the learner's answer and the SymPy verifier's verdict for each step, in
    order (the service is the one that holds those, judged turn-by-turn — this builder does no
    judging itself, keeping SymPy in ``domain/`` per CLAUDE.md §8.2). The three lists must be
    the same length; a mismatch is a programming error and raises ``ValueError`` so a malformed
    audit can never silently look valid (CLAUDE.md §8.5)."""
    if not (len(steps) == len(submitted_answers) == len(corrects)):
        raise ValueError(
            "probe audit trail requires one submitted answer and one verdict per step "
            f"(got {len(steps)} steps, {len(submitted_answers)} answers, {len(corrects)} verdicts)"
        )
    entries = tuple(
        ProbeAuditEntry(
            problem_id=step.problem_id,
            kc=step.kc,
            representation=step.surface_format,
            statement=step.statement,
            submitted_answer=answer,
            is_correct=correct,
        )
        for step, answer, correct in zip(steps, submitted_answers, corrects, strict=True)
    )
    return ProbeAuditTrail(entries=entries)


__all__ = [
    "ProbeAuditEntry",
    "ProbeAuditTrail",
    "build_live_probe_steps",
    "build_probe_audit_trail",
]
