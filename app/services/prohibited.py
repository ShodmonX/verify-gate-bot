import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.db.models import MatchType, ProhibitedWord

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+", re.UNICODE)
APOSTROPHES = ["'", "’", "‘", "ʻ", "ʼ", "`", "´", "ˈ"]
PLUS_PATTERN = re.compile(r"(\\d+)\\+")


@dataclass
class ProhibitedEntry:
    word: str
    original: str
    match_type: MatchType


class ProhibitedCache:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker
        self.tokens: dict[str, ProhibitedEntry] = {}
        self.phrases: list[ProhibitedEntry] = []

    async def refresh(self) -> None:
        async with self.sessionmaker() as session:
            result = await session.execute(
                select(ProhibitedWord).where(ProhibitedWord.enabled.is_(True))
            )
            rows = result.scalars().all()

        tokens: dict[str, ProhibitedEntry] = {}
        phrases: list[ProhibitedEntry] = []
        for row in rows:
            display = row.original or row.word
            entry = ProhibitedEntry(word=row.word, original=display, match_type=row.match_type)
            if row.match_type == MatchType.PHRASE:
                entry.word = normalize_text(row.word)
                phrases.append(entry)
            else:
                tokens[normalize_word(row.word)] = entry

        self.tokens = tokens
        self.phrases = phrases
        logger.info("Prohibited cache refreshed. tokens=%s phrases=%s", len(tokens), len(phrases))

    def match(self, text: str) -> ProhibitedEntry | None:
        if not text:
            return None
        cleaned = normalize_text(text)
        tokens = set(tokenize(cleaned))

        for token in tokens:
            entry = self.tokens.get(token)
            if entry:
                return entry

        for entry in self.phrases:
            if entry.word and entry.word in cleaned:
                return entry

        return None


def normalize_word(word: str) -> str:
    word = word.strip()
    if settings.CASE_INSENSITIVE:
        word = word.lower()
    word = PLUS_PATTERN.sub(r"\\1plus", word)
    for ch in APOSTROPHES:
        word = word.replace(ch, "")
    word = word.replace("+", "")
    tokens = TOKEN_RE.findall(word)
    return "".join(tokens)


def normalize_text(text: str) -> str:
    text = text.strip()
    if settings.CASE_INSENSITIVE:
        text = text.lower()
    text = PLUS_PATTERN.sub(r"\\1plus", text)
    for ch in APOSTROPHES:
        text = text.replace(ch, "")
    text = text.replace("+", "")
    tokens = TOKEN_RE.findall(text)
    return " ".join(tokens)


def tokenize(text: str) -> Iterable[str]:
    return TOKEN_RE.findall(text)


def parse_words_from_file(path: str) -> list[str]:
    words: list[str] = []
    file_path = Path(path)
    if not file_path.exists():
        return words

    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        items = data.get("words", [])
        if not isinstance(items, list):
            raise ValueError("Invalid JSON format: 'words' must be a list")
        words = [str(item).strip() for item in items if str(item).strip()]
    else:
        lines = file_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            words.append(line)
    return words


async def seed_from_file_if_empty(sessionmaker: async_sessionmaker[AsyncSession]) -> None:
    async with sessionmaker() as session:
        result = await session.execute(select(ProhibitedWord.id).limit(1))
        if result.scalar_one_or_none() is not None:
            return
        words = parse_words_from_file(settings.PROHIBITED_WORDS_PATH)
        if not words:
            return
        now = datetime.now(tz=timezone.utc)
        rows = []
        for raw in words:
            norm = normalize_word(raw)
            if not norm or len(norm) < 3:
                continue
            match_type = MatchType.PHRASE if " " in norm else MatchType.TOKEN
            rows.append(
                {
                    "word": norm,
                    "original": raw,
                    "enabled": True,
                    "match_type": match_type,
                    "created_at": now,
                    "created_by": settings.ADMIN_ID or 0,
                }
            )
        if rows:
            stmt = pg_insert(ProhibitedWord).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["word"])
            await session.execute(stmt)
            await session.commit()
            logger.info("Seeded prohibited words from file: %s", len(rows))
