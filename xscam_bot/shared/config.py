import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "234252234252")

_raw_bot_username = os.getenv("BOT_USERNAME", "Xscamss_bot").strip().lstrip("@")
BOT_USERNAME = f"@{_raw_bot_username}"

_db_env = os.getenv("DATABASE_PATH", "").strip()
DB_PATH = Path(_db_env) if _db_env else BASE_DIR / "xscam.db"

from shared.garants_data import GARANTS_DETAILED, GARANTS_PAGE_SIZES  # noqa: E402

ADMINS_DETAILED = [
    {"username": "@Omega_Darkes", "channel": "@ProofsOmega"},
    {"username": "@ARESOFF", "main": True, "scammers_count": 615},
]