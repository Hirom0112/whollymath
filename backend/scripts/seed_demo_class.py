"""Seed the demo class into the configured database (one-off operator script).

WHY: ``app.personas.student_bots.seed_demo_class`` builds the whole demo class — a demo
teacher plus six persona-driven student bots, rostered and driven through the REAL turn loop
— but nothing invoked it, so the demo class never actually existed in a running DB. This is
that missing entrypoint. It is a one-off operator script (CLAUDE.md §2: scripts get no TDD),
deliberately thin: it builds a session factory from ``DATABASE_URL`` and calls the existing,
tested seeder. Idempotent — re-running yields the same teacher/students/turns.

Usage (from backend/):
    DATABASE_URL=postgresql://whollymath:whollymath@localhost:5433/whollymath \
        uv run python -m scripts.seed_demo_class

Then sign in via the teacher "demo" button (POST /teacher/demo-login) — no password.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.engine import (
    create_db_engine,
    create_session_factory,
    database_url_from_env,
)
from app.personas.student_bots import DEMO_BOT_PROFILES, seed_demo_class


def main() -> None:
    url = database_url_from_env()
    engine = create_db_engine(url)
    factory = create_session_factory(engine)
    learner_ids = seed_demo_class(factory, now=datetime.now(UTC))
    print(f"seeded demo class against {url}")
    print(f"demo teacher + {len(learner_ids)} student bots (learner ids: {learner_ids})")
    for profile, lid in zip(DEMO_BOT_PROFILES, learner_ids, strict=True):
        print(
            f"  - {profile.display_name:<22} learner_id={lid}  intended={profile.intended_category}"
        )


if __name__ == "__main__":
    main()
