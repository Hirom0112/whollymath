"""child username globally unique

Revision ID: b2d4f6a8c1e3
Revises: a3c8e1f5d720
Create Date: 2026-06-04

Owner decision (2026-06-04): a child logs in with username + PIN ALONE — no parent
email — so the child username must be GLOBALLY unique (it identifies the child by
itself). This drops the per-household unique index (uq_learner_parent_username) and
replaces it with a global unique index on child_username. Safe on a fresh deploy (no
production child rows exist yet); the new index only fails if two existing children
already share a username, which cannot have happened. SQLite- and Postgres-safe
(drop-index + create-index, no ALTER ADD CONSTRAINT).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b2d4f6a8c1e3'
down_revision: Union[str, Sequence[str], None] = 'a3c8e1f5d720'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("uq_learner_parent_username", table_name="learner")
    op.create_index("uq_learner_child_username", "learner", ["child_username"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("uq_learner_child_username", table_name="learner")
    op.create_index(
        "uq_learner_parent_username", "learner", ["parent_id", "child_username"], unique=True
    )
