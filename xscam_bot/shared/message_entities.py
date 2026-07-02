"""Конвертация entities из сообщения Telegram в HTML."""

from __future__ import annotations

from aiogram.types import Message

from runtime import entities_to_html


def message_entities_as_dicts(message: Message) -> list[dict]:
    if not message.entities:
        return []
    rows: list[dict] = []
    for ent in message.entities:
        row: dict = {
            "type": ent.type,
            "offset": ent.offset,
            "length": ent.length,
        }
        if ent.url:
            row["url"] = ent.url
        if ent.custom_emoji_id:
            row["document_id"] = ent.custom_emoji_id
        rows.append(row)
    return rows


def message_to_storage_html(message: Message) -> str:
    text = message.text or message.caption or ""
    entities = message_entities_as_dicts(message)
    if entities:
        return entities_to_html(text, entities)
    return text