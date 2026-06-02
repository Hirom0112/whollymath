"""Contract tests for GET /units and GET /unit/{slug} — the unit/lesson shell (DAT.8/DAT.9/DAT.10).

The unit-product endpoints serve the curriculum's unit/lesson shell with the learner's progress
overlaid, for BOTH kinds of learner (signed-in from persisted mastery; anonymous demo from the
in-memory session) and a brand-new visitor (the fresh default shell, NOT a 401).

These are HTTP-level contract tests through the real ASGI stack (CLAUDE.md §9), using the tiny
in-process ASGI client (no httpx dependency) the rest of the api/ contract tests use. They assert
the WIRE SHAPE (``extra="forbid"`` honored, the documented fields present) and the
anonymous-vs-404 behavior; they do not re-test the unit-progress overlay's math (that is covered
by ``tests/mastery/test_unit_progress.py``).
"""

from __future__ import annotations

from app.api.app import create_app
from app.domain.curriculum import all_units

from tests.api.asgi_client import get

# The exact field set each wire view must expose — asserting equality (not subset) is what proves
# ``model_config = ConfigDict(extra="forbid")`` actually keeps stray keys off the wire.
_UNIT_KEYS = {
    "unit_slug",
    "title",
    "description",
    "order",
    "ccss_cluster",
    "teks_cluster",
    "status",
    "percent_complete",
    "lesson_count",
    "assigned",
}
_LESSON_KEYS = {
    "lesson_slug",
    "title",
    "description",
    "kc_id",
    "ccss_code",
    "teks_code",
    "status",
    "probability",
    "playable",
    "concept_only",
}


def test_anonymous_units_returns_full_catalog_no_assignment() -> None:
    """A brand-new visitor (no token/session) gets every unit, statuses present, no assignment."""
    app = create_app()
    status_code, body = get(app, "/units")
    assert status_code == 200, body
    assert set(body) == {"units", "assigned_unit_slug"}
    # Anonymous callers have no teacher assignment (DAT.10).
    assert body["assigned_unit_slug"] is None
    # Every catalog unit is present, in catalog (teaching) order.
    catalog = all_units()
    assert [u["unit_slug"] for u in body["units"]] == [u.slug for u in catalog]
    # Each unit carries a status and is not assigned for an anonymous caller.
    for unit in body["units"]:
        assert unit["status"]
        assert unit["assigned"] is False


def test_units_unit_view_shape_is_forbid_extra() -> None:
    """A unit on the wire carries exactly the documented fields (extra='forbid' honored)."""
    app = create_app()
    status_code, body = get(app, "/units")
    assert status_code == 200, body
    assert body["units"], "expected at least one unit in the catalog"
    assert set(body["units"][0]) == _UNIT_KEYS


def test_units_unknown_session_is_anonymous_not_401() -> None:
    """An unknown session_id is NOT an error — it yields the fresh default unit list, no 401."""
    app = create_app()
    status_code, body = get(app, "/units?session_id=never-started")
    assert status_code == 200, body
    assert body["assigned_unit_slug"] is None
    assert len(body["units"]) == len(all_units())


def test_unit_detail_hit_returns_lessons() -> None:
    """GET /unit/{slug} for a real unit returns its lessons, count matching, correct shape."""
    app = create_app()
    slug = all_units()[0].slug
    status_code, body = get(app, f"/unit/{slug}")
    assert status_code == 200, body
    assert body["unit_slug"] == slug
    # The detail view is the unit-card fields plus lessons.
    assert set(body) == _UNIT_KEYS | {"lessons"}
    assert isinstance(body["lessons"], list)
    assert len(body["lessons"]) == body["lesson_count"] >= 1
    assert set(body["lessons"][0]) == _LESSON_KEYS


def test_unit_detail_unknown_slug_is_404() -> None:
    """An unknown unit slug yields a 404 (not a 200 with an empty shell, not a 500)."""
    app = create_app()
    status_code, _ = get(app, "/unit/no-such-unit")
    assert status_code == 404


def test_unit_detail_lesson_view_exposes_concept_only_flag() -> None:
    """``concept_only`` rides the wire and is True for exactly the four U8 concept lessons.

    DEC.FINLIT: u8_l1/u8_l2/u8_l4/u8_l5 are pure-concept TEKS items we deliberately stubbed
    (no SymPy/tutor mechanism), so the surface can render an honest "concept lesson" state.
    The two SymPy-graded U8 lessons (u8_l3 check register, u8_l6 lifetime income) are NOT
    concept-only. Asserting it on the wire (not just the overlay) proves the flag survives the
    LessonView projection the frontend reads.
    """
    app = create_app()
    status_code, body = get(app, "/unit/u8")
    assert status_code == 200, body
    by_slug = {lesson["lesson_slug"]: lesson for lesson in body["lessons"]}
    concept_slugs = {"u8_l1", "u8_l2", "u8_l4", "u8_l5"}
    for slug, lesson in by_slug.items():
        assert lesson["concept_only"] is (slug in concept_slugs), slug
    # The two arithmetic U8 lessons stay non-concept (they have a real tutor mechanism).
    assert by_slug["u8_l3"]["concept_only"] is False
    assert by_slug["u8_l6"]["concept_only"] is False
