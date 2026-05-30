"""Tests for the EDM Cup 2023 / ASSISTments parser (Slice 3.2).

TDD-mandatory module: the HelpNeed predictor's training data flows through this
parser, and silent data corruption here would silently corrupt the model
(CLAUDE.md §2, §8.5). Tests assert the per-turn aggregation contract, fraction
filtering + KC mapping (PROJECT.md §3.7), determinism (§4.1), and bounded-memory
streaming. Feature engineering (latency windows, recent-error rates) is OUT OF
SCOPE here — that is Slice 3.3 — so the tests stop at ``EdmCupTurn``.
"""

from __future__ import annotations

import os
from io import StringIO
from pathlib import Path
from textwrap import dedent

import pytest
from app.domain.knowledge_components import KnowledgeComponentId
from app.helpneed.parse_edmcup import (
    EdmCupTurn,
    ParseStats,
    load_fraction_problems,
    map_ccss_to_kc,
    parse_action_logs,
)

# ─── Fixtures: tiny in-memory CSVs that exercise the parser shape ──────────────

_ACTION_HEADER = (
    "assignment_log_id,timestamp,problem_id,max_attempts,available_core_tutoring,"
    "score_viewable,continuous_score_viewable,action,hint_id,explanation_id\n"
)


def _action_row(
    *,
    assignment: str,
    ts: int,
    problem: str,
    action: str,
    hint_id: str = "",
    max_attempts: str = "3",
) -> str:
    """Build one action_logs CSV row matching the verified production schema."""
    return f"{assignment},{ts},{problem},{max_attempts},1.0,1.0,1.0,{action},{hint_id},\n"


def _problem_details_csv(rows: list[tuple[str, str]]) -> str:
    """Build a problem_details CSV from ``(problem_id, ccss_code)`` pairs.

    Other columns are filled with valid-but-uninteresting values; the parser only
    consumes problem_id and problem_skill_code.
    """
    header = (
        "problem_id,problem_multipart_id,problem_multipart_position,problem_type,"
        "problem_skill_code,problem_skill_description,problem_contains_image,"
        "problem_contains_equation,problem_contains_video,problem_text_bert_pca\n"
    )
    body = "".join(
        f"{pid},MP_{pid},1,Multiple Choice,{ccss},Skill,0.0,0.0,0.0,[]\n" for pid, ccss in rows
    )
    return header + body


def _write_problem_details(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    """Write a problem_details fixture to disk and return its path."""
    path = tmp_path / "problem_details.csv"
    path.write_text(_problem_details_csv(rows))
    return path


def _write_action_logs(tmp_path: Path, body: str) -> Path:
    """Write an action_logs fixture to disk and return its path."""
    path = tmp_path / "action_logs.csv"
    path.write_text(_ACTION_HEADER + body)
    return path


# ─── CCSS → KC mapping ────────────────────────────────────────────────────────


def test_map_ccss_to_kc_number_line_placement_3nfa2() -> None:
    """3.NF.A.2 (placing a fraction on a number line) → NUMBER_LINE_PLACEMENT."""
    assert map_ccss_to_kc("3.NF.A.2") == KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    assert map_ccss_to_kc("3.NF.A.2a") == KnowledgeComponentId.NUMBER_LINE_PLACEMENT
    assert map_ccss_to_kc("3.NF.A.2b") == KnowledgeComponentId.NUMBER_LINE_PLACEMENT


def test_map_ccss_to_kc_equivalence_family() -> None:
    """3.NF.A.1, 3.NF.A.3, and 4.NF.A.* are the equivalence family."""
    assert map_ccss_to_kc("3.NF.A.1") == KnowledgeComponentId.EQUIVALENCE
    assert map_ccss_to_kc("3.NF.A.3") == KnowledgeComponentId.EQUIVALENCE
    assert map_ccss_to_kc("3.NF.A.3a") == KnowledgeComponentId.EQUIVALENCE
    assert map_ccss_to_kc("4.NF.A.1") == KnowledgeComponentId.EQUIVALENCE
    assert map_ccss_to_kc("4.NF.A.2") == KnowledgeComponentId.EQUIVALENCE


def test_map_ccss_to_kc_addition_family() -> None:
    """4.NF.B.* (like-denom add/sub precursor) and 5.NF.A.* (unlike) → ADDITION_UNLIKE.

    The CCSS code alone cannot distinguish 5.NF.A.1 add from 5.NF.A.2 subtract
    (both code add/subtract); see the module docstring's documented limitation.
    """
    assert map_ccss_to_kc("4.NF.B.3") == KnowledgeComponentId.ADDITION_UNLIKE
    assert map_ccss_to_kc("4.NF.B.3a") == KnowledgeComponentId.ADDITION_UNLIKE
    assert map_ccss_to_kc("5.NF.A.1") == KnowledgeComponentId.ADDITION_UNLIKE
    assert map_ccss_to_kc("5.NF.A.2") == KnowledgeComponentId.ADDITION_UNLIKE


def test_map_ccss_to_kc_out_of_scope_codes_return_none() -> None:
    """Genuinely out-of-scope codes must still be EXCLUDED after the Grade-6 widening:
    Gr-4 mult-by-whole (4.NF.B.4), Gr-4 decimals (4.NF.C), the fraction-as-division
    concept (5.NF.B.3), bare codes with no sub-letter we map, and non-content strings.
    """
    assert map_ccss_to_kc("4.NF.B.4") is None  # multiplying fraction × whole (Gr 4)
    assert map_ccss_to_kc("4.NF.B.4a") is None
    assert map_ccss_to_kc("4.NF.C.5") is None  # decimal notation
    assert map_ccss_to_kc("4.NF.C.6") is None
    assert map_ccss_to_kc("5.NF.B.3") is None  # interpret a fraction as division (concept)
    assert map_ccss_to_kc("6.RP.A.3") is None  # bare cluster code, no sub-letter in our map
    assert map_ccss_to_kc("") is None
    assert map_ccss_to_kc("not.a.code") is None


def test_map_ccss_to_kc_grade6_and_adjacent_grade_codes() -> None:
    """The cross-topic widening: real Grade-6 cluster-letter codes (with the corpus's
    ``-N`` suffix splits) and the adjacent-grade recovery rows map to the right KC.
    Pins the contract T2's training harness mirrors (T1_T2_COORDINATION.md §4)."""
    KC = KnowledgeComponentId  # noqa: N806 — local alias keeps the assertions readable
    # Suffix split is covered by startswith.
    assert map_ccss_to_kc("6.RP.A.3c-1") == KC.PERCENT
    assert map_ccss_to_kc("6.NS.A.1") == KC.DIVIDE_FRACTIONS
    # 6.EE.6 lives in cluster B, not A — the bug T2 caught.
    assert map_ccss_to_kc("6.EE.B.6") == KC.WRITE_EXPRESSIONS
    assert map_ccss_to_kc("6.EE.A.2c") == KC.EVALUATE_EXPRESSIONS
    # 6.NS.6 split: 6c → number line, 6b → coordinate plane (per CURRICULUM_STANDARD U3 L2/L6).
    assert map_ccss_to_kc("6.NS.C.6c") == KC.RATIONALS_ON_LINE
    assert map_ccss_to_kc("6.NS.C.6b") == KC.COORDINATE_PLANE
    # Order-sensitive: 6.SP.B.5c (MAD) must win over the broader 6.SP.B.5 (summary stats).
    assert map_ccss_to_kc("6.SP.B.5c") == KC.MEAN_ABSOLUTE_DEVIATION
    assert map_ccss_to_kc("6.SP.B.5a") == KC.SUMMARY_STATISTICS
    # Adjacent-grade recovery: integers (CCSS Gr 7) and multiply/divide fractions (CCSS Gr 5).
    assert map_ccss_to_kc("7.NS.A.1") == KC.INTEGER_ADD_SUBTRACT
    assert map_ccss_to_kc("7.NS.A.2") == KC.INTEGER_MULTIPLY_DIVIDE
    assert map_ccss_to_kc("5.NF.B.4") == KC.MULTIPLY_FRACTIONS
    assert map_ccss_to_kc("5.NF.B.7") == KC.DIVIDE_FRACTIONS  # division precursor


# ─── load_fraction_problems ───────────────────────────────────────────────────


def test_load_fraction_problems_keeps_only_in_scope_codes(tmp_path: Path) -> None:
    """The fraction filter must keep ONLY the codes we teach and map them to KCs."""
    path = _write_problem_details(
        tmp_path,
        [
            ("P_NL", "3.NF.A.2a"),  # in scope: NUMBER_LINE_PLACEMENT
            ("P_EQ", "4.NF.A.1"),  # in scope: EQUIVALENCE
            ("P_ADD", "5.NF.A.1"),  # in scope: ADDITION_UNLIKE
            ("P_MULT", "5.NF.B.3"),  # out of scope (mult/div)
            ("P_RP", "6.RP.A.3"),  # out of scope (non-NF)
            ("P_DEC", "4.NF.C.5"),  # out of scope (decimals)
        ],
    )
    fraction_problems = load_fraction_problems(path)
    assert set(fraction_problems.keys()) == {"P_NL", "P_EQ", "P_ADD"}
    assert fraction_problems["P_NL"] == ("3.NF.A.2a", KnowledgeComponentId.NUMBER_LINE_PLACEMENT)
    assert fraction_problems["P_EQ"] == ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE)
    assert fraction_problems["P_ADD"] == ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)


def test_load_fraction_problems_skips_blank_ccss(tmp_path: Path) -> None:
    """Problems with no skill code at all are silently skipped (not an error)."""
    path = _write_problem_details(tmp_path, [("P_OK", "5.NF.A.1"), ("P_BLANK", "")])
    result = load_fraction_problems(path)
    assert "P_OK" in result
    assert "P_BLANK" not in result


# ─── parse_action_logs: the verified sample sequence (the contract) ───────────


def test_parse_action_logs_verified_sample_sequence(tmp_path: Path) -> None:
    """The brief's verified single-problem sequence yields exactly the expected turn.

    Sequence (problem I2GX4OQIE on assignment A1):
        problem_started   ts=1599150990
        wrong_response    ts=1599151065
        wrong_response    ts=1599151090
        answer_requested  ts=1599151096
        correct_response  ts=1599151114

    Expected turn:
        correct=True, first_attempt_correct=False, attempt_count=3 (2 wrong + 1 correct),
        hint_count=0, requested_answer=True,
        latency_ms_to_first_response = (1599151065 - 1599150990) * 1000 = 75_000,
        total_latency_ms             = (1599151114 - 1599150990) * 1000 = 124_000.
    """
    body = (
        _action_row(assignment="A1", ts=1599150990, problem="I2GX4OQIE", action="problem_started")
        + _action_row(assignment="A1", ts=1599151065, problem="I2GX4OQIE", action="wrong_response")
        + _action_row(assignment="A1", ts=1599151090, problem="I2GX4OQIE", action="wrong_response")
        + _action_row(
            assignment="A1", ts=1599151096, problem="I2GX4OQIE", action="answer_requested"
        )
        + _action_row(
            assignment="A1", ts=1599151114, problem="I2GX4OQIE", action="correct_response"
        )
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {
        "I2GX4OQIE": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE),
    }
    turns = list(parse_action_logs(action_logs, fraction_problems))

    assert len(turns) == 1
    turn = turns[0]
    assert turn == EdmCupTurn(
        assignment_log_id="A1",
        problem_id="I2GX4OQIE",
        ccss_code="5.NF.A.1",
        kc=KnowledgeComponentId.ADDITION_UNLIKE,
        correct=True,
        first_attempt_correct=False,
        attempt_count=3,
        hint_count=0,
        requested_answer=True,
        latency_ms_to_first_response=75_000,
        total_latency_ms=124_000,
    )


# ─── First-attempt-correct (no hint, no wrong response) ───────────────────────


def test_parse_action_logs_first_attempt_correct(tmp_path: Path) -> None:
    """An unaided immediate correct_response is first_attempt_correct=True."""
    body = _action_row(
        assignment="A1", ts=1000, problem="P1", action="problem_started"
    ) + _action_row(assignment="A1", ts=1005, problem="P1", action="correct_response")
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE)}
    (turn,) = list(parse_action_logs(action_logs, fraction_problems))

    assert turn.first_attempt_correct is True
    assert turn.correct is True
    assert turn.attempt_count == 1
    assert turn.hint_count == 0
    assert turn.requested_answer is False
    assert turn.latency_ms_to_first_response == 5_000
    assert turn.total_latency_ms == 5_000


# ─── Hint usage disqualifies first_attempt_correct ────────────────────────────


def test_parse_action_logs_hint_before_response_disqualifies_first_attempt(
    tmp_path: Path,
) -> None:
    """A hint event (non-empty hint_id) before the first response taints first attempt.

    A hint-then-correct sequence still has first_attempt_correct=False per the
    PROJECT.md §3.7 definition (the assistance signal must be reflected).
    """
    body = (
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + _action_row(
            assignment="A1",
            ts=1010,
            problem="P1",
            action="hint_requested",
            hint_id="H1",
        )
        + _action_row(assignment="A1", ts=1020, problem="P1", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    (turn,) = list(parse_action_logs(action_logs, fraction_problems))

    assert turn.hint_count == 1
    assert turn.first_attempt_correct is False
    assert turn.correct is True
    assert turn.attempt_count == 1  # one correct_response; the hint is not an attempt


# ─── Out-of-scope problems are silently filtered out, not yielded ─────────────


def test_parse_action_logs_filters_non_fraction_problems(tmp_path: Path) -> None:
    """Actions on a non-fraction problem are dropped before being assembled into turns."""
    body = (
        _action_row(assignment="A1", ts=1000, problem="P_RP", action="problem_started")
        + _action_row(assignment="A1", ts=1010, problem="P_RP", action="correct_response")
        + _action_row(assignment="A1", ts=2000, problem="P_FRAC", action="problem_started")
        + _action_row(assignment="A1", ts=2050, problem="P_FRAC", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    # Only P_FRAC is in the in-scope map; P_RP (a ratios problem) is absent.
    fraction_problems = {"P_FRAC": ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE)}
    turns = list(parse_action_logs(action_logs, fraction_problems))

    assert [t.problem_id for t in turns] == ["P_FRAC"]


# ─── Multi-assignment / multi-problem: no cross-session leakage ───────────────


def test_parse_action_logs_no_cross_session_leakage(tmp_path: Path) -> None:
    """Two assignments on the same problem must NOT be merged into one turn."""
    body = (
        # Assignment A1, problem P1: wrong, wrong, correct.
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + _action_row(assignment="A1", ts=1010, problem="P1", action="wrong_response")
        + _action_row(assignment="A1", ts=1020, problem="P1", action="wrong_response")
        + _action_row(assignment="A1", ts=1030, problem="P1", action="correct_response")
        # Assignment A2, problem P1: a clean first-attempt correct.
        + _action_row(assignment="A2", ts=5000, problem="P1", action="problem_started")
        + _action_row(assignment="A2", ts=5005, problem="P1", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    turns = list(parse_action_logs(action_logs, fraction_problems))

    assert len(turns) == 2
    by_assignment = {t.assignment_log_id: t for t in turns}
    assert by_assignment["A1"].attempt_count == 3
    assert by_assignment["A1"].first_attempt_correct is False
    assert by_assignment["A2"].attempt_count == 1
    assert by_assignment["A2"].first_attempt_correct is True


def test_parse_action_logs_interleaved_problems_within_one_session(tmp_path: Path) -> None:
    """One assignment juggling two problems must keep their attempt counts apart."""
    body = (
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + _action_row(assignment="A1", ts=1005, problem="P2", action="problem_started")
        + _action_row(assignment="A1", ts=1010, problem="P1", action="wrong_response")
        + _action_row(assignment="A1", ts=1020, problem="P2", action="correct_response")
        + _action_row(assignment="A1", ts=1030, problem="P1", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {
        "P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE),
        "P2": ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE),
    }
    turns = {t.problem_id: t for t in parse_action_logs(action_logs, fraction_problems)}

    assert turns["P1"].attempt_count == 2  # 1 wrong + 1 correct
    assert turns["P1"].correct is True
    assert turns["P2"].attempt_count == 1
    assert turns["P2"].first_attempt_correct is True


# ─── Determinism (PROJECT.md §4.1) ────────────────────────────────────────────


def test_parse_action_logs_is_deterministic(tmp_path: Path) -> None:
    """Same input twice ⇒ exactly the same list of turns, by equality."""
    body = (
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + _action_row(assignment="A1", ts=1010, problem="P1", action="wrong_response")
        + _action_row(assignment="A1", ts=1020, problem="P1", action="correct_response")
        + _action_row(assignment="A2", ts=3000, problem="P2", action="problem_started")
        + _action_row(assignment="A2", ts=3010, problem="P2", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {
        "P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE),
        "P2": ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE),
    }
    first = list(parse_action_logs(action_logs, fraction_problems))
    second = list(parse_action_logs(action_logs, fraction_problems))
    assert first == second


# ─── answer_requested without final correct_response → not correct ────────────


def test_parse_action_logs_answer_requested_without_correct_is_incorrect(
    tmp_path: Path,
) -> None:
    """If the learner asks for the answer and never lands a correct_response,
    correct=False and total_latency_ms is None (no successful completion)."""
    body = (
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + _action_row(assignment="A1", ts=1010, problem="P1", action="wrong_response")
        + _action_row(assignment="A1", ts=1020, problem="P1", action="answer_requested")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    (turn,) = list(parse_action_logs(action_logs, fraction_problems))

    assert turn.correct is False
    assert turn.requested_answer is True
    assert turn.attempt_count == 1
    assert turn.total_latency_ms is None
    assert turn.latency_ms_to_first_response == 10_000


# ─── EOF flush of still-open turns ────────────────────────────────────────────


def test_parse_action_logs_flushes_open_turns_at_eof(tmp_path: Path) -> None:
    """A turn with no terminal action (correct_response / answer_requested) must
    still be emitted when the stream ends — silently dropping it would lose data
    (CLAUDE.md §8.5 fail loudly: data is preserved, not invented)."""
    body = _action_row(
        assignment="A1", ts=1000, problem="P1", action="problem_started"
    ) + _action_row(assignment="A1", ts=1010, problem="P1", action="wrong_response")
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    turns = list(parse_action_logs(action_logs, fraction_problems))

    assert len(turns) == 1
    turn = turns[0]
    assert turn.correct is False
    assert turn.attempt_count == 1
    assert turn.requested_answer is False
    assert turn.total_latency_ms is None
    assert turn.latency_ms_to_first_response == 10_000


# ─── Malformed-row tolerance via the stats sink ───────────────────────────────


def test_parse_action_logs_records_skipped_unparseable_rows(tmp_path: Path) -> None:
    """Rows with non-integer timestamps must be skipped and counted, not crash."""
    body = (
        _action_row(assignment="A1", ts=1000, problem="P1", action="problem_started")
        + "A1,not_a_timestamp,P1,3,1.0,1.0,1.0,wrong_response,,\n"
        + _action_row(assignment="A1", ts=1010, problem="P1", action="correct_response")
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    stats = ParseStats()
    turns = list(parse_action_logs(action_logs, fraction_problems, stats=stats))

    assert len(turns) == 1
    assert turns[0].attempt_count == 1  # only the well-formed correct_response counted
    assert stats.malformed_rows == 1


# ─── Streaming / bounded memory: a row_limit-truncated scan completes ─────────


def test_parse_action_logs_row_limit_truncates_the_stream(tmp_path: Path) -> None:
    """Passing ``row_limit`` halts iteration after N data rows (excluding header),
    which lets the integration smoke run without scanning the full 24M-row file."""
    body = "".join(
        _action_row(assignment=f"A{i}", ts=1000 + i, problem="P1", action="problem_started")
        for i in range(5)
    )
    action_logs = _write_action_logs(tmp_path, body)
    fraction_problems = {"P1": ("5.NF.A.1", KnowledgeComponentId.ADDITION_UNLIKE)}
    stats = ParseStats()
    turns = list(parse_action_logs(action_logs, fraction_problems, row_limit=2, stats=stats))
    # Five problem_started rows on the same problem in different assignments would
    # yield five open-turn flushes at EOF; with row_limit=2, only two are read,
    # so only two open turns get flushed.
    assert len(turns) == 2
    assert stats.rows_read == 2


# ─── Inline string-stream variant of the contract test, to prove StringIO works ─


def test_parse_action_logs_accepts_text_stream() -> None:
    """Beyond Path inputs, the parser accepts any text iterable — useful for
    keeping the unit tests pure (no tmp files needed for the simplest cases)."""
    body = dedent(
        f"""\
        {_ACTION_HEADER.rstrip()}
        A1,1000,P1,3,1.0,1.0,1.0,problem_started,,
        A1,1005,P1,3,1.0,1.0,1.0,correct_response,,
        """
    )
    fraction_problems = {"P1": ("4.NF.A.1", KnowledgeComponentId.EQUIVALENCE)}
    turns = list(parse_action_logs(StringIO(body), fraction_problems))
    assert len(turns) == 1
    assert turns[0].first_attempt_correct is True


# ─── Integration smoke (slow, skipped if data absent) ─────────────────────────

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "edmcup2023"


@pytest.mark.skipif(
    not (_DATA_DIR / "action_logs.csv").exists()
    or not (_DATA_DIR / "problem_details.csv").exists(),
    reason="EDM Cup 2023 dataset not present locally (gitignored).",
)
@pytest.mark.skipif(
    os.environ.get("WHOLLYMATH_RUN_SLOW") != "1",
    reason="slow integration test; set WHOLLYMATH_RUN_SLOW=1 to enable",
)
def test_integration_smoke_parses_real_action_logs() -> None:
    """A truncated real-data scan must produce >0 fraction turns without crashing.

    Gated on the env var so the default test run stays sub-second; set
    ``WHOLLYMATH_RUN_SLOW=1`` to run. The 50k-row prefix is enough to hit fraction
    problems on the real dataset (Common Core 5.NF / 4.NF codes are well-represented).
    """
    fraction_problems = load_fraction_problems(_DATA_DIR / "problem_details.csv")
    assert len(fraction_problems) > 0

    stats = ParseStats()
    turns = list(
        parse_action_logs(
            _DATA_DIR / "action_logs.csv",
            fraction_problems,
            row_limit=50_000,
            stats=stats,
        )
    )
    assert stats.rows_read == 50_000
    assert len(turns) > 0
