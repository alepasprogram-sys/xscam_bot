"""Состояния диалогов пользователя (поиск гарантов и т.д.)."""

from __future__ import annotations

_sessions: dict[int, dict] = {}


def get(user_id: int) -> dict:
    return _sessions.setdefault(user_id, {})


def clear(user_id: int) -> None:
    _sessions.pop(user_id, None)


def set_flow(user_id: int, flow: str) -> None:
    get(user_id)["flow"] = flow


def get_flow(user_id: int) -> str | None:
    return get(user_id).get("flow")


def pop_flow(user_id: int) -> str | None:
    return get(user_id).pop("flow", None)