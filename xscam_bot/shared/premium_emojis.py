"""ID премиум-эмодзи из 44/эмодзи.txt."""

from __future__ import annotations

# Профиль / check / me
PROFILE_NAME = "5870994129244131212"
PROFILE_ID = "5936017305585586269"
PROFILE_DB_CHECK = "5258096772776991776"
PROFILE_ROLE = "5877495434124988415"
PROFILE_ROLE_ARROW = "5884123981706956210"
PROFILE_CLEAN_USER = "5870695289714643076"
PROFILE_SEARCHED = "5429571366384842791"
PROFILE_VERIFIED = "5350626672028697529"
PROFILE_DATE = "5258105663359294787"

# Админы — ник в скобках (старшие)
ADMIN_NICK_SENIOR = "5877530150345641603"


def tg(emoji_id: str | int, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'