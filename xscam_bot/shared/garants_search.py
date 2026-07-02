"""Поиск гарантов по нику, каналу или ручению."""

from __future__ import annotations

from shared import database as db


def _handlers_blob(entry: dict) -> str:
    parts: list[str] = []
    handlers = entry.get("handlers")
    if isinstance(handlers, list):
        parts.extend(str(h) for h in handlers if h)
    handler = entry.get("handler")
    if handler:
        parts.append(str(handler))
    return " ".join(parts).lower()


def search_garants(query: str) -> list[dict]:
    q = (query or "").strip().lower().lstrip("@")
    if not q or len(q) < 2:
        return []

    exact: list[dict] = []
    prefix: list[dict] = []
    partial: list[dict] = []

    for entry in db.get_catalog_garants():
        username = (entry.get("username") or "").lower().lstrip("@")
        channel = (entry.get("channel") or "").lower().lstrip("@")
        handlers = _handlers_blob(entry)
        proofs = (entry.get("proofs") or "").lower()

        if username == q:
            exact.append(entry)
        elif username.startswith(q):
            prefix.append(entry)
        elif (
            q in username
            or q in channel
            or q in handlers
            or q in proofs
            or channel.startswith(q)
        ):
            partial.append(entry)

    return exact or prefix or partial