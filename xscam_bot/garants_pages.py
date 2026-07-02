"""Страницы гарантов — строятся динамически из БД."""

from __future__ import annotations

from typing import Any

from shared.garants_list import build_all_garants_pages, build_garants_page, total_garants_pages

TOTAL_PAGES = 4  # fallback для старого кода; актуально — total_garants_pages()


def build_synthetic_page(page: int) -> dict[str, Any]:
    return build_garants_page(page)