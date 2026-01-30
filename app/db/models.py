import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, DateTime, Enum, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SessionState(str, enum.Enum):
    JOINED_LOCKED = "JOINED_LOCKED"
    WAITING_DM_CONFIRM = "WAITING_DM_CONFIRM"
    CONFIRMED_UNLOCKED = "CONFIRMED_UNLOCKED"


class ApprovedMember(Base):
    __tablename__ = "approved_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_approved_group_user"),)


class VerificationSession(Base):
    __tablename__ = "verification_sessions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    group_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    state: Mapped[SessionState] = mapped_column(Enum(SessionState, name="session_state"))
    magic_word: Mapped[str] = mapped_column(String(64))
    welcome_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )
    last_seen_in_group_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_session_group_user"),
        Index("ix_session_state", "state"),
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_ai_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_moderation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )


class MatchType(str, enum.Enum):
    TOKEN = "TOKEN"
    PHRASE = "PHRASE"


class ProhibitedWord(Base):
    __tablename__ = "prohibited_words"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    word: Mapped[str] = mapped_column(String(256), nullable=False)
    original: Mapped[str | None] = mapped_column(String(256), nullable=True)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    match_type: Mapped[MatchType] = mapped_column(Enum(MatchType, name="match_type"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
    created_by: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (UniqueConstraint("word", name="uq_prohibited_word"),)


class ModerationAction(str, enum.Enum):
    NONE = "NONE"
    MUTED = "MUTED"


class ModerationReason(str, enum.Enum):
    KEYWORD = "KEYWORD"
    AI = "AI"


class ModerationEvent(Base):
    __tablename__ = "moderation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(BigInteger)
    user_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    action: Mapped[ModerationAction] = mapped_column(
        Enum(ModerationAction, name="moderation_action"), default=ModerationAction.NONE
    )
    reason_type: Mapped[ModerationReason] = mapped_column(
        Enum(ModerationReason, name="moderation_reason")
    )
    matched_word: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ai_label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc)
    )
    updated_by: Mapped[int] = mapped_column(BigInteger)
