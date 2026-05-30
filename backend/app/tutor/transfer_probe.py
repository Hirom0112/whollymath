"""The S5 transfer probe + transfer-item generation (Slice 3.7).

This is the moment of truth that turns PROVISIONAL mastery into CONFIRMED — or
demotes it (PROJECT.md §3.4 "Mastery is then provisional until the transfer probe
(S5) is passed"; §3.5 S5; §3.9 the two transfer item types; ARCHITECTURE.md §6).
A learner reaches S5 only after the mandatory interleaved set passes (§3.6 row 6,
wired in ``tutor/session.py``); S5 then presents the transfer items, and the
verdict either CONFIRMS mastery or, on failure, feeds the policy
``TransferProbeFailed`` signal that demotes the learner back to scaffolded practice
(S2/S3 by the failed KC — the policy already owns that routing, §3.6 row 7).

The two transfer item types (PROJECT.md §3.9), generated here:

  1. **Representation transfer.** The SAME KC presented in a representation DIFFERENT
     from the learner's recent work — ``generate_problem(kc, seed, other_format)``.
     Catches Surface Sam, whose grip is tied to one format: format-mastery is not
     KC-mastery (§4.2 P4). Evaluated by the SymPy verifier (``domain.verifier.verify``)
     — correctness is the domain's job, never this module's, never an LLM's
     (CLAUDE.md §8.2; ARCHITECTURE.md §14 invariant 2).
  2. **Error-finding transfer.** An item that presents a (wrong) claimed answer and
     asks the learner to find the error ("Tim says 1/4 + 1/4 = 2/8 — why is he
     wrong?"). Catches Procedure Priya, who runs the procedure without the concept and
     so cannot reject a wrong claim (§4.2 P2). Driven via
     ``SimulationContext(request=FIND_ERROR, claimed_answer=...)``. The wrong claim is
     reused from the diagnostic-gem bank's error-finding items where one exists for the
     KC (ADD-004 = 2/8 for 1/4+1/4; SUB-005 = 4/3 for 5/6-1/3), otherwise it is
     constructed from the KC's named misconception's wrong value (add-across /
     subtract-across on the generated operands). PASS means the learner correctly
     REJECTS the wrong claim: ``is_correct AND can_justify`` on the FIND_ERROR turn —
     the §3.9 marker that distinguishes conceptual understanding from procedural
     fluency.

How the probe decides (PROJECT.md §3.9 "Both must be passed for mastery to be
declared confirmed"):

  - BOTH items passed  → ``TransferProbeResult.passed is True`` → mastery CONFIRMED.
  - EITHER item failed  → ``passed is False`` with the failed KC carried out, which
    the caller feeds to the policy as ``TransferProbeFailed`` → demotion to S2/S3.

Hard boundaries (the same ones the simulator and tutor already hold; CLAUDE.md
§8.1/§8.2, ARCHITECTURE.md §14): NO LLM, NO DB, NO SymPy here. SymPy correctness is
the verifier's job (``domain/verifier.py``); the wrong-claim VALUE is the
misconception generators' job (``domain/misconceptions.py``); the persona's action is
the Layer-3 simulator's job (``personas/simulator.py``). This module only assembles
the two items and routes their verdicts. Determinism (PROJECT.md §4.1): items are
seeded and the simulator is deterministic, so the SAME (persona, KC, recent format,
seed) yields the SAME probe result every call — which is what makes the probe usable
as part of the persona integration suite (CLAUDE.md §9).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sympy import Rational

from app.domain.knowledge_components import KnowledgeComponentId, Representation, get_kc
from app.domain.misconceptions import add_across, subtract_across
from app.domain.problem_generators import Problem, generate_problem
from app.domain.verifier import verify
from app.personas.persona_config import PersonaConfig
from app.personas.simulator import RequestType, SimulationContext, simulate_action

# ─── The two transfer item types (§3.9) ──────────────────────────────────────


class TransferItemType(StrEnum):
    """Which of the two §3.9 transfer item types a probe item is.

    A ``StrEnum`` so a result reads/serializes as its stable string (logs, the
    decision the reviewer sees). The two members are the §3.9 enumeration verbatim:
    representation transfer (catches Surface Sam) and error-finding transfer (catches
    Procedure Priya).
    """

    REPRESENTATION = "representation_transfer"
    ERROR_FINDING = "error_finding_transfer"


@dataclass(frozen=True)
class TransferItem:
    """One generated transfer item: the problem, its type, and its FIND_ERROR claim.

    Frozen — a generated probe item is a fact about the probe, not mutable state
    (ARCHITECTURE.md §14, CLAUDE.md §8.4). Fields:

    - ``item_type``  which §3.9 type this is.
    - ``problem``    the shared ``Problem`` the learner is shown. For a representation-
      transfer item this is the KC in a format different from recent work; for an
      error-finding item it is the KC's problem the wrong claim is about.
    - ``claimed_answer``  the (wrong) magnitude a FIND_ERROR item attributes to the
      fictional third party ("Tim wrote 2/8"); ``None`` for a representation item,
      which has no claimed answer to judge.
    """

    item_type: TransferItemType
    problem: Problem
    claimed_answer: Rational | None


@dataclass(frozen=True)
class TransferItemOutcome:
    """The recorded verdict on one transfer item — evidence the decision log reads.

    Frozen. ``passed`` is the per-item pass/fail; the other fields record exactly WHY,
    so a reviewer can see what each transfer item caught:

    - representation item: ``passed`` is the SymPy verifier's ``is_correct`` on the
      different-format problem (``submitted_answer`` is what the persona submitted).
    - error-finding item: ``passed`` is "correctly REJECTED the wrong claim" —
      ``is_correct AND can_justify`` on the FIND_ERROR turn (§3.9). ``can_justify``
      is carried so the procedure-without-concept tell is visible even when the
      submitted value happens to look right.
    """

    item_type: TransferItemType
    passed: bool
    submitted_answer: Rational | None
    can_justify: bool


@dataclass(frozen=True)
class TransferProbeResult:
    """The S5 probe verdict for one KC (PROJECT.md §3.9; ARCHITECTURE.md §6).

    Frozen. ``passed`` is True only when BOTH transfer items passed → mastery is
    CONFIRMED (no longer provisional). When False, ``failed_kc`` is the KC to feed
    the policy's ``TransferProbeFailed`` signal so it demotes the learner to S2/S3
    (§3.6 row 7). ``representation`` and ``error_finding`` carry the per-item outcomes
    so the caller / decision log sees which item caught a non-master.
    """

    kc: KnowledgeComponentId
    passed: bool
    failed_kc: KnowledgeComponentId | None
    representation: TransferItemOutcome
    error_finding: TransferItemOutcome


# ─── Item generation (§3.9) ───────────────────────────────────────────────────


def _representation_transfer_format(
    kc: KnowledgeComponentId, recent_format: Representation
) -> Representation:
    """Pick a representation for the KC DIFFERENT from the learner's recent work.

    PROJECT.md §3.9 representation transfer: present the SAME KC in a representation
    different from recent work (§3.5 S5: "a problem from a different representation
    than recent work"). We choose the first of the KC's advertised representations
    (``knowledge_components`` registry) that is not ``recent_format``. Every KC in
    scope advertises ≥ 2 representations, so a different one always exists; if a KC
    ever advertised only the recent format we raise rather than silently reuse it
    (CLAUDE.md §8.5 — fail loudly), because a same-format "transfer" item would not be
    a transfer at all.
    """
    for representation in get_kc(kc).representations:
        if representation != recent_format:
            return representation
    raise ValueError(
        f"{kc.value} advertises only {recent_format.value}; cannot build a "
        "representation-transfer item in a different format"
    )


def build_representation_transfer_item(
    kc: KnowledgeComponentId,
    *,
    recent_format: Representation,
    seed: int,
) -> TransferItem:
    """Build the §3.9 representation-transfer item: same KC, a DIFFERENT format.

    The problem is generated for ``kc`` in a representation other than
    ``recent_format`` (``generate_problem`` with the format PARAMETER, decision
    0.D.1). Seeded ⇒ deterministic. No claimed answer — this item asks the learner to
    solve, and the SymPy verifier judges it.
    """
    other_format = _representation_transfer_format(kc, recent_format)
    problem = generate_problem(kc, seed, other_format)
    return TransferItem(
        item_type=TransferItemType.REPRESENTATION,
        problem=problem,
        claimed_answer=None,
    )


# The bank's error-finding items, distilled to (KC → the wrong claim its "Tim says"
# statement presents). ADD-004: "Tim worked out 1/4 + 1/4 and wrote 2/8" → 2/8 == 1/4.
# SUB-005: "Tim worked out 5/6 - 1/3 and wrote 4/3" → 4/3. Reusing the bank's exact
# claims (PROJECT.md §3.9 "Reuse the bank's error-finding items where available")
# keeps the probe's wrong claim research-cited rather than invented; for the
# arithmetic operation KCs that have no bank error-finding item we fall back to the
# KC's misconception's wrong value (see ``_error_finding_claim``).
_BANK_ERROR_FINDING_CLAIM: dict[KnowledgeComponentId, Rational] = {
    KnowledgeComponentId.ADDITION_UNLIKE: Rational(2, 8),  # ADD-004 (claim about 1/4+1/4)
    KnowledgeComponentId.SUBTRACTION_UNLIKE: Rational(4, 3),  # SUB-005 (claim about 5/6-1/3)
}

# The exact operands the reused bank error-finding items are about, so the generated
# problem the claim is judged against is the bank item's own problem (not an unrelated
# generated one). ADD-004 is about 1/4 + 1/4; SUB-005 is about 5/6 - 1/3.
_BANK_ERROR_FINDING_OPERANDS: dict[KnowledgeComponentId, tuple[Rational, Rational]] = {
    KnowledgeComponentId.ADDITION_UNLIKE: (Rational(1, 4), Rational(1, 4)),
    KnowledgeComponentId.SUBTRACTION_UNLIKE: (Rational(5, 6), Rational(1, 3)),
}


def _misconception_claim(problem: Problem) -> Rational | None:
    """The wrong VALUE the KC's named misconception yields on this problem, or None.

    Replays the Layer-1 across-error generators (``domain/misconceptions.py``) on the
    problem's operands — the domain owns the arithmetic of the wrong answer; this only
    selects which error the fictional third party "made" so the FIND_ERROR item has a
    genuinely-wrong claim to reject. Used for operation KCs that have no bank
    error-finding item. Returns ``None`` when the KC/operands do not map to a modeled
    across-error (we never fabricate a claim the domain does not model).
    """
    operands = problem.operands
    if operands is None or len(operands) != 2:
        return None
    first, second = operands
    if problem.kc is KnowledgeComponentId.ADDITION_UNLIKE:
        wrong = add_across(first.p, first.q, second.p, second.q)
    elif problem.kc is KnowledgeComponentId.SUBTRACTION_UNLIKE:
        wrong = subtract_across(first.p, first.q, second.p, second.q)
    else:
        return None
    if wrong.denominator == 0:
        return None
    claim = wrong.as_rational()
    # A degenerate "wrong" claim that equals the correct value is not a wrong claim at
    # all (it could not catch anyone), so reject it rather than build a no-op item.
    if claim == problem.correct_value:
        return None
    return claim


def _build_bank_error_finding_item(kc: KnowledgeComponentId) -> TransferItem:
    """Build the error-finding item from the reused bank claim (ADD-004 / SUB-005).

    The problem is the bank item's own operands (so the claim is judged against the
    problem it is really about), assembled as the shared ``Problem`` type with a
    SymPy-computed correct value. We do NOT touch the JSON at runtime — the claim and
    operands are the bank's verified values, distilled into the maps above (the bank
    items themselves are exercised by the domain suite). The claim is the wrong value
    the bank's "Tim says" statement presents.
    """
    first, second = _BANK_ERROR_FINDING_OPERANDS[kc]
    is_addition = kc is KnowledgeComponentId.ADDITION_UNLIKE
    correct = first + second if is_addition else first - second
    claim = _BANK_ERROR_FINDING_CLAIM[kc]
    operator = "+" if is_addition else "-"
    # Display the claim in its UNREDUCED across-error form (1/4 + 1/4 = 2/8, not the SymPy-
    # reduced 1/4) — that unreduced fraction IS the misconception we want the learner to spot.
    # Rendering claim.p/claim.q would silently reduce 2/8 → 1/4 and hide the mistake. The
    # claimed VALUE (claimed_answer below) is unchanged; only the shown text is corrected.
    across = (
        add_across(first.p, first.q, second.p, second.q)
        if is_addition
        else subtract_across(first.p, first.q, second.p, second.q)
    )
    statement = (
        f"Tim says {first.p}/{first.q} {operator} {second.p}/{second.q} "
        f"= {across.numerator}/{across.denominator}. Is he right? If not, why?"
    )
    problem = Problem(
        problem_id=f"TRANSFER-FINDERR-{kc.value}",
        kc=kc,
        surface_format=Representation.SYMBOLIC,
        statement=statement,
        correct_value=correct,
        representations_available=get_kc(kc).representations,
        operands=(first, second),
    )
    return TransferItem(
        item_type=TransferItemType.ERROR_FINDING,
        problem=problem,
        claimed_answer=claim,
    )


def build_error_finding_transfer_item(
    kc: KnowledgeComponentId,
    *,
    seed: int,
) -> TransferItem:
    """Build the §3.9 error-finding item: a wrong claimed answer to reject.

    Prefers the bank's research-cited error-finding claim where one exists for the KC
    (ADD-004 / SUB-005 — "Reuse the bank's error-finding items where available",
    §3.9). For an operation KC with no bank item, it generates a problem (seeded ⇒
    deterministic) and constructs the wrong claim from the KC's named misconception
    (add-across / subtract-across). The item is driven via
    ``SimulationContext(request=FIND_ERROR, claimed_answer=...)`` and passed only when
    the learner correctly REJECTS the claim (``is_correct AND can_justify``).

    Raises ``ValueError`` if the KC neither has a bank error-finding item nor maps to a
    modeled across-error (equivalence / common-denominator / number-line placement) —
    those KCs have no canonical "wrong-procedure claim" to build an error-finding item
    from in this slice, so we fail loudly rather than ship a hollow probe (CLAUDE.md
    §8.5). The two operation KCs the personas attack (Priya runs addition/subtraction)
    both have bank items, so the probe covers them.
    """
    if kc in _BANK_ERROR_FINDING_CLAIM:
        return _build_bank_error_finding_item(kc)

    problem = generate_problem(kc, seed)
    claim = _misconception_claim(problem)
    if claim is None:
        raise ValueError(
            f"no error-finding claim available for {kc.value}: it has no bank "
            "error-finding item and no modeled across-error misconception"
        )
    return TransferItem(
        item_type=TransferItemType.ERROR_FINDING,
        problem=problem,
        claimed_answer=claim,
    )


# ─── Per-item evaluation ──────────────────────────────────────────────────────


def _evaluate_representation_item(
    persona: PersonaConfig, item: TransferItem
) -> TransferItemOutcome:
    """Evaluate a representation-transfer item: SymPy verdict on the persona's answer.

    The persona answers a routine (ANSWER) turn on the different-format problem; the
    SymPy verifier (``domain.verifier.verify``) decides correctness (§9 — never this
    module). PASS = the verifier says correct. This is what catches Surface Sam: in a
    format his grip is not tied to, the same KC collapses to his add-across wrong
    answer, the verifier marks it incorrect, and the item FAILS.
    """
    action = simulate_action(persona, item.problem)
    submitted = action.submitted_answer
    is_correct = submitted is not None and verify(item.problem, submitted).is_correct
    return TransferItemOutcome(
        item_type=TransferItemType.REPRESENTATION,
        passed=is_correct,
        submitted_answer=submitted,
        can_justify=action.can_justify,
    )


def _evaluate_error_finding_item(persona: PersonaConfig, item: TransferItem) -> TransferItemOutcome:
    """Evaluate an error-finding item: did the learner correctly REJECT the wrong claim?

    The persona judges the claimed (wrong) answer on a FIND_ERROR turn (§3.9). PASS
    requires BOTH (§3.9): the learner does not endorse the wrong claim — the verifier
    marks the submitted answer correct (i.e. they supplied the right value, not Tim's
    wrong one) — AND they can justify the rejection (``can_justify``). This is what
    catches Procedure Priya: she endorses the wrong claim with ``can_justify=False``,
    so the item FAILS even though her routine answers look fluent.
    """
    context = SimulationContext(
        request=RequestType.FIND_ERROR,
        claimed_answer=item.claimed_answer,
    )
    action = simulate_action(persona, item.problem, context=context)
    submitted = action.submitted_answer
    rejected_wrong_claim = submitted is not None and verify(item.problem, submitted).is_correct
    passed = rejected_wrong_claim and action.can_justify
    return TransferItemOutcome(
        item_type=TransferItemType.ERROR_FINDING,
        passed=passed,
        submitted_answer=submitted,
        can_justify=action.can_justify,
    )


# ─── The probe ──────────────────────────────────────────────────────────────


def run_transfer_probe(
    persona: PersonaConfig,
    kc: KnowledgeComponentId,
    *,
    recent_format: Representation,
    representation_seed: int = 0,
    error_finding_seed: int = 0,
) -> TransferProbeResult:
    """Run the S5 transfer probe for ``kc`` against ``persona`` (PROJECT.md §3.9).

    Given a KC the mastery model has declared PROVISIONALLY mastered, presents BOTH
    §3.9 transfer items and evaluates them:

      1. a representation-transfer item — the KC in a format different from
         ``recent_format`` — judged by the SymPy verifier;
      2. an error-finding item — a wrong claimed answer (bank-reused where available,
         else constructed from the KC's misconception) — passed only when the learner
         correctly REJECTS it (``is_correct AND can_justify``).

    Returns a ``TransferProbeResult``: ``passed`` is True only when BOTH items pass →
    mastery CONFIRMED. Otherwise ``passed`` is False and ``failed_kc`` is ``kc``, which
    the caller feeds to the policy as ``TransferProbeFailed`` to demote the learner to
    S2/S3 (§3.6 row 7 — the policy owns that routing). Deterministic: seeded items + a
    deterministic simulator ⇒ the same verdict every call (PROJECT.md §4.1).
    """
    representation_item = build_representation_transfer_item(
        kc, recent_format=recent_format, seed=representation_seed
    )
    error_finding_item = build_error_finding_transfer_item(kc, seed=error_finding_seed)

    representation_outcome = _evaluate_representation_item(persona, representation_item)
    error_finding_outcome = _evaluate_error_finding_item(persona, error_finding_item)

    passed = representation_outcome.passed and error_finding_outcome.passed
    return TransferProbeResult(
        kc=kc,
        passed=passed,
        failed_kc=None if passed else kc,
        representation=representation_outcome,
        error_finding=error_finding_outcome,
    )


__all__ = [
    "TransferItem",
    "TransferItemOutcome",
    "TransferItemType",
    "TransferProbeResult",
    "build_error_finding_transfer_item",
    "build_representation_transfer_item",
    "run_transfer_probe",
]
