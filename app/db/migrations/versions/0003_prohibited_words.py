"""prohibited_words

Revision ID: 0003_prohibited_words
Revises: 0002_user_profiles
Create Date: 2026-01-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_prohibited_words"
down_revision: Union[str, None] = "0002_user_profiles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    match_type_enum = postgresql.ENUM("TOKEN", "PHRASE", name="match_type")
    match_type_enum.create(op.get_bind(), checkfirst=True)
    match_type_enum.create_type = False

    op.create_table(
        "prohibited_words",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("word", sa.String(length=256), nullable=False),
        sa.Column("original", sa.String(length=256), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("match_type", match_type_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.UniqueConstraint("word", name="uq_prohibited_word"),
    )


def downgrade() -> None:
    op.drop_table("prohibited_words")
    match_type_enum = postgresql.ENUM("TOKEN", "PHRASE", name="match_type")
    match_type_enum.drop(op.get_bind(), checkfirst=True)
