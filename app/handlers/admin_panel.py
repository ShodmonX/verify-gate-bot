import logging
from datetime import datetime, timezone
from html import escape
from typing import Optional

from aiogram import Bot, Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings, get_admin_ids
from app.db.models import MatchType, ProhibitedWord
from app.services.prohibited import ProhibitedCache, normalize_word
from app.services.runtime_settings import (
    SUPPORTED_KEYS,
    apply_runtime_settings,
    get_current_settings,
    upsert_setting,
)

logger = logging.getLogger(__name__)

router = Router()
ADMIN_STATE: dict[int, dict[str, str]] = {}


def is_admin(user_id: int) -> bool:
    return user_id in get_admin_ids()


def admin_menu_kb() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📜 List words", callback_data="admin:list:p=1")],
        [InlineKeyboardButton(text="➕ Add word", callback_data="admin:add")],
        [InlineKeyboardButton(text="🗑 Remove word", callback_data="admin:remove")],
        [InlineKeyboardButton(text="🔎 Search", callback_data="admin:search")],
        [InlineKeyboardButton(text="📥 Bulk import", callback_data="admin:bulk")],
        [InlineKeyboardButton(text="📤 Export", callback_data="admin:export")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin:settings")],
        [InlineKeyboardButton(text="❌ Close", callback_data="admin:close")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def list_kb(page: int, total_pages: int, items: list[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    rows = []
    for word_id, display, enabled in items:
        status = "✅" if enabled else "🚫"
        rows.append(
            [InlineKeyboardButton(text=f"{status} {display}", callback_data=f"admin:detail:id={word_id}")]
        )
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀ Prev", callback_data=f"admin:list:p={page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Next ▶", callback_data=f"admin:list:p={page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="⬅ Back", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def detail_kb(word_id: int, enabled: bool) -> InlineKeyboardMarkup:
    toggle_text = "🚫 Disable" if enabled else "✅ Enable"
    rows = [
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin:toggle:id={word_id}")],
        [InlineKeyboardButton(text="🗑 Remove", callback_data=f"admin:remove:id={word_id}")],
        [InlineKeyboardButton(text="⬅ Back to list", callback_data="admin:backlist")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_remove_kb(word_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="✅ Ha, o'chirilsin", callback_data=f"admin:remove:confirm:id={word_id}"),
            InlineKeyboardButton(text="❌ Bekor", callback_data=f"admin:detail:id={word_id}"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def normalize_input(text: str) -> Optional[str]:
    norm = normalize_word(text)
    if not norm or len(norm) < 2:
        return None
    return norm


def parse_callback_param(data: str, key: str) -> Optional[str]:
    for part in data.split(":"):
        if part.startswith(f"{key}="):
            return part.split("=", 1)[1]
    return None


def remember_list_page(chat_id: int, page: int) -> None:
    ADMIN_STATE.setdefault(chat_id, {})["last_list_page"] = str(page)


def get_list_page(chat_id: int) -> int:
    return int(ADMIN_STATE.get(chat_id, {}).get("last_list_page", "1"))


@router.message(Command("admin"))
async def admin_entry(message: Message) -> None:
    logger.info("Handler admin_entry chat_id=%s user_id=%s", message.chat.id, message.from_user.id if message.from_user else None)
    if message.chat.type != "private":
        logger.info("admin_entry stop: not private")
        return
    if not settings.ADMIN_PANEL_ENABLED or message.from_user is None or not is_admin(message.from_user.id):
        logger.info("admin_entry stop: access denied")
        return
    await message.answer("Admin panel:", reply_markup=admin_menu_kb())


@router.callback_query(F.data.startswith("admin:"))
async def admin_callbacks(
    callback: CallbackQuery,
    bot: Bot,
    sessionmaker: async_sessionmaker[AsyncSession],
    prohibited_cache: ProhibitedCache,
) -> None:
    logger.info("Handler admin_callbacks data=%s user_id=%s", callback.data, callback.from_user.id if callback.from_user else None)
    if not settings.ADMIN_PANEL_ENABLED:
        await callback.answer("Access denied", show_alert=True)
        logger.info("admin_callbacks stop: panel disabled")
        return
    if callback.from_user is None or not is_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        logger.info("admin_callbacks stop: access denied")
        return

    data = callback.data or ""
    if data.startswith("admin:menu"):
        await callback.message.edit_text("Admin panel:", reply_markup=admin_menu_kb())
        await callback.answer()
        return

    if data.startswith("admin:close"):
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer()
        return

    if data.startswith("admin:list"):
        page_str = parse_callback_param(data, "p") or "1"
        page = max(1, int(page_str))
        per_page = 10
        async with sessionmaker() as session:
            total = await session.scalar(select(func.count()).select_from(ProhibitedWord))
            result = await session.execute(
                select(ProhibitedWord)
                .order_by(ProhibitedWord.created_at.desc(), ProhibitedWord.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            rows = result.scalars().all()
        total_pages = max(1, (total + per_page - 1) // per_page) if total is not None else 1
        lines = [f"Taqiqlangan so'zlar (page {page}/{total_pages}):"]
        items = []
        for row in rows:
            display = escape(row.original or row.word)
            items.append((row.id, display, row.enabled))
        remember_list_page(callback.message.chat.id, page)
        await callback.message.edit_text("\n".join(lines), reply_markup=list_kb(page, total_pages, items))
        await callback.answer()
        return

    if data.startswith("admin:detail"):
        word_id = parse_callback_param(data, "id")
        if not word_id:
            await callback.answer()
            return
        async with sessionmaker() as session:
            row = await session.get(ProhibitedWord, int(word_id))
            if not row:
                await callback.answer("Not found", show_alert=True)
                return
        status = "✅ enabled" if row.enabled else "🚫 disabled"
        display = escape(row.original or row.word)
        text = (
            f"Word: {display}\n"
            f"Normalized: {escape(row.word)}\n"
            f"Status: {status}\n"
            f"Match: {row.match_type}"
        )
        await callback.message.edit_text(text, reply_markup=detail_kb(row.id, row.enabled))
        await callback.answer()
        return

    if data.startswith("admin:backlist"):
        page = get_list_page(callback.message.chat.id)
        per_page = 10
        async with sessionmaker() as session:
            total = await session.scalar(select(func.count()).select_from(ProhibitedWord))
            result = await session.execute(
                select(ProhibitedWord)
                .order_by(ProhibitedWord.created_at.desc(), ProhibitedWord.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            rows = result.scalars().all()
        total_pages = max(1, (total + per_page - 1) // per_page) if total is not None else 1
        lines = [f"Taqiqlangan so'zlar (page {page}/{total_pages}):"]
        items = []
        for row in rows:
            display = escape(row.original or row.word)
            items.append((row.id, display, row.enabled))
        await callback.message.edit_text("\n".join(lines), reply_markup=list_kb(page, total_pages, items))
        await callback.answer()
        return

    if data.startswith("admin:toggle"):
        word_id = parse_callback_param(data, "id")
        if not word_id:
            await callback.answer()
            return
        async with sessionmaker() as session:
            row = await session.get(ProhibitedWord, int(word_id))
            if not row:
                await callback.answer("Not found", show_alert=True)
                return
            row.enabled = not row.enabled
            await session.commit()
        await prohibited_cache.refresh()
        logger.info("Prohibited cache refreshed after toggle id=%s enabled=%s", row.id, row.enabled)
        status = "✅ enabled" if row.enabled else "🚫 disabled"
        display = escape(row.original or row.word)
        text = (
            f"Word: {display}\n"
            f"Normalized: {escape(row.word)}\n"
            f"Status: {status}\n"
            f"Match: {row.match_type}"
        )
        try:
            await callback.message.edit_text(text, reply_markup=detail_kb(row.id, row.enabled))
        except Exception:
            pass
        await callback.answer("Updated")
        return

    if data.startswith("admin:remove:id="):
        word_id = parse_callback_param(data, "id")
        if not word_id:
            await callback.answer()
            return
        async with sessionmaker() as session:
            row = await session.get(ProhibitedWord, int(word_id))
            if not row:
                await callback.answer("Not found", show_alert=True)
                return
        display = escape(row.original or row.word)
        text = (
            f"Ushbu so'zni o'chirishni tasdiqlang:\n\n"
            f"Word: {display}\n"
            f"Normalized: {escape(row.word)}"
        )
        await callback.message.edit_text(text, reply_markup=confirm_remove_kb(row.id))
        await callback.answer()
        return

    if data.startswith("admin:remove:confirm"):
        word_id = parse_callback_param(data, "id")
        if not word_id:
            await callback.answer()
            return
        async with sessionmaker() as session:
            row = await session.get(ProhibitedWord, int(word_id))
            if not row:
                await callback.answer("Not found", show_alert=True)
                return
            await session.delete(row)
            await session.commit()
        await prohibited_cache.refresh()
        await callback.answer("Deleted")

        # return to list
        page = get_list_page(callback.message.chat.id)
        per_page = 10
        async with sessionmaker() as session:
            total = await session.scalar(select(func.count()).select_from(ProhibitedWord))
            result = await session.execute(
                select(ProhibitedWord)
                .order_by(ProhibitedWord.created_at.desc(), ProhibitedWord.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            rows = result.scalars().all()
        total_pages = max(1, (total + per_page - 1) // per_page) if total is not None else 1
        lines = [f"Taqiqlangan so'zlar (page {page}/{total_pages}):"]
        items = []
        for row in rows:
            display = escape(row.original or row.word)
            items.append((row.id, display, row.enabled))
        await callback.message.edit_text("\n".join(lines), reply_markup=list_kb(page, total_pages, items))
        return

    if data.startswith("admin:add"):
        await callback.message.edit_text("Yangi so‘zni yuboring (1 ta so‘z yoki phrase). Bekor qilish: /cancel")
        await callback.answer()
        ADMIN_STATE[callback.message.chat.id] = {"mode": "add"}
        return

    if data.startswith("admin:remove"):
        await callback.message.edit_text("O‘chirish uchun so‘zni yuboring (aniq mos).")
        await callback.answer()
        ADMIN_STATE[callback.message.chat.id] = {"mode": "remove"}
        return

    if data.startswith("admin:search"):
        await callback.message.edit_text("Qidiruv so‘zini yuboring.")
        await callback.answer()
        ADMIN_STATE[callback.message.chat.id] = {"mode": "search"}
        return

    if data.startswith("admin:bulk"):
        await callback.message.edit_text("Bir nechta so‘z/phrase yuboring (har qator bitta). # izohlar e’tiborga olinmaydi.")
        await callback.answer()
        ADMIN_STATE[callback.message.chat.id] = {"mode": "bulk"}
        return

    if data.startswith("admin:export"):
        async with sessionmaker() as session:
            result = await session.execute(
                select(ProhibitedWord).where(ProhibitedWord.enabled.is_(True)).order_by(ProhibitedWord.word)
            )
            rows = result.scalars().all()
        lines = [row.original or row.word for row in rows]
        chunk = []
        current = ""
        for line in lines:
            if len(current) + len(line) + 1 > 3500:
                chunk.append(current)
                current = ""
            current += (line + "\n")
        if current:
            chunk.append(current)
        for part in chunk:
            await callback.message.answer(part.strip())
        await callback.answer()
        return

    if data.startswith("admin:settings"):
        current = get_current_settings()
        lines = ["Settings:"]
        for key in sorted(SUPPORTED_KEYS):
            lines.append(f"- {key} = {current.get(key)}")
        buttons = [
            [InlineKeyboardButton(text=key, callback_data=f"admin:settings:edit:key={key}")]
            for key in sorted(SUPPORTED_KEYS)
        ]
        buttons.append([InlineKeyboardButton(text="⬅ Back", callback_data="admin:menu")])
        await callback.message.edit_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
        return

    if data.startswith("admin:settings:edit"):
        key = parse_callback_param(data, "key")
        if not key or key not in SUPPORTED_KEYS:
            await callback.answer()
            return
        ADMIN_STATE[callback.message.chat.id] = {"mode": "setting", "key": key}
        await callback.message.edit_text(f"Yangi qiymat kiriting: {key}\nBekor qilish: /cancel")
        await callback.answer()
        return


@router.message(lambda message: message.chat.type == "private" and message.chat.id in ADMIN_STATE)
async def admin_text_input(
    message: Message,
    sessionmaker: async_sessionmaker[AsyncSession],
    prohibited_cache: ProhibitedCache,
) -> None:
    logger.info("Handler admin_text_input chat_id=%s user_id=%s", message.chat.id, message.from_user.id if message.from_user else None)
    if not settings.ADMIN_PANEL_ENABLED:
        logger.info("admin_text_input stop: panel disabled")
        return
    if message.from_user is None or not is_admin(message.from_user.id):
        logger.info("admin_text_input stop: access denied")
        return

    state = ADMIN_STATE.get(message.chat.id)
    if not state:
        logger.info("admin_text_input stop: no state")
        return

    if message.text and message.text.strip() == "/cancel":
        ADMIN_STATE.pop(message.chat.id, None)
        await message.answer("Admin panel:", reply_markup=admin_menu_kb())
        return

    mode = state.get("mode")
    if mode == "add":
        raw = (message.text or "").strip()
        norm = normalize_input(raw)
        if not norm:
            await message.answer("Noto‘g‘ri so‘z. /cancel")
            return
        match_type = MatchType.PHRASE if " " in norm else MatchType.TOKEN
        now = datetime.now(tz=timezone.utc)
        async with sessionmaker() as session:
            stmt = pg_insert(ProhibitedWord).values(
                word=norm,
                original=raw,
                enabled=True,
                match_type=match_type,
                created_at=now,
                created_by=message.from_user.id,
            ).on_conflict_do_update(
                index_elements=["word"],
                set_={"enabled": True, "original": raw},
            )
            await session.execute(stmt)
            await session.commit()
        await prohibited_cache.refresh()
        ADMIN_STATE.pop(message.chat.id, None)
        await message.answer("Saved ✅", reply_markup=admin_menu_kb())
        return

    if mode == "setting":
        key = state.get("key")
        if not key:
            ADMIN_STATE.pop(message.chat.id, None)
            await message.answer("Admin panel:", reply_markup=admin_menu_kb())
            return
        raw = (message.text or "").strip()
        if not raw:
            await message.answer("Noto‘g‘ri qiymat. /cancel")
            return
        try:
            async with sessionmaker() as session:
                await upsert_setting(session, key, raw, message.from_user.id)
                await session.commit()
                overrides = {key: raw}
                apply_runtime_settings(overrides)
            ADMIN_STATE.pop(message.chat.id, None)
            note = ""
            await message.answer(f"Saved: {key} = {raw}{note}", reply_markup=admin_menu_kb())
        except Exception:
            logger.exception("Failed to save setting %s", key)
            await message.answer("Xatolik. /cancel")
        return

    if mode == "remove":
        raw = (message.text or "").strip()
        norm = normalize_input(raw)
        if not norm:
            await message.answer("Noto‘g‘ri so‘z. /cancel")
            return
        async with sessionmaker() as session:
            result = await session.execute(select(ProhibitedWord).where(ProhibitedWord.word == norm))
            row = result.scalar_one_or_none()
            if not row:
                await message.answer("Topilmadi")
            else:
                row.enabled = False
                await session.commit()
                await prohibited_cache.refresh()
                await message.answer("Disabled ✅")
        ADMIN_STATE.pop(message.chat.id, None)
        await message.answer("Admin panel:", reply_markup=admin_menu_kb())
        return

    if mode == "search":
        query = (message.text or "").strip()
        if not query:
            await message.answer("Noto‘g‘ri so‘z. /cancel")
            return
        query_norm = normalize_word(query)
        async with sessionmaker() as session:
            result = await session.execute(
                select(ProhibitedWord).where(ProhibitedWord.word.ilike(f"%{query_norm}%"))
            )
            rows = result.scalars().all()
        if not rows:
            await message.answer("Topilmadi")
        else:
            lines = ["Search results:"]
            for row in rows[:50]:
                status = "✅" if row.enabled else "🚫"
                display = escape(row.original or row.word)
                lines.append(f"- {display} {status} (id:{row.id})")
            await message.answer("\n".join(lines))
        ADMIN_STATE.pop(message.chat.id, None)
        await message.answer("Admin panel:", reply_markup=admin_menu_kb())
        return

    if mode == "bulk":
        lines = (message.text or "").splitlines()
        added = 0
        reenabled = 0
        skipped = 0
        now = datetime.now(tz=timezone.utc)
        rows = []
        norms = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            norm = normalize_input(line)
            if not norm:
                skipped += 1
                continue
            match_type = MatchType.PHRASE if " " in norm else MatchType.TOKEN
            norms.append(norm)
            rows.append(
                {
                    "word": norm,
                    "original": line,
                    "enabled": True,
                    "match_type": match_type,
                    "created_at": now,
                    "created_by": message.from_user.id,
                }
            )
        async with sessionmaker() as session:
            if rows:
                existing = {}
                result = await session.execute(
                    select(ProhibitedWord.word, ProhibitedWord.enabled).where(ProhibitedWord.word.in_(norms))
                )
                for word, enabled in result.all():
                    existing[word] = enabled
                stmt = pg_insert(ProhibitedWord).values(rows)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["word"],
                    set_={"enabled": True, "original": "excluded.original"},
                )
                await session.execute(stmt)
                await session.commit()
                for norm in norms:
                    if norm not in existing:
                        added += 1
                    elif existing.get(norm) is False:
                        reenabled += 1
        await prohibited_cache.refresh()
        ADMIN_STATE.pop(message.chat.id, None)
        await message.answer(
            f"Imported: {added}, re-enabled: {reenabled}, skipped: {skipped}",
            reply_markup=admin_menu_kb(),
        )
        return
