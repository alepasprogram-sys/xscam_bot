"""Движок ответов бота — загружает bot_data.json и отправляет сохранённые ответы."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from shared.garants_list import build_all_garants_pages
from shared.assets import get_photo, photo_for_command
from shared.bot_branding import apply_bot_branding

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

ENTITY_TO_HTML = {
    "MessageEntityBold": ("<b>", "</b>"),
    "MessageEntityItalic": ("<i>", "</i>"),
    "MessageEntityUnderline": ("<u>", "</u>"),
    "MessageEntityStrike": ("<s>", "</s>"),
    "MessageEntityCode": ("<code>", "</code>"),
    "MessageEntityPre": ("<pre>", "</pre>"),
    "MessageEntitySpoiler": ("<tg-spoiler>", "</tg-spoiler>"),
    "MessageEntityTextUrl": ('<a href="{url}">', "</a>"),
    "MessageEntityCustomEmoji": ('<tg-emoji emoji-id="{document_id}">', "</tg-emoji>"),
}

TEXT_TO_COMMAND = {
    "👁 мой профиль": "me",
    "🛡️ список гарантов": "garants",
    "🔄 провести сделку через гаранта 🔄": "start_deal",
    "📁 команды": "help",
    "ℹ️ о проекте": "info",
}

CALLBACK_ALIASES = {
    "t": ("command", "start"),
}

# Ответы, ошибочно привязанные при клонировании (не отправлять)
SKIP_RESPONSE_IDS = {84678}

# Команды, где нужна цепочка из нескольких сообщений
MULTI_RESPONSE_COMMANDS = {"start"}


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attr(text: str) -> str:
    return _escape_html(text).replace('"', "&quot;")


def _utf16_pos_to_py_index(text: str, utf16_pos: int) -> int:
    utf16 = 0
    for i, ch in enumerate(text):
        if utf16 >= utf16_pos:
            return i
        utf16 += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def _utf16_slice(text: str, offset: int, length: int) -> tuple[int, int] | None:
    if length <= 0 or offset < 0:
        return None
    start = _utf16_pos_to_py_index(text, offset)
    end = _utf16_pos_to_py_index(text, offset + length)
    if start < 0 or end < start or end > len(text):
        return None
    return start, end


def entities_to_html(text: str, entities: list[dict[str, Any]]) -> str:
    if not text:
        return ""
    if not entities:
        return _escape_html(text)

    result = text
    for ent in sorted(entities, key=lambda e: e.get("offset", 0), reverse=True):
        offset = ent.get("offset", 0)
        length = ent.get("length", 0)
        ent_type = ent.get("type", "")
        bounds = _utf16_slice(result, offset, length)
        if not bounds:
            continue
        start, end = bounds
        mapping = ENTITY_TO_HTML.get(ent_type)
        if not mapping:
            continue
        open_tag, close_tag = mapping
        if "{url}" in open_tag:
            url = ent.get("url") or ""
            if not url:
                continue
            open_tag = open_tag.format(url=_escape_attr(url))
        if "{document_id}" in open_tag:
            doc_id = ent.get("document_id") or ent.get("custom_emoji_id", "")
            if not doc_id:
                continue
            open_tag = open_tag.format(document_id=doc_id)
        segment = result[start:end]
        result = result[:start] + open_tag + segment + close_tag + result[end:]
    return result


def keyboard_from_dict(data: dict[str, Any] | None):
    if not data:
        return None
    kb_type = data.get("type")
    if kb_type == "inline":
        rows = []
        for row in data.get("rows", []):
            buttons = []
            for btn in row:
                text = btn.get("text", "")
                if btn.get("url"):
                    buttons.append(InlineKeyboardButton(text=text, url=btn["url"]))
                else:
                    cb = btn.get("callback_data_decoded") or btn.get("callback_data") or text
                    buttons.append(InlineKeyboardButton(text=text, callback_data=str(cb)))
            rows.append(buttons)
        return InlineKeyboardMarkup(inline_keyboard=rows)
    if kb_type == "reply":
        rows = [
            [KeyboardButton(text=btn.get("text", "")) for btn in row]
            for row in data.get("rows", [])
        ]
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=data.get("resize", True),
            one_time_keyboard=data.get("one_time", False),
            is_persistent=data.get("is_persistent", False),
        )
    return None


class BotRuntime:
    def __init__(self, data_path: Path | None = None) -> None:
        path = data_path or (BASE_DIR / "bot_data.json")
        with path.open(encoding="utf-8") as f:
            self.data = json.load(f)
        self.by_trigger: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.garants_pages: dict[int, dict[str, Any]] = {}
        self._index_responses()
        self._index_garants_pages()

    def _trigger_key(self, t_type: str, payload: str) -> tuple[str, str] | None:
        if t_type == "command":
            return ("command", payload.lstrip("/").lower())
        if t_type == "text":
            return ("text", payload.lower())
        if t_type == "callback":
            return ("callback", payload)
        return None

    def _index_responses(self) -> None:
        seen_ids: set[int] = set()
        for resp in self.data.get("responses", []):
            trigger = resp.get("trigger", {})
            t_type = trigger.get("type", "")
            payload = trigger.get("payload", "")
            if t_type in ("history", "unknown", ""):
                continue
            key = self._trigger_key(t_type, payload)
            if not key:
                continue
            if t_type == "text" and payload.lower() in TEXT_TO_COMMAND:
                continue
            msg_id = resp.get("id")
            if msg_id in seen_ids or msg_id in SKIP_RESPONSE_IDS:
                continue
            seen_ids.add(msg_id)
            self.by_trigger.setdefault(key, []).append(resp)

        for key, items in self.by_trigger.items():
            deduped: list[dict[str, Any]] = []
            seen_text: set[str] = set()
            for item in items:
                sig = item.get("text", "")[:200]
                if sig in seen_text:
                    continue
                seen_text.add(sig)
                deduped.append(item)
            self.by_trigger[key] = deduped

    @staticmethod
    def _pick_best_response(responses: list[dict[str, Any]]) -> dict[str, Any]:
        with_asset = [r for r in responses if r.get("asset_path")]
        pool = with_asset or responses
        return max(pool, key=lambda r: r.get("id", 0))

    def _finalize_responses(
        self,
        t_type: str,
        payload: str,
        responses: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not responses:
            return []
        if t_type == "command" and payload.lstrip("/").lower() in MULTI_RESPONSE_COMMANDS:
            return responses
        if len(responses) == 1:
            return responses
        return [self._pick_best_response(responses)]

    @staticmethod
    def _detect_garants_page_num(resp: dict[str, Any]) -> int | None:
        kb = resp.get("keyboard") or {}
        if kb.get("type") != "inline":
            return None
        for row in kb.get("rows", []):
            for btn in row:
                label = btn.get("text", "")
                if not re.fullmatch(r"\d+/\d+", label):
                    continue
                cb = btn.get("callback_data_decoded") or btn.get("callback_data") or ""
                if cb == "noop":
                    try:
                        return int(label.split("/")[0])
                    except ValueError:
                        return None
        return None

    def _index_garants_pages(self) -> None:
        self._refresh_garants_pages()

    def _refresh_garants_pages(self) -> None:
        pages = build_all_garants_pages()
        self.garants_pages = {i + 1: page for i, page in enumerate(pages)}

    def get_responses(self, t_type: str, payload: str) -> list[dict[str, Any]]:
        if t_type == "command" and payload.lstrip("/").lower() == "garants":
            self._refresh_garants_pages()
            first = self.garants_pages.get(1)
            return [first] if first else []

        if t_type == "callback" and payload.startswith("garants_page:"):
            try:
                page = int(payload.split(":")[-1])
            except ValueError:
                return []
            self._refresh_garants_pages()
            found = self.garants_pages.get(page)
            return [found] if found else []

        key = self._trigger_key(t_type, payload)
        if key and key in self.by_trigger:
            return self._finalize_responses(t_type, payload, self.by_trigger[key])

        if t_type == "command":
            alias = CALLBACK_ALIASES.get(payload.lstrip("/").lower())
            if alias:
                return self._finalize_responses(t_type, payload, self.by_trigger.get(alias, []))

        if t_type == "text":
            cmd = TEXT_TO_COMMAND.get(payload.lower())
            if cmd:
                return self._finalize_responses(
                    "command", cmd, self.by_trigger.get(("command", cmd), [])
                )
            return self._finalize_responses(
                t_type, payload, self.by_trigger.get(("text", payload.lower()), [])
            )

        if t_type == "callback":
            if payload in CALLBACK_ALIASES:
                alias = CALLBACK_ALIASES[payload]
                return self._finalize_responses(t_type, payload, self.by_trigger.get(alias, []))
        return []

    async def send_responses(
        self,
        target: Message | CallbackQuery,
        responses: list[dict[str, Any]],
        *,
        personalize: bool = False,
        force_photo: str | None = None,
    ) -> None:
        is_callback = isinstance(target, CallbackQuery)
        message = target.message if is_callback else target
        if message is None:
            return

        if not responses:
            if is_callback:
                await target.answer("Нет данных для этого действия.", show_alert=True)
            else:
                await message.answer("Нет данных для этого действия.")
            return

        for idx, resp in enumerate(responses):
            text = apply_bot_branding(resp.get("text", ""))
            if personalize and message.from_user:
                user = message.from_user
                uname = f"@{user.username}" if user.username else user.full_name
                text = text.replace("@Alepasik", uname)
                text = text.replace("Alepasik", user.full_name or uname)
                if user.id:
                    text = re.sub(
                        r"\[\d+\]",
                        f"[<code>{user.id}</code>]",
                        text,
                        count=1,
                    )

            html = entities_to_html(text, resp.get("entities", []))
            if personalize and message.from_user and message.from_user.id:
                html = re.sub(
                    r"🪪id:\s*\[\d+\]",
                    f"🪪id: [<code>{message.from_user.id}</code>]",
                    html,
                    count=1,
                )
            kb = keyboard_from_dict(resp.get("keyboard"))
            asset = resp.get("asset_path")
            sent = False

            if asset:
                path = BASE_DIR / asset
                if path.is_file():
                    sent = await self._send_media(message, path, html, kb, resp.get("media"))
                else:
                    logger.warning("Медиа не найдено: %s", path)

            if not sent and force_photo and idx == 0:
                forced = get_photo(force_photo)
                if forced:
                    sent = await self._send_media(
                        message, forced, html, kb, resp.get("media"),
                    )

            if not sent:
                trigger = resp.get("trigger") or {}
                if trigger.get("type") == "command":
                    payload = trigger.get("payload", "")
                    cmd_photo = photo_for_command(payload)
                    if cmd_photo and payload == "/start":
                        media = resp.get("media") or {}
                        if not media.get("has_photo") and "Добро Пожаловать" not in text:
                            cmd_photo = None
                    if cmd_photo:
                        sent = await self._send_media(
                            message, cmd_photo, html, kb, resp.get("media"),
                        )

            if not sent and "Официальные гаранты" in text:
                garants_img = get_photo("garants")
                if garants_img:
                    sent = await self._send_media(message, garants_img, html, kb, resp.get("media"))

            if not sent:
                sent = await self._send_text(
                    message, html, text, kb,
                    edit=is_callback and idx == 0,
                )

        if is_callback:
            try:
                await target.answer()
            except Exception:
                pass

    async def _send_text(
        self,
        message: Message,
        html: str,
        plain: str,
        kb: Any,
        *,
        edit: bool = False,
    ) -> bool:
        if not html.strip() and not plain.strip():
            if kb is not None:
                try:
                    await message.answer(" ", reply_markup=kb)
                    return True
                except TelegramBadRequest:
                    return False
            return False

        variants: list[tuple[str, str | None]] = []
        if html.strip():
            variants.append((html, "HTML"))
            if not self._is_safe_html(html):
                simplified = self._simplify_html(html)
                if simplified.strip() and simplified != html:
                    variants.append((simplified, "HTML"))
        if plain.strip():
            variants.append((plain.strip(), None))

        seen: set[str] = set()
        for content, parse_mode in variants:
            if content in seen:
                continue
            seen.add(content)
            try:
                kwargs: dict[str, Any] = {"reply_markup": kb, "parse_mode": parse_mode}
                if edit:
                    await message.edit_text(content, **kwargs)
                else:
                    await message.answer(content, **kwargs)
                return True
            except TelegramBadRequest:
                continue
            except Exception as exc:
                logger.warning("Ошибка отправки текста: %s", exc)
                continue
        return False

    @staticmethod
    def _is_safe_html(html: str) -> bool:
        if not html:
            return False
        if re.search(r"<a\s+[^>]*href\s*=\s*\"\"", html):
            return False
        if re.search(r"<a[^>]*href=\"[^\"]*\"\s*[^>]*>", html) is None and "<a " in html:
            if "<a href=" not in html:
                return False
        if "<tg-emoji" in html:
            return bool(re.search(r'<tg-emoji emoji-id="\d+">', html))
        return True

    @staticmethod
    def _simplify_html(html: str) -> str:
        text = re.sub(
            r"<tg-emoji[^>]*>(.*?)</tg-emoji>",
            r"\1",
            html,
            flags=re.DOTALL,
        )
        text = re.sub(r"<a href=\"[^\"]*\">(.*?)</a>", r"\1", text)
        text = re.sub(r"</?b>", "", text)
        text = re.sub(r"</?i>", "", text)
        text = re.sub(r"<code>(.*?)</code>", r"\1", text)
        return text.strip()

    def _photo_caption_variants(self, html: str) -> list[str | None]:
        if not html.strip():
            return [None]
        variants: list[str | None] = []
        variants.append(html)
        simplified = self._simplify_html(html)
        if simplified and simplified not in variants:
            variants.append(simplified)
        plain = re.sub(r"<[^>]+>", "", simplified or html)
        if plain.strip() and plain.strip() not in {v for v in variants if v}:
            variants.append(plain.strip())
        variants.append(None)
        return variants

    async def _send_media(
        self,
        message: Message,
        path: Path,
        html: str,
        kb: Any,
        media: dict[str, Any] | None,
    ) -> bool:
        media = media or {}
        media_type = media.get("type", "")
        suffix = path.suffix.lower()
        file = FSInputFile(path)
        is_photo = "Photo" in media_type or suffix in {".jpg", ".jpeg", ".png", ".webp"}

        if is_photo:
            for caption in self._photo_caption_variants(html):
                try:
                    kwargs: dict[str, Any] = {"photo": file, "reply_markup": kb}
                    if caption:
                        kwargs["caption"] = caption
                        if "<" in caption:
                            kwargs["parse_mode"] = "HTML"
                    await message.answer_photo(**kwargs)
                    return True
                except TelegramBadRequest as exc:
                    logger.warning("Фото %s caption=%r: %s", path.name, caption, exc)
                    continue
                except Exception as exc:
                    logger.warning("Ошибка отправки фото %s: %s", path, exc)
                    break

            try:
                await message.answer_photo(photo=file)
                if html.strip():
                    await self._send_text(message, html, html, kb)
                elif kb is not None:
                    await message.answer(" ", reply_markup=kb)
                return True
            except Exception as exc:
                logger.warning("Ошибка отправки фото %s: %s", path, exc)
                return False

        try:
            if media.get("sticker") or suffix == ".tgs":
                await message.answer_sticker(sticker=file, reply_markup=kb)
                return True
            if html.strip():
                await message.answer_document(document=file, caption=html, reply_markup=kb)
            else:
                await message.answer_document(document=file, reply_markup=kb)
            return True
        except Exception as exc:
            logger.warning("Ошибка отправки медиа %s: %s", path, exc)
            return False


runtime = BotRuntime()