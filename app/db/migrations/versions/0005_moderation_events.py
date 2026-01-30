"""moderation events and profile ai fields

Revision ID: 0005_moderation_events
Revises: 0004_seed_prohibited_words
Create Date: 2026-01-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_moderation_events"
down_revision: Union[str, None] = "0004_seed_prohibited_words"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_profiles", sa.Column("last_ai_check_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_profiles", sa.Column("last_moderation_at", sa.DateTime(timezone=True), nullable=True))

    action_enum = postgresql.ENUM("NONE", "MUTED", name="moderation_action")
    reason_enum = postgresql.ENUM("KEYWORD", "AI", name="moderation_reason")
    action_enum.create(op.get_bind(), checkfirst=True)
    reason_enum.create(op.get_bind(), checkfirst=True)
    action_enum.create_type = False
    reason_enum.create_type = False

    op.create_table(
        "moderation_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("group_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=False),
        sa.Column("action", action_enum, nullable=False),
        sa.Column("reason_type", reason_enum, nullable=False),
        sa.Column("matched_word", sa.String(length=256), nullable=True),
        sa.Column("ai_label", sa.String(length=32), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("ai_summary", sa.String(length=256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("moderation_events")
    reason_enum = postgresql.ENUM("KEYWORD", "AI", name="moderation_reason")
    action_enum = postgresql.ENUM("NONE", "MUTED", name="moderation_action")
    reason_enum.drop(op.get_bind(), checkfirst=True)
    action_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_column("user_profiles", "last_ai_check_at")
    op.drop_column("user_profiles", "last_moderation_at")
