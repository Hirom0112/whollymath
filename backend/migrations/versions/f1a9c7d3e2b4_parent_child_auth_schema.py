"""parent/child auth schema

Revision ID: f1a9c7d3e2b4
Revises: e7c2a9f4b108
Create Date: 2026-06-03

Adds the parent/child verifiable-parental-consent account schema (Slice
auth/parent-child, owner decision 2026-06-03 — reverses the "auth is post-launch"
line in TECH_STACK §9). On the existing ``learner`` table: the parent link, the
parent password hash + email-verified flag, and the child credential columns
(display name, grade, per-household username, PIN hash + lockout, opaque public
id). Plus the new ``consent_record`` table that stamps the auditable act of
consent (COPPA; RESEARCH.md, FTC COPPA Rule).

SQLite (the test/bootstrap DB) cannot ``ALTER TABLE ... ADD CONSTRAINT``, so the
new NOT NULL columns carry a ``server_default`` for the backfill, the unique
per-household-username constraint is added as a UNIQUE INDEX (which SQLite accepts
via CREATE INDEX), and the self-referential parent FK — which gives prod Postgres
real ON DELETE CASCADE — is created only on non-SQLite backends. ``create_all``
(the test app path) builds the equivalent objects directly from the model.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a9c7d3e2b4'
down_revision: Union[str, Sequence[str], None] = 'e7c2a9f4b108'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # New parent/child identity + credential columns on the existing learner table.
    # The two NOT NULL columns (email_verified, failed_pin_attempts) carry a
    # server_default so the ALTER backfills the existing rows; everything else is
    # nullable (only parent/child rows populate them).
    op.add_column("learner", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("learner", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "learner",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("learner", sa.Column("display_name", sa.String(length=64), nullable=True))
    op.add_column("learner", sa.Column("grade_level", sa.Integer(), nullable=True))
    op.add_column("learner", sa.Column("child_username", sa.String(length=32), nullable=True))
    op.add_column("learner", sa.Column("pin_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "learner",
        sa.Column("failed_pin_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("learner", sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("learner", sa.Column("public_id", sa.String(length=36), nullable=True))

    op.create_index(op.f("ix_learner_parent_id"), "learner", ["parent_id"], unique=False)
    op.create_index(op.f("ix_learner_public_id"), "learner", ["public_id"], unique=True)
    # Per-household uniqueness of a child's login username (Learner.__table_args__):
    # a UNIQUE INDEX rather than a table constraint so SQLite can add it to the
    # already-existing learner table.
    op.create_index(
        "uq_learner_parent_username", "learner", ["parent_id", "child_username"], unique=True
    )

    # The self-referential parent FK gives prod Postgres real ON DELETE CASCADE.
    # SQLite cannot add an FK to an existing table, so skip it there — the ORM
    # cascade + the create_all-built FK cover the test path.
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_learner_parent_id_learner",
            "learner",
            "learner",
            ["parent_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_table(
        "consent_record",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=False),
        sa.Column("child_id", sa.Integer(), nullable=True),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column(
            "method", sa.String(length=32), nullable=False, server_default="parent_account"
        ),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["learner.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["child_id"], ["learner.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_consent_record_parent_id"), "consent_record", ["parent_id"], unique=False
    )
    op.create_index(
        op.f("ix_consent_record_child_id"), "consent_record", ["child_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_consent_record_child_id"), table_name="consent_record")
    op.drop_index(op.f("ix_consent_record_parent_id"), table_name="consent_record")
    op.drop_table("consent_record")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_learner_parent_id_learner", "learner", type_="foreignkey")

    op.drop_index("uq_learner_parent_username", table_name="learner")
    op.drop_index(op.f("ix_learner_public_id"), table_name="learner")
    op.drop_index(op.f("ix_learner_parent_id"), table_name="learner")

    op.drop_column("learner", "public_id")
    op.drop_column("learner", "pin_locked_until")
    op.drop_column("learner", "failed_pin_attempts")
    op.drop_column("learner", "pin_hash")
    op.drop_column("learner", "child_username")
    op.drop_column("learner", "grade_level")
    op.drop_column("learner", "display_name")
    op.drop_column("learner", "email_verified")
    op.drop_column("learner", "password_hash")
    op.drop_column("learner", "parent_id")
