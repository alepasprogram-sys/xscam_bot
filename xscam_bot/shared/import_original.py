"""Импорт базы скамеров и справочников из оригинального @Xscam_bot."""
import json
import logging
import sqlite3
from pathlib import Path

from shared import database as db
from shared.config import ADMINS_DETAILED, BASE_DIR, GARANTS_DETAILED

logger = logging.getLogger(__name__)

DATA_DIR = BASE_DIR / "data"
DEFAULT_SOURCE = DATA_DIR / "original_xscam.db"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {r[1].lower() for r in rows}
    except sqlite3.Error:
        return set()


def _pick_column(columns: set[str], *candidates: str) -> str | None:
    for name in candidates:
        if name.lower() in columns:
            return name
    return None


def _extract_blacklist_rows(conn: sqlite3.Connection) -> list[dict]:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    for table in ("blacklist", "scammers", "scam_list", "scam_users", "black_list"):
        if table not in tables:
            continue
        cols = _table_columns(conn, table)
        user_col = _pick_column(cols, "target_username", "username", "user_username", "tg_username")
        id_col = _pick_column(cols, "target_id", "user_id", "telegram_id", "tg_id")
        reason_col = _pick_column(cols, "reason", "description", "comment", "note")
        if not user_col and not id_col:
            continue
        select = []
        if id_col:
            select.append(id_col)
        else:
            select.append("NULL")
        if user_col:
            select.append(user_col)
        else:
            select.append("NULL")
        if reason_col:
            select.append(reason_col)
        else:
            select.append("''")
        sql = f"SELECT {', '.join(select)} FROM {table}"
        rows = conn.execute(sql).fetchall()
        result = []
        for row in rows:
            uid, uname, reason = row[0], row[1], row[2] if len(row) > 2 else ""
            if uname:
                uname = str(uname).lstrip("@").lower()
            result.append({
                "target_id": int(uid) if uid else None,
                "target_username": uname or None,
                "reason": str(reason or "")[:500],
            })
        if result:
            logger.info("Найдена таблица %s: %s записей", table, len(result))
            return result
    return []


def import_blacklist_from_sqlite(
    source: Path,
    *,
    added_by: int = 0,
    clear_existing: bool = False,
) -> dict[str, int]:
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Файл не найден: {source}")

    src = sqlite3.connect(source)
    try:
        rows = _extract_blacklist_rows(src)
    finally:
        src.close()

    if clear_existing:
        db.clear_blacklist()

    added = 0
    skipped = 0
    for row in rows:
        if not row.get("target_username") and not row.get("target_id"):
            skipped += 1
            continue
        ok = db.add_blacklist(
            target_username=row.get("target_username"),
            target_id=row.get("target_id"),
            reason=row.get("reason", ""),
            added_by=added_by,
        )
        if ok:
            added += 1
        else:
            skipped += 1

    return {"added": added, "skipped": skipped, "total_source": len(rows)}


def import_catalog_from_json(path: Path) -> dict[str, int]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    garants = data.get("garants", data.get("GARANTS_DETAILED", []))
    admins = data.get("admins", data.get("ADMINS_DETAILED", []))
    g = db.replace_catalog_garants(garants) if garants else 0
    a = db.replace_catalog_admins(admins) if admins else 0
    return {"garants": g, "admins": a}


def seed_catalog_from_config() -> dict[str, int]:
    json_path = DATA_DIR / "catalog.json"
    if json_path.is_file():
        return import_catalog_from_json(json_path)
    db.replace_catalog_garants(GARANTS_DETAILED)
    db.replace_catalog_admins(ADMINS_DETAILED)
    return {
        "garants": db.count_catalog_garants(),
        "admins": db.count_catalog_admins(),
    }


def import_all_from_sqlite(
    source: Path,
    *,
    added_by: int = 0,
    clear_blacklist: bool = False,
) -> dict:
    stats = {"blacklist": import_blacklist_from_sqlite(source, added_by=added_by, clear_existing=clear_blacklist)}
    json_path = source.parent / "catalog.json"
    if json_path.is_file():
        stats["catalog"] = import_catalog_from_json(json_path)
    else:
        stats["catalog"] = seed_catalog_from_config()
    return stats


def auto_import_if_present(added_by: int = 0) -> dict | None:
    if not DEFAULT_SOURCE.is_file():
        return None
    logger.info("Найден %s — импорт базы оригинала", DEFAULT_SOURCE)
    stats = import_all_from_sqlite(DEFAULT_SOURCE, added_by=added_by, clear_blacklist=True)
    logger.info("Импорт завершён: %s", stats)
    return stats