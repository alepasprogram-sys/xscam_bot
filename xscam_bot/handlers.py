"""Обработчики @Xscamss_bot — ответы из bot_data.json + проверка/поиск."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, TelegramObject

from shared import database as db

import flows
from profile_builder import entry_user_id, send_profile, username_from_garant
from runtime import TEXT_TO_COMMAND, BotRuntime, entities_to_html, runtime
from shared.garants_search import search_garants
from shared.parsers import parse_target, parse_target_from_message, parse_forwarded_user

router = Router()


class TrackUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            db.touch_user(user.id, user.username, user.full_name)
        return await handler(event, data)


router.message.middleware(TrackUserMiddleware())
router.callback_query.middleware(TrackUserMiddleware())

COMMANDS = [
    "info", "help", "garants", "admins",
    "sponsors", "start_deal", "cancel", "id", "t",
]


def _register_command(cmd: str) -> None:
    @router.message(Command(cmd))
    async def handler(message: Message, _cmd: str = cmd) -> None:
        key = "start" if _cmd == "t" else _cmd
        responses = runtime.get_responses("command", f"/{key}")

        if not responses and _cmd == "id" and message.from_user:
            await message.answer(
                f"🪪 Ваш ID: <code>{message.from_user.id}</code>",
            )
            return

        if not responses and _cmd == "sponsors":
            responses = runtime.get_responses("command", "/info")

        force_photo = "start" if key == "start" else None
        await runtime.send_responses(message, responses, force_photo=force_photo)

    handler.__name__ = f"handle_{cmd}"


for command in COMMANDS:
    _register_command(command)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    if message.from_user:
        flows.clear(message.from_user.id)
    responses = runtime.get_responses("command", "/start")
    await runtime.send_responses(message, responses, force_photo="start")


@router.message(Command("me"))
async def handle_me(message: Message) -> None:
    if not message.from_user:
        return
    flows.clear(message.from_user.id)
    await send_profile(
        message,
        username=message.from_user.username,
        user_id=message.from_user.id,
        log_check=False,
    )


@router.message(Command("check"))
async def handle_check(message: Message, command: CommandObject) -> None:
    if message.from_user:
        flows.clear(message.from_user.id)

    parsed = None
    if command.args:
        parsed = parse_target(command.args.strip())
    if not parsed:
        parsed = parse_target_from_message(message)

    if not parsed:
        responses = runtime.get_responses("command", "/check")
        await runtime.send_responses(message, responses)
        return

    await send_profile(
        message,
        username=parsed.username,
        user_id=parsed.user_id,
    )


@router.message(Command("cancel"))
async def handle_cancel(message: Message) -> None:
    if message.from_user:
        flows.clear(message.from_user.id)
    responses = runtime.get_responses("command", "/cancel")
    await runtime.send_responses(message, responses)


@router.message(F.text.func(lambda t: t is not None and t.lower() in TEXT_TO_COMMAND))
async def handle_menu_button(message: Message) -> None:
    if not message.from_user:
        return
    flows.clear(message.from_user.id)
    cmd = TEXT_TO_COMMAND[message.text.lower()]

    if cmd == "me":
        await send_profile(
            message,
            username=message.from_user.username,
            user_id=message.from_user.id,
            log_check=False,
        )
        return

    responses = runtime.get_responses("command", f"/{cmd}")
    await runtime.send_responses(message, responses)


@router.message(
    F.text.func(lambda t: t is not None and ("text", t.lower()) in runtime.by_trigger)
)
async def handle_text_button(message: Message) -> None:
    responses = runtime.get_responses("text", message.text)
    await runtime.send_responses(message, responses)


@router.callback_query(F.data == "noop")
async def handle_noop(callback: CallbackQuery) -> None:
    await callback.answer()


GARANTS_SEARCH_PROMPT = (
    "🔎 Введите @username, часть ника или канал (без @) "
    "или напишите /cancel для отмены."
)


@router.callback_query(F.data == "garants:search")
async def handle_garants_search(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        await callback.answer()
        return
    flows.set_flow(callback.from_user.id, "garants_search")
    await callback.answer()
    responses = runtime.get_responses("callback", "garants:search")
    if responses:
        resp = responses[0]
        text = resp.get("text") or GARANTS_SEARCH_PROMPT
        html = entities_to_html(text, resp.get("entities", []))
        if BotRuntime._is_safe_html(html):
            await callback.message.answer(html, parse_mode="HTML")
        else:
            await callback.message.answer(text)
    else:
        await callback.message.answer(GARANTS_SEARCH_PROMPT)


@router.callback_query()
async def handle_callback(callback: CallbackQuery) -> None:
    if not callback.data:
        await callback.answer()
        return

    if callback.data.strip().lower() in {"/me", "me"} and callback.message:
        if callback.from_user:
            flows.clear(callback.from_user.id)
            await send_profile(
                callback.message,
                username=callback.from_user.username,
                user_id=callback.from_user.id,
                log_check=False,
            )
        await callback.answer()
        return

    responses = runtime.get_responses("callback", callback.data)
    personalize = callback.data == "🔗 Вечная ссылка"
    await runtime.send_responses(callback, responses, personalize=personalize)


def _is_menu_text(text: str) -> bool:
    lower = text.lower()
    return lower in TEXT_TO_COMMAND or ("text", lower) in runtime.by_trigger


@router.message(F.text)
async def handle_free_text(message: Message) -> None:
    if not message.from_user or not message.text:
        return

    text = message.text.strip()
    uid = message.from_user.id

    if _is_menu_text(text):
        return

    flow = flows.get_flow(uid)

    if flow == "garants_search":
        if text.lower() in ("/cancel", "cancel"):
            flows.pop_flow(uid)
            responses = runtime.get_responses("command", "/cancel")
            await runtime.send_responses(message, responses)
            return

        results = search_garants(text)
        if not results:
            await message.answer("Ничего не найдено.")
            flows.set_flow(uid, "garants_search")
            return

        flows.pop_flow(uid)
        for garant in results[:3]:
            await send_profile(
                message,
                username=username_from_garant(garant),
                user_id=entry_user_id(garant),
            )
        return

    if message.forward_origin:
        parsed = parse_forwarded_user(message)
        if parsed:
            flows.clear(uid)
            await send_profile(
                message,
                username=parsed.username,
                user_id=parsed.user_id,
            )
            return

    parsed = parse_target(text)
    if parsed:
        await send_profile(
            message,
            username=parsed.username,
            user_id=parsed.user_id,
        )
        return

    await message.answer("Используйте /start или кнопки меню.")


@router.message()
async def handle_forward_or_unknown(message: Message) -> None:
    if message.forward_origin:
        parsed = parse_forwarded_user(message)
        if parsed:
            flows.clear(message.from_user.id if message.from_user else 0)
            await send_profile(
                message,
                username=parsed.username,
                user_id=parsed.user_id,
            )
            return

    await message.answer("Используйте /start или кнопки меню.")