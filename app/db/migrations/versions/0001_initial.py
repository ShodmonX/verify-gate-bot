"""initial

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "approved_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("group_id", "user_id", name="uq_approved_group_user"),
    )
    op.create_index("ix_approved_members_group_id", "approved_members", ["group_id"])
    op.create_index("ix_approved_members_user_id", "approved_members", ["user_id"])

    session_state_enum = postgresql.ENUM(
        "JOINED_LOCKED",
        "WAITING_DM_CONFIRM",
        "CONFIRMED_UNLOCKED",
        name="session_state",
    )
    session_state_enum.create(op.get_bind(), checkfirst=True)
    session_state_enum.create_type = False

    op.create_table(
        "verification_sessions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("state", session_state_enum, nullable=False),
        sa.Column("magic_word", sa.String(length=64), nullable=False),
        sa.Column("welcome_message_id", sa.BigInteger(), nullable=True),
        sa.Column("reminder_count", sa.Integer(), nullable=False),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_in_group_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("group_id", "user_id", name="uq_session_group_user"),
    )
    op.create_index("ix_verification_sessions_group_id", "verification_sessions", ["group_id"])
    op.create_index("ix_verification_sessions_user_id", "verification_sessions", ["user_id"])
    op.create_index("ix_session_state", "verification_sessions", ["state"])


def downgrade() -> None:
    op.drop_index("ix_session_state", table_name="verification_sessions")
    op.drop_index("ix_verification_sessions_user_id", table_name="verification_sessions")
    op.drop_index("ix_verification_sessions_group_id", table_name="verification_sessions")
    op.drop_table("verification_sessions")

    op.drop_index("ix_approved_members_user_id", table_name="approved_members")
    op.drop_index("ix_approved_members_group_id", table_name="approved_members")
    op.drop_table("approved_members")

    session_state_enum = postgresql.ENUM(
        "JOINED_LOCKED",
        "WAITING_DM_CONFIRM",
        "CONFIRMED_UNLOCKED",
        name="session_state",
    )
    session_state_enum.drop(op.get_bind(), checkfirst=True)
