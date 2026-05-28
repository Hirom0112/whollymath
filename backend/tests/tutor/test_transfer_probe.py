"""The S5 transfer probe + transfer-item generation tests (Slice 3.7).

These are the §3.9 integration suite — the moment of truth that turns PROVISIONAL
mastery into CONFIRMED or demotes it (PROJECT.md §3.4, §3.5 S5, §3.9; ARCHITECTURE.md
§6, §7 the S5 → confirmed / S5 → S2/S3 edges). They are ALSO part of the mastery
model's integration suite (CLAUDE.md §9): the personas are the adversaries the probe
must catch.

Two layers are asserted:

  - the probe in isolation (``run_transfer_probe``): it generates the two §3.9 item
    types — representation transfer and error-finding — and decides BOTH-passed →
    CONFIRMED vs either-failed → FAIL-with-KC;
  - the probe wired into the reactive ``TutorSession`` (Slice 3.7): when the surface
    reaches S5 (the interleaved set passed, §3.6 row 6), ``run_transfer_probe`` runs
    the probe and routes the verdict — CONFIRMED, or demotion via the policy's
    ``TransferProbeFailed`` signal (§3.6 row 7).

The two adversarial catches are the headline (PROJECT.md §3.11):

  - **Procedure Priya — THE full catch** (closes the Week-2 NOTE in
    ``test_persona_integration.py``): she reaches provisional mastery via routine
    items, but the ERROR-FINDING transfer item catches her — she endorses the wrong
    claim (``can_justify=False``) — so the probe FAILS, she is NOT confirmed, and the
    loop demotes her to a scaffolded state.
  - **Surface Sam — representation transfer**: the representation-transfer item (a
    non-tied format) catches him — the SAME KC collapses to his add-across error — so
    the probe FAILS and he is NOT confirmed.

A genuinely-knowing (BOTH-mode) learner passes BOTH items → CONFIRMED, so the probe
is not trivially always-fail. Correctness is the tutor's own SymPy verifier
(ARCHITECTURE.md §9). No LLM, no DB, deterministic (PROJECT.md §4.1).
"""

from __future__ import annotations

from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.personas.persona_config import (
    BehavioralParameters,
    KnowledgeMode,
    KnowledgeState,
    PersonaConfig,
)
from app.personas.priya import PRIYA
from app.personas.sam import SAM
from app.policy.surface_states import SurfaceState
from app.tutor.session import TutorSession
from app.tutor.transfer_probe import (
    TransferItemType,
    build_error_finding_transfer_item,
    build_representation_transfer_item,
    run_transfer_probe,
)
from sympy import Rational

_KC_ADD = KnowledgeComponentId.ADDITION_UNLIKE
_KC_SUB = KnowledgeComponentId.SUBTRACTION_UNLIKE


# ─── A BOTH-mode "genuinely knows it" learner, as a TEST fixture ─────────────
#
# The task allows adding a BOTH-mode persona in the test file rather than editing the
# persona package (the five committed personas are all adversaries; none holds a KC in
# BOTH mode). Mastery Mia is the positive control: she genuinely understands addition,
# so she answers any format correctly AND rejects a wrong claim with justification —
# the learner the probe should CONFIRM. Deliberately not added to the persona registry
# (it is not one of the §4.2 five); it lives here only to prove the probe can pass.

_MASTERY_MIA = PersonaConfig(
    persona_id="mastery_mia",
    name="Mastery Mia",
    knowledge={_KC_ADD: KnowledgeState(kc_id=_KC_ADD, mode=KnowledgeMode.BOTH)},
    misconceptions=(),
    behavior=BehavioralParameters(
        response_latency_seconds=10.0,  # well above the engagement floor
        hint_request_probability=0.0,  # she does not lean on hints
        engagement_floor=0.9,
        scaffold_dependence_rate=0.1,
    ),
)


# ─── Transfer-item generation (§3.9) ─────────────────────────────────────────


def test_representation_transfer_item_uses_a_different_format_than_recent_work() -> None:
    """§3.9 representation transfer: the item presents the SAME KC in a representation
    DIFFERENT from the learner's recent work (§3.5 S5). Built from recent SYMBOLIC
    work, the item's format is not symbolic, and it is the same KC."""
    item = build_representation_transfer_item(
        _KC_ADD, recent_format=Representation.SYMBOLIC, seed=1
    )

    assert item.item_type is TransferItemType.REPRESENTATION
    assert item.problem.kc is _KC_ADD
    assert item.problem.surface_format != Representation.SYMBOLIC
    # A representation item asks the learner to solve; there is no claimed answer.
    assert item.claimed_answer is None


def test_error_finding_item_reuses_the_bank_wrong_claim() -> None:
    """§3.9 error-finding: the item presents a (wrong) claimed answer to reject,
    reused from the bank where available — ADD-004's 1/4 + 1/4 = 2/8 (claim 2/8, which
    equals 1/4) for addition, SUB-005's 5/6 - 1/3 = 4/3 for subtraction. The claim is
    a genuinely WRONG value (not the correct answer)."""
    add_item = build_error_finding_transfer_item(_KC_ADD, seed=1)
    sub_item = build_error_finding_transfer_item(_KC_SUB, seed=1)

    assert add_item.item_type is TransferItemType.ERROR_FINDING
    assert add_item.claimed_answer == Rational(2, 8)  # ADD-004's claim (== 1/4)
    assert add_item.claimed_answer != add_item.problem.correct_value  # genuinely wrong

    assert sub_item.claimed_answer == Rational(4, 3)  # SUB-005's claim
    assert sub_item.claimed_answer != sub_item.problem.correct_value


# ─── Procedure Priya — THE full catch (closes the Week-2 NOTE) ───────────────


def test_priya_transfer_probe_fails_caught_by_error_finding() -> None:
    """THE full catch (PROJECT.md §3.9, §4.2 P2): Priya reaches provisional mastery on
    addition via routine items, but the ERROR-FINDING transfer item catches her. She
    endorses the wrong claim (``can_justify`` is False), so the error-finding item
    FAILS and the probe FAILS overall — she is NOT confirmed. (Her representation
    transfer happens to pass: PROCEDURE_ONLY gets the routine answer right in any
    format; the error-finding item is what the §3.9 design adds precisely to catch
    her.)"""
    result = run_transfer_probe(PRIYA, _KC_ADD, recent_format=Representation.SYMBOLIC)

    assert result.passed is False, "Priya must NOT be confirmed — the §3.9 defense"
    assert result.failed_kc is _KC_ADD
    # The error-finding item is the one that caught her: she endorsed the wrong claim
    # and could not justify rejecting it (the procedure-without-concept tell, §4.2 P2).
    assert result.error_finding.passed is False
    assert result.error_finding.can_justify is False


def test_priya_full_catch_demotes_her_in_the_reactive_loop() -> None:
    """THE full catch, end-to-end through the reactive loop (Slice 3.7 wiring): Priya
    reaches S5 (interleaved set passed, §3.6 row 6), the transfer probe FAILS, she is
    NOT confirmed, and the policy ``TransferProbeFailed`` signal demotes her OFF S5 to
    a scaffolded state (§3.6 row 7). This is the demotion the Week-2 NOTE deferred to
    Slice 3.7."""
    session = TutorSession.cold_start(chosen_kc=_KC_ADD)
    # Routine addition correct in S1 (so recent work for this KC is SYMBOLIC).
    session.submit_answer("7/12", latency_ms=8_000)
    # The mastery model's interleaved-set-passed signal routes the surface to S5.
    session.interleaved_set_passed(_KC_ADD)
    assert session.surface_state is SurfaceState.TRANSFER_PROBE

    result = session.run_transfer_probe(PRIYA, _KC_ADD)

    assert result.passed is False
    # NOT confirmed: provisional mastery stays provisional (§3.4).
    assert session.is_confirmed(_KC_ADD) is False
    # Demoted off S5 to a scaffolded state (operation KC → S3, §3.6 row 7). Read into a
    # local so the earlier "is S5" assert does not narrow the type for the type-checker.
    final_state: SurfaceState = session.surface_state
    assert final_state is SurfaceState.FRACTION_BARS_PRIMARY


# ─── Surface Sam — representation transfer ───────────────────────────────────


def test_sam_transfer_probe_fails_caught_by_representation_transfer() -> None:
    """PROJECT.md §3.9 / §4.2 P4: Sam's grip on addition is tied to the SYMBOLIC
    format. The representation-transfer item presents the SAME KC in a NON-tied format,
    where his grip collapses to the add-across error — the verifier marks it wrong, so
    the representation item FAILS and the probe FAILS overall. He is NOT confirmed:
    format-mastery is not KC-mastery."""
    result = run_transfer_probe(SAM, _KC_ADD, recent_format=Representation.SYMBOLIC)

    assert result.passed is False, "Sam must NOT be confirmed — format ≠ KC mastery"
    assert result.failed_kc is _KC_ADD
    # The representation-transfer item is the one that caught him.
    assert result.representation.passed is False


def test_sam_representation_catch_demotes_him_in_the_reactive_loop() -> None:
    """Sam, end-to-end: reaches S5, the transfer probe FAILS (representation transfer),
    he is NOT confirmed, and the loop demotes him off S5 to a scaffolded state (§3.6
    row 7)."""
    session = TutorSession.cold_start(chosen_kc=_KC_ADD)
    # Sam's tied symbolic addition answer is correct (looks fluent) → recent SYMBOLIC.
    session.present_problem(kc=_KC_ADD, seed=1, surface_format=Representation.SYMBOLIC)
    correct = session.current_problem.correct_value
    session.submit_answer(f"{correct.p}/{correct.q}", latency_ms=6_000)
    session.interleaved_set_passed(_KC_ADD)
    assert session.surface_state is SurfaceState.TRANSFER_PROBE

    result = session.run_transfer_probe(SAM, _KC_ADD)

    assert result.passed is False
    assert session.is_confirmed(_KC_ADD) is False
    # Operation KC failure routes to the fraction bars (S3), §3.6 row 7. Local var so
    # the earlier "is S5" assert does not narrow the type for the type-checker.
    final_state: SurfaceState = session.surface_state
    assert final_state is SurfaceState.FRACTION_BARS_PRIMARY


# ─── A genuinely-knowing learner passes → CONFIRMED ──────────────────────────


def test_genuinely_knowing_learner_passes_both_transfer_items() -> None:
    """The probe is not trivially always-fail (PROJECT.md §3.9): a learner who
    genuinely knows the KC (BOTH mode) passes BOTH transfer items — correct in the
    different representation AND correctly rejects the wrong claim with justification —
    so the probe PASSES and mastery is CONFIRMED."""
    result = run_transfer_probe(_MASTERY_MIA, _KC_ADD, recent_format=Representation.SYMBOLIC)

    assert result.passed is True, "a genuine master must be CONFIRMED"
    assert result.failed_kc is None
    assert result.representation.passed is True
    assert result.error_finding.passed is True
    # The error-finding pass is a justified rejection, not luck (§3.9).
    assert result.error_finding.can_justify is True


def test_genuinely_knowing_learner_is_confirmed_in_the_reactive_loop() -> None:
    """End-to-end CONFIRM (Slice 3.7 wiring): a genuine master reaches S5, the probe
    PASSES, and the KC is marked CONFIRMED — provisional mastery becomes confirmed
    (§3.4). The surface stays in S5 (the §3.6 S5 → mastery-confirmed edge ends the walk
    for this KC; there is no demotion transition)."""
    session = TutorSession.cold_start(chosen_kc=_KC_ADD)
    session.submit_answer("7/12", latency_ms=10_000)
    session.interleaved_set_passed(_KC_ADD)
    assert session.surface_state is SurfaceState.TRANSFER_PROBE

    result = session.run_transfer_probe(_MASTERY_MIA, _KC_ADD)

    assert result.passed is True
    assert session.is_confirmed(_KC_ADD) is True
    # No demotion: the walk ends in S5 on a confirmed probe.
    assert session.surface_state is SurfaceState.TRANSFER_PROBE


# ─── Probe runs only in S5 (refuse-rule sequencing) ──────────────────────────


def test_probe_refuses_to_run_outside_s5() -> None:
    """S5 IS the transfer test (§3.5): the loop runs the probe only in S5. Calling it
    from another state fails loudly rather than probing out of sequence (CLAUDE.md
    §8.5)."""
    session = TutorSession.cold_start(chosen_kc=_KC_ADD)
    assert session.surface_state is SurfaceState.SYMBOLIC_FOCUS  # not S5

    try:
        session.run_transfer_probe(_MASTERY_MIA, _KC_ADD)
    except ValueError as exc:
        assert "S5" in str(exc) or "TRANSFER_PROBE" in str(exc)
    else:  # pragma: no cover — the call must raise
        raise AssertionError("run_transfer_probe should refuse to run outside S5")


# ─── Determinism (PROJECT.md §4.1; CLAUDE.md §9) ─────────────────────────────


def test_transfer_probe_is_deterministic() -> None:
    """Same (persona, KC, recent format, seeds) ⇒ identical probe verdict every run:
    same overall pass/fail, same per-item outcomes, same submitted answers. This
    reproducibility is what lets the probe sit in the persona integration suite."""
    for persona in (PRIYA, SAM, _MASTERY_MIA):
        first = run_transfer_probe(persona, _KC_ADD, recent_format=Representation.SYMBOLIC)
        second = run_transfer_probe(persona, _KC_ADD, recent_format=Representation.SYMBOLIC)

        assert first.passed == second.passed
        assert first.failed_kc == second.failed_kc
        assert first.representation.passed == second.representation.passed
        assert first.representation.submitted_answer == second.representation.submitted_answer
        assert first.error_finding.passed == second.error_finding.passed
        assert first.error_finding.submitted_answer == second.error_finding.submitted_answer


def test_reactive_probe_wiring_is_deterministic() -> None:
    """The full S5 → probe → confirm/demote wiring is deterministic: the same persona
    driven to S5 the same way reaches the same confirmation and the same final state
    every run."""

    def walk(persona: PersonaConfig) -> tuple[bool, SurfaceState]:
        session = TutorSession.cold_start(chosen_kc=_KC_ADD)
        session.submit_answer("7/12", latency_ms=10_000)
        session.interleaved_set_passed(_KC_ADD)
        session.run_transfer_probe(persona, _KC_ADD)
        return session.is_confirmed(_KC_ADD), session.surface_state

    for persona in (PRIYA, _MASTERY_MIA):
        assert walk(persona) == walk(persona)
