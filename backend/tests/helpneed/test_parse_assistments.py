"""The ASSISTments-2009 parser stub is INERT and decision-gated (Slice 0.1, V2_TODO WAVE 0).

This pins that the stub produces NO data and fails LOUDLY with the documented block reason — it is
a decision gate (owner commercial-license sign-off required), never a silent no-op that could leak
fake or unlicensed data into the training set (CLAUDE.md §5, §8.5; V2_TODO open-decisions).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.helpneed.parse_assistments import parse_assistments_skill_builder


def test_parser_raises_not_implemented_and_parses_nothing() -> None:
    """Calling the stub raises NotImplementedError — it never returns data."""
    with pytest.raises(NotImplementedError):
        # The generator-or-not contract doesn't matter: the call itself must raise, so even
        # materializing it cannot yield rows. ``list(...)`` would also raise here.
        parse_assistments_skill_builder(Path("does/not/matter.csv"))


def test_block_reason_names_the_license_gate() -> None:
    """The raised message documents WHY it's blocked (the commercial-license decision)."""
    with pytest.raises(NotImplementedError, match="commercial-license"):
        parse_assistments_skill_builder(Path("x.csv"), row_limit=10)
