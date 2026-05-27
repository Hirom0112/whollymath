"""End-to-end session-walk tests for the tutor orchestrator (Slice 1.7).

This is the Week-1 Friday checkpoint asserted as code: "the domain model walks
through a hardcoded session correctly" (PROJECT.md §6). The tutor session loop
(``app/tutor/session.py``) orchestrates the already-tested Layer-1 domain and the
mastery model; these tests do NOT re-test SymPy verification or the BKT math
(those have their own suites). They assert the *orchestration*:

  - the two-step cold start (locked decision 0.D.2): a kid-friendly routing
    choice seeds a BKT prior (a prior, NOT a commitment), and Turn 1 presents the
    locked calibration problem for the chosen route;
  - the session loop (S1 only this week — PROJECT.md §3.6 NOTE: state
    transitions are Slice 2.4): present in S1, accept an answer, verify via the
    domain, build a mastery ``Observation``, update the in-session mastery view,
    append the turn to history, and report a result;
  - the surface stays S1 throughout (no transitions this week).

Determinism (CLAUDE.md §2; PROJECT.md §4.1): the session is seeded, so the same
inputs walk the same path every run.
"""

from __future__ import annotations

from app.api.schemas import SurfaceState
from app.domain.knowledge_components import KnowledgeComponentId, Representation
from app.domain.verifier import ErrorCategory
from app.mastery.mastery_model import initial_prior_from_self_report
from app.tutor.session import (
    UNSURE_ROUTE,
    TutorSession,
    routing_choices,
)
from sympy import Rational

# ─── Turn 0: routing → prior seed (0.D.2) ──────────────────────────────────


def test_routing_offers_three_kc_options_plus_deemphasized_unsure() -> None:
    """The routing question offers three KC options + a de-emphasized 'I'm not
    sure' default (0.D.2). The unsure option maps to KC_equivalence and is flagged
    de-emphasized so the surface can render it lower-weight (no quiz framing)."""
    choices = routing_choices()

    kc_options = [c for c in choices if not c.is_unsure_default]
    unsure = [c for c in choices if c.is_unsure_default]

    assert len(kc_options) == 3
    assert len(unsure) == 1
    # The three real options map to distinct KCs.
    assert len({c.routes_to for c in kc_options}) == 3
    # The de-emphasized default routes to equivalence (0.D.2).
    assert unsure[0].routes_to == KnowledgeComponentId.EQUIVALENCE
    assert unsure[0] is UNSURE_ROUTE


def test_routing_into_a_kc_seeds_its_prior_above_the_unsure_default() -> None:
    """Routing into a KC seeds that KC's BKT prior ABOVE the unsure default for the
    other KCs — the self-report is a prior, not a commitment (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    chosen_prior = session.prior_for(KnowledgeComponentId.ADDITION_UNLIKE)
    other_prior = session.prior_for(KnowledgeComponentId.EQUIVALENCE)

    assert chosen_prior > other_prior
    # Matches the mastery model's documented seeding (single source of truth).
    assert chosen_prior == initial_prior_from_self_report(
        KnowledgeComponentId.ADDITION_UNLIKE,
        chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE,
    )


def test_unsure_route_seeds_equivalence_at_the_unsure_default() -> None:
    """The 'I'm not sure' default seeds no KC above the default (chosen_kc is
    None): every prior is the unsure-default value (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=None)

    # Every KC sits at the unsure default; nothing is elevated.
    priors = {kc: session.prior_for(kc) for kc in KnowledgeComponentId}
    assert len(set(priors.values())) == 1


# ─── Turn 1: the locked calibration problem per route (0.D.2) ──────────────


def test_addition_route_calibration_is_one_third_plus_one_quarter() -> None:
    """Addition route → the locked Turn-1 calibration problem '1/3 + 1/4' (0.D.2),
    presented in S1, with the SymPy-correct value 7/12 and no preemptive hint."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert problem.operands == (Rational(1, 3), Rational(1, 4))
    assert problem.correct_value == Rational(7, 12)
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS
    # No hint is offered preemptively at calibration (0.D.2; refuse-rule 5).
    assert session.last_turn is None


def test_equivalence_route_calibration_is_two_thirds_equals_four_sixths() -> None:
    """Equivalence route → the locked 'is 2/3 = 4/6?' calibration item (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.EQUIVALENCE)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.EQUIVALENCE
    assert problem.operands == (Rational(2, 3), Rational(4, 6))


def test_number_line_route_calibration_places_three_fifths() -> None:
    """Number-line route → place 3/5 (0.D.2): correct_value is the magnitude 3/5."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    assert problem.correct_value == Rational(3, 5)
    assert problem.operands == (Rational(3, 5),)


def test_unsure_route_calibration_is_the_equivalence_item() -> None:
    """The 'I'm not sure'/default route uses the equivalence calibration (0.D.2)."""
    session = TutorSession.cold_start(chosen_kc=None)
    problem = session.current_problem

    assert problem.kc == KnowledgeComponentId.EQUIVALENCE
    assert problem.operands == (Rational(2, 3), Rational(4, 6))


def test_routing_choice_object_drives_cold_start() -> None:
    """cold_start accepts the RouteOption the surface returns, mapping it to its
    chosen KC (the unsure option → None, so it seeds at the unsure default)."""
    add_option = next(
        c for c in routing_choices() if c.routes_to == KnowledgeComponentId.ADDITION_UNLIKE
    )
    session = TutorSession.from_route(add_option)
    assert session.current_problem.kc == KnowledgeComponentId.ADDITION_UNLIKE

    unsure_session = TutorSession.from_route(UNSURE_ROUTE)
    # Unsure routes to equivalence as a calibration target but seeds no KC above
    # the default (it was a default, not a self-claim).
    assert unsure_session.current_problem.kc == KnowledgeComponentId.EQUIVALENCE
    priors = {kc: unsure_session.prior_for(kc) for kc in KnowledgeComponentId}
    assert len(set(priors.values())) == 1


# ─── The session loop: verify → mastery → record (S1 only) ──────────────────


def test_correct_calibration_answer_verifies_true_and_raises_mastery() -> None:
    """Submitting the correct calibration answer verifies True and raises the
    chosen KC's in-session mastery probability above its cold-start prior. S1 only:
    the surface does not change (transitions are Slice 2.4)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)
    prior = session.mastery_probability(KnowledgeComponentId.ADDITION_UNLIKE)

    result = session.submit_answer("7/12", latency_ms=8_000)

    assert result.correct is True
    assert result.error_category == ErrorCategory.NONE
    after = session.mastery_probability(KnowledgeComponentId.ADDITION_UNLIKE)
    assert after > prior
    # S1 only — no transition this week (PROJECT.md §3.6 NOTE).
    assert result.surface_state == SurfaceState.SYMBOLIC_FOCUS
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS
    # A snapshot for the answered KC is in the result.
    snapshot_kcs = {s.kc for s in result.mastery_snapshot}
    assert KnowledgeComponentId.ADDITION_UNLIKE in snapshot_kcs


def test_add_across_wrong_answer_verifies_false_with_operation_error() -> None:
    """The add-across error on 1/3 + 1/4 (= 2/7) verifies False and is classified
    OPERATION (a wrong-procedure error), per the domain verifier."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    # add-across of 1/3 + 1/4 is (1+1)/(3+4) = 2/7.
    result = session.submit_answer("2/7", latency_ms=6_000)

    assert result.correct is False
    assert result.error_category == ErrorCategory.OPERATION
    # Feedback is a single non-empty line (the surface label; refuse-rule 4 shape).
    assert result.feedback
    assert "\n" not in result.feedback


def test_session_records_turns_in_order_and_stays_in_s1() -> None:
    """The session records each turn in submission order, and the surface stays S1
    across the whole walk (no transitions this week)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("2/7", latency_ms=6_000)  # add-across wrong
    session.present_problem(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        seed=42,
        surface_format=Representation.SYMBOLIC,
    )
    correct = session.current_problem.correct_value
    session.submit_answer(f"{correct.p}/{correct.q}", latency_ms=9_000)

    history = session.history
    assert len(history) == 2
    # Recorded in order: first wrong, then correct.
    assert history[0].result.correct is False
    assert history[1].result.correct is True
    # Surface never left S1.
    assert all(turn.surface_state == SurfaceState.SYMBOLIC_FOCUS for turn in history)
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS


def test_observation_records_representation_hint_and_latency() -> None:
    """Each recorded turn carries the mastery Observation the loop built from it:
    the KC, correctness, representation, hinted flag, and latency — the fields the
    mastery model's §3.4 rules range over."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    session.submit_answer("7/12", latency_ms=8_000, hint_used=True)
    obs = session.history[-1].observation

    assert obs.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert obs.correct is True
    assert obs.representation == Representation.SYMBOLIC
    assert obs.hinted is True
    assert obs.latency_ms == 8_000


def test_self_report_is_never_echoed_but_logged_as_calibration_signal() -> None:
    """0.D.2: the self-report is never referenced back to the learner; predicted-
    vs-actual is logged as a metacognitive-calibration signal only (not acted on).
    The signal records the routed KC and whether the Turn-1 attempt was correct,
    and the learner-facing feedback never mentions the route."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.ADDITION_UNLIKE)

    result = session.submit_answer("7/12", latency_ms=8_000)

    signal = session.calibration_signal
    assert signal is not None
    assert signal.self_reported_kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert signal.first_attempt_correct is True
    # The feedback must not echo the route/self-report back to the learner.
    assert "addition" not in result.feedback.lower()
    assert "route" not in result.feedback.lower()


def test_present_problem_uses_a_generator_problem_in_s1() -> None:
    """present_problem swaps in a fresh generated problem for a KC in S1 without
    changing the surface state (S1 only this week)."""
    session = TutorSession.cold_start(chosen_kc=KnowledgeComponentId.EQUIVALENCE)
    session.present_problem(
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        seed=7,
        surface_format=Representation.SYMBOLIC,
    )
    assert session.current_problem.kc == KnowledgeComponentId.ADDITION_UNLIKE
    assert session.surface_state == SurfaceState.SYMBOLIC_FOCUS
