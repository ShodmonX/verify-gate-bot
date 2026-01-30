from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str
    GROUP_ID: int
    SECRET_KEY: str

    REMIND_AFTER_MIN: int = 10
    EXPIRE_AFTER_MIN: int = 60
    MAX_REMINDERS: int = 2

    DATABASE_URL: str

    ADMIN_ID: int | None = None
    PROHIBITED_WORDS_PATH: str
    MUTE_MINUTES: int = 10
    TIMEZONE: str = "Asia/Tashkent"
    CASE_INSENSITIVE: bool = True

    ADMIN_PANEL_ENABLED: bool = True
    ADMIN_IDS: str | None = None

    OPENROUTER_API_KEY: str | None = None
    OPENROUTER_MODEL: str = "openai/gpt-4o-mini"
    OPENROUTER_TIMEOUT_SEC: int = 8
    AI_MODERATION_ENABLED: bool = True
    AI_MODERATION_SAMPLE_RATE: float = 1.0
    AI_MODERATION_MIN_CHARS: int = 12
    AI_MODERATION_COOLDOWN_SEC: int = 30
    AI_PROHIBITED_LABELS: str = "gambling,fraud"
    AI_CONFIDENCE_THRESHOLD: float = 0.7

    LOG_LEVEL: str = "INFO"


def get_admin_ids() -> set[int]:
    ids: set[int] = set()
    if settings.ADMIN_ID:
        ids.add(int(settings.ADMIN_ID))
    if settings.ADMIN_IDS:
        for item in settings.ADMIN_IDS.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                ids.add(int(item))
            except ValueError:
                continue
    return ids


def get_primary_admin_id() -> int | None:
    ids = list(get_admin_ids())
    return ids[0] if ids else None


settings = Settings()
