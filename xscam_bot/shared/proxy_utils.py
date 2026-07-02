"""Проверка и выбор прокси для Telegram API."""

from __future__ import annotations

import os
import socket


def proxy_port_open(proxy: str) -> bool:
    if not proxy.startswith("socks5://"):
        return False
    host_port = proxy.removeprefix("socks5://")
    if ":" not in host_port:
        return False
    host, port_s = host_port.rsplit(":", 1)
    try:
        port = int(port_s)
    except ValueError:
        return False
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def default_proxy() -> str:
    """Локально — VPN; на Scalingo/Heroku — напрямую."""
    if os.getenv("SCALINGO_APP") or os.getenv("DYNO"):
        return ""
    return "socks5://127.0.0.1:10808"


def resolve_proxy() -> str | None:
    """Прокси из .env, если порт отвечает; иначе None (напрямую)."""
    raw = os.getenv("PROXY", default_proxy()).strip()
    if not raw:
        return None
    if proxy_port_open(raw):
        return raw
    return None