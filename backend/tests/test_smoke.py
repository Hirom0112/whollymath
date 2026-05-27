"""Smoke test: proves the toolchain (uv + pytest) is wired and green.

This is intentionally trivial. Real domain/mastery/persona/helpneed tests are
TDD-first and live in the mirroring subpackages of tests/ (CLAUDE.md §2, §6).
"""


def test_backend_package_imports() -> None:
    """The app package and its layer packages import cleanly."""
    import app  # noqa: F401
    import app.domain  # noqa: F401
    import app.llm  # noqa: F401
    import app.mastery  # noqa: F401

    assert True
