"""widen turn.surface_state and turn.state_transition

Revision ID: c4f1a9d27b30
Revises: b2d4f6a8c1e3
Create Date: 2026-06-05

Bug found 2026-06-05 while seeding the demo class against Postgres: turn.surface_state was
VARCHAR(16), but EVERY SurfaceState value is longer ("S1_symbolic_focus"=17 …
"S3_fraction_bars_primary"=24), so every turn INSERT raised
StringDataRightTruncation and the whole session rolled back — 0 turns / 0 mastery rows
persisted. It was invisible because tests and the local default store use SQLite, which
ignores VARCHAR length limits; only Postgres (the prod RDS backend) enforces them.

Widen surface_state 16 -> 32 (max real value 24, with headroom) and state_transition
64 -> 255 (free-text learner sentence, currently 62/64 = zero headroom). Pure column-type
widening: no data loss, idempotent in effect. batch_alter_table keeps it SQLite- and
Postgres-safe (ALTER on Postgres, table-rebuild on SQLite).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f1a9d27b30"
down_revision: str | Sequence[str] | None = "b2d4f6a8c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Widen the two truncating turn columns."""
    with op.batch_alter_table("turn") as batch_op:
        batch_op.alter_column(
            "surface_state",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.alter_column(
            "state_transition",
            existing_type=sa.String(length=64),
            type_=sa.String(length=255),
            existing_nullable=True,
        )


def downgrade() -> None:
    """Revert to the original (truncating) widths."""
    with op.batch_alter_table("turn") as batch_op:
        batch_op.alter_column(
            "state_transition",
            existing_type=sa.String(length=255),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "surface_state",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
        )
