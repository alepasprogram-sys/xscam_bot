import re
from dataclasses import dataclass

from aiogram.types import Message

@dataclass
class ParsedTarget:
    username: str | None = None
    user_id: int | None = None
    raw: str = ""


_USERNAME_RE = re.compile(r"^@?([a-zA-Z0-9_]{5,32})$")
_TME_RE = re.compile(
    r"(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]{5,32})",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"^\d{5,15}$")
_ID_IN_TEXT_RE = re.compile(
    r"(?:🪪\s*)?id:\s*\[?\s*(?:<code>)?(\d{5,15})",
    re.IGNORECASE,
)


def parse_target(text: str) -> ParsedTarget | None:
    text = (text or "").strip()
    if not text:
        return None

    if m := _TME_RE.search(text):
        return ParsedTarget(username=m.group(1).lower(), raw=text)

    if m := _USERNAME_RE.match(text):
        return ParsedTarget(username=m.group(1).lower(), raw=text)

    if _ID_RE.match(text):
        return ParsedTarget(user_id=int(text), raw=text)

    return None


def parse_forwarded_user(message: Message) -> ParsedTarget | None:
    user = None
    if message.forward_from:
        user = message.forward_from
    elif message.forward_origin:
        sender = getattr(message.forward_origin, "sender_user", None)
        if sender:
            user = sender

    if not user or getattr(user, "is_bot", False):
        return None

    return ParsedTarget(
        username=user.username.lower() if user.username else None,
        user_id=user.id,
        raw=f"forward:{user.id}",
    )


def _id_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = _ID_IN_TEXT_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_target_from_message(message: Message) -> ParsedTarget | None:
    if message.reply_to_message:
        reply = message.reply_to_message
        parsed = parse_forwarded_user(reply)
        if parsed:
            return parsed
        if reply.from_user and not reply.from_user.is_bot:
            return ParsedTarget(
                username=reply.from_user.username.lower() if reply.from_user.username else None,
                user_id=reply.from_user.id,
                raw=f"reply:{reply.from_user.id}",
            )
        for blob in (reply.text, reply.caption):
            found_id = _id_from_text(blob)
            if found_id:
                parsed = parse_target(blob or "")
                return ParsedTarget(
                    username=parsed.username if parsed else None,
                    user_id=found_id,
                    raw=f"reply_id:{found_id}",
                )
            if blob:
                parsed = parse_target(blob)
                if parsed:
                    return parsed
    if message.text:
        return parse_target(message.text.strip())
    return None


def format_target(username: str | None, user_id: int | None) -> str:
    if username:
        return f"@{username.lstrip('@')}"
    if user_id:
        return str(user_id)
    return "—"