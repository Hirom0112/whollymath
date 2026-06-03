"""auth session (revocable server-side sessions)

Revision ID: a3c8e1f5d720
Revises: f1a9c7d3e2b4
Create Date: 2026-06-03

Adds the ``auth_session`` table (Slice auth/parent-child, S2): the revocable
server-side half of a parent/child session, keyed to the JWT ``jti`` so a session
can be killed (logout / parent "sign out everywhere") even though the JWT itself is
stateless. A plain ``create_table`` — fine on both SQLite (test/bootstrap) and
Postgres (prod), since FKs declared in CREATE TABLE are accepted by SQLite.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c8e1f5d720'
down_revision: Union[str, Sequence[str], None] = 'f1a9c7d3e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "auth_session",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("learner_id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["learner_id"], ["learner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_auth_session_learner_id"), "auth_session", ["learner_id"], unique=False
    )
    op.create_index(op.f("ix_auth_session_jti"), "auth_session", ["jti"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_auth_session_jti"), table_name="auth_session")
    op.drop_index(op.f("ix_auth_session_learner_id"), table_name="auth_session")
    op.drop_table("auth_session")
