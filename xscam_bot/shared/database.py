import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from shared.config import DB_PATH

COMPLAINT_PENDING = "pending"
COMPLAINT_APPROVED = "approved"
COMPLAINT_REJECTED = "rejected"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_start() -> str:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS bot_users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                first_seen TEXT NOT NULL,
                last_active TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blacklist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                target_username TEXT,
                reason TEXT DEFAULT '',
                added_by INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(target_id),
                UNIQUE(target_username)
            );

            CREATE INDEX IF NOT EXISTS idx_blacklist_username
                ON blacklist(target_username);
            CREATE INDEX IF NOT EXISTS idx_blacklist_id
                ON blacklist(target_id);

            CREATE TABLE IF NOT EXISTS check_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checker_id INTEGER NOT NULL,
                target_username TEXT,
                target_id INTEGER,
                found INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS complaints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reporter_id INTEGER NOT NULL,
                reporter_username TEXT,
                target_username TEXT,
                target_id INTEGER,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_complaints_status
                ON complaints(status);

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS broadcast_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                sent_count INTEGER NOT NULL,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS target_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_username TEXT,
                target_id INTEGER,
                search_count INTEGER NOT NULL DEFAULT 0,
                last_checked TEXT NOT NULL,
                UNIQUE(target_username),
                UNIQUE(target_id)
            );

            CREATE TABLE IF NOT EXISTS catalog_garants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flag TEXT DEFAULT '🇷🇺',
                username TEXT NOT NULL UNIQUE,
                proofs TEXT DEFAULT '0+',
                channel TEXT,
                rating TEXT DEFAULT '5.0/5',
                deal_price TEXT DEFAULT '0₽',
                handler TEXT,
                handlers TEXT,
                subgroup TEXT DEFAULT 'Элитные гаранты',
                tier TEXT DEFAULT 'elite',
                role_label TEXT,
                rating_votes INTEGER DEFAULT 0,
                deals_count INTEGER,
                senior_admin TEXT,
                scammers_added INTEGER,
                warns TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS suspicious (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id INTEGER,
                target_username TEXT,
                reason TEXT DEFAULT '',
                referrer TEXT,
                added_by INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(target_username),
                UNIQUE(target_id)
            );

            CREATE INDEX IF NOT EXISTS idx_suspicious_username
                ON suspicious(target_username);
            CREATE INDEX IF NOT EXISTS idx_suspicious_id
                ON suspicious(target_id);

            CREATE TABLE IF NOT EXISTS catalog_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                channel TEXT,
                is_main INTEGER NOT NULL DEFAULT 0,
                scammers_count INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0
            );
        """)
        _migrate_catalog_garants(conn)
        _migrate_profile_stats(conn)
    sync_known_target_ids()


def _migrate_profile_stats(conn: sqlite3.Connection) -> None:
    for table in ("blacklist", "suspicious", "catalog_garants"):
        columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if table != "catalog_garants" and "scam_count" not in columns:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN scam_count INTEGER DEFAULT 0"
            )
        if "photo_file" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN photo_file TEXT")
        if "profile_text" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN profile_text TEXT")


def _migrate_catalog_garants(conn: sqlite3.Connection) -> None:
    columns = {r[1] for r in conn.execute("PRAGMA table_info(catalog_garants)").fetchall()}
    additions = {
        "handlers": "TEXT",
        "subgroup": "TEXT DEFAULT 'Элитные гаранты'",
        "tier": "TEXT DEFAULT 'elite'",
        "role_label": "TEXT",
        "rating_votes": "INTEGER DEFAULT 0",
        "deals_count": "INTEGER",
        "senior_admin": "TEXT",
        "scammers_added": "INTEGER",
        "warns": "TEXT",
        "photo_file": "TEXT",
        "telegram_id": "INTEGER",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE catalog_garants ADD COLUMN {name} {ddl}")


def _serialize_handlers(entry: dict) -> str | None:
    handlers = entry.get("handlers")
    if isinstance(handlers, list) and handlers:
        return "\n".join(handlers)
    handler = entry.get("handler")
    return handler


def _deserialize_handlers(handler: str | None, handlers: str | None) -> list[str]:
    if handlers:
        return [line.strip() for line in handlers.splitlines() if line.strip()]
    if handler:
        return [handler.strip()]
    return []


def _garant_row_to_dict(row: sqlite3.Row) -> dict:
    handlers = _deserialize_handlers(row["handler"], row["handlers"] if "handlers" in row.keys() else None)
    data = {
        "id": row["id"],
        "flag": row["flag"],
        "username": row["username"],
        "proofs": row["proofs"],
        "channel": row["channel"],
        "rating": row["rating"],
        "deal_price": row["deal_price"],
        "subgroup": row["subgroup"] if "subgroup" in row.keys() else "Элитные гаранты",
        "tier": row["tier"] if "tier" in row.keys() else "elite",
        "role_label": row["role_label"] if "role_label" in row.keys() else None,
        "rating_votes": int(row["rating_votes"]) if row["rating_votes"] is not None else 0,
        "deals_count": row["deals_count"] if "deals_count" in row.keys() else None,
        "senior_admin": row["senior_admin"] if "senior_admin" in row.keys() else None,
        "scammers_added": row["scammers_added"] if "scammers_added" in row.keys() else None,
        "warns": row["warns"] if "warns" in row.keys() else None,
        "photo_file": row["photo_file"] if "photo_file" in row.keys() else None,
        "profile_text": row["profile_text"] if "profile_text" in row.keys() else None,
    }
    if "telegram_id" in row.keys() and row["telegram_id"]:
        data["telegram_id"] = int(row["telegram_id"])
        data["target_id"] = int(row["telegram_id"])
    if handlers:
        data["handlers"] = handlers
        data["handler"] = handlers[0]
    tier = data.get("tier", "elite")
    subgroup = data.get("subgroup", "Элитные гаранты")
    if tier == "regular" or subgroup == "Гаранты":
        data["list_style"] = "compact"
    return data


def _norm_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.lstrip("@").lower()


def lookup_target_id(username: str | None, user_id: int | None = None) -> int | None:
    """Найти Telegram ID по всем известным источникам."""
    if user_id is not None:
        return int(user_id)

    uname = _norm_username(username)
    with get_db() as conn:
        if uname:
            garant = conn.execute(
                """SELECT telegram_id FROM catalog_garants
                   WHERE LOWER(REPLACE(username, '@', '')) = ? AND telegram_id IS NOT NULL""",
                (uname,),
            ).fetchone()
            if garant and garant["telegram_id"]:
                return int(garant["telegram_id"])

            for table in ("blacklist", "suspicious"):
                row = conn.execute(
                    f"""SELECT target_id FROM {table}
                        WHERE target_id IS NOT NULL
                          AND LOWER(REPLACE(target_username, '@', '')) = ?""",
                    (uname,),
                ).fetchone()
                if row and row["target_id"]:
                    return int(row["target_id"])

            row = conn.execute(
                """SELECT target_id FROM target_stats
                   WHERE target_id IS NOT NULL
                     AND target_username = ? COLLATE NOCASE""",
                (uname,),
            ).fetchone()
            if row and row["target_id"]:
                return int(row["target_id"])

            row = conn.execute(
                """SELECT target_id FROM check_log
                   WHERE target_id IS NOT NULL
                     AND LOWER(REPLACE(target_username, '@', '')) = ?
                   ORDER BY id DESC LIMIT 1""",
                (uname,),
            ).fetchone()
            if row and row["target_id"]:
                return int(row["target_id"])

            row = conn.execute(
                """SELECT telegram_id FROM bot_users
                   WHERE username IS NOT NULL
                     AND LOWER(REPLACE(username, '@', '')) = ?
                   ORDER BY last_active DESC LIMIT 1""",
                (uname,),
            ).fetchone()
            if row and row["telegram_id"]:
                return int(row["telegram_id"])

            row = conn.execute(
                """SELECT target_id FROM complaints
                   WHERE target_id IS NOT NULL
                     AND LOWER(REPLACE(target_username, '@', '')) = ?
                   ORDER BY id DESC LIMIT 1""",
                (uname,),
            ).fetchone()
            if row and row["target_id"]:
                return int(row["target_id"])

    return None


def _id_for_username(conn: sqlite3.Connection, uname: str) -> int | None:
    sources = (
        ("blacklist", "target_username", "target_id"),
        ("suspicious", "target_username", "target_id"),
        ("target_stats", "target_username", "target_id"),
        ("complaints", "target_username", "target_id"),
        ("bot_users", "username", "telegram_id"),
    )
    for table, ucol, idcol in sources:
        row = conn.execute(
            f"""SELECT {idcol} AS tid FROM {table}
                WHERE {idcol} IS NOT NULL
                  AND LOWER(REPLACE({ucol}, '@', '')) = ?""",
            (uname,),
        ).fetchone()
        if row and row["tid"]:
            return int(row["tid"])

    row = conn.execute(
        """SELECT target_id FROM check_log
           WHERE target_id IS NOT NULL
             AND LOWER(REPLACE(target_username, '@', '')) = ?
           ORDER BY id DESC LIMIT 1""",
        (uname,),
    ).fetchone()
    if row and row["target_id"]:
        return int(row["target_id"])
    return None


def sync_known_target_ids() -> int:
    """Подтянуть telegram_id гарантов и target_id статистики из известных таблиц."""
    updated = 0
    with get_db() as conn:
        garants = conn.execute(
            "SELECT id, username, telegram_id FROM catalog_garants"
        ).fetchall()
        for garant in garants:
            if garant["telegram_id"]:
                continue
            uname = _norm_username(garant["username"])
            if not uname:
                continue
            tid = _id_for_username(conn, uname)
            if tid is None:
                continue
            conn.execute(
                "UPDATE catalog_garants SET telegram_id = ? WHERE id = ?",
                (tid, garant["id"]),
            )
            updated += 1

        stats = conn.execute(
            """SELECT id, target_username FROM target_stats
               WHERE target_id IS NULL AND target_username IS NOT NULL"""
        ).fetchall()
        for row in stats:
            uname = _norm_username(row["target_username"])
            if not uname:
                continue
            tid = _id_for_username(conn, uname)
            if tid is None:
                continue
            conn.execute(
                "UPDATE target_stats SET target_id = ? WHERE id = ?",
                (tid, row["id"]),
            )
            updated += 1

    return updated


def remember_target_id(username: str | None, user_id: int | None) -> None:
    """Запомнить связку username ↔ ID для будущих проверок."""
    if user_id is None:
        return
    user_id = int(user_id)
    uname = _norm_username(username)
    now = _now()

    with get_db() as conn:
        if uname:
            conn.execute(
                """UPDATE catalog_garants
                   SET telegram_id = ?
                   WHERE LOWER(REPLACE(username, '@', '')) = ?
                     AND (telegram_id IS NULL OR telegram_id = ?)""",
                (user_id, uname, user_id),
            )

            row = _stats_row_by_username(conn, uname)
            if row:
                if not row["target_id"]:
                    conn.execute(
                        "UPDATE target_stats SET target_id = ? WHERE id = ?",
                        (user_id, row["id"]),
                    )
            elif uname:
                try:
                    conn.execute(
                        """INSERT INTO target_stats
                           (target_username, target_id, search_count, last_checked)
                           VALUES (?, ?, 0, ?)""",
                        (uname, user_id, now),
                    )
                except sqlite3.IntegrityError:
                    pass

            conn.execute(
                """UPDATE check_log SET target_id = ?
                   WHERE target_id IS NULL
                     AND LOWER(REPLACE(target_username, '@', '')) = ?""",
                (user_id, uname),
            )

        if not uname:
            row = _stats_row_by_id(conn, user_id)
            if not row:
                try:
                    conn.execute(
                        """INSERT INTO target_stats
                           (target_username, target_id, search_count, last_checked)
                           VALUES (?, ?, 0, ?)""",
                        (None, user_id, now),
                    )
                except sqlite3.IntegrityError:
                    pass


def touch_user(telegram_id: int, username: str | None, first_name: str | None):
    now = _now()
    with get_db() as conn:
        row = conn.execute(
            "SELECT telegram_id FROM bot_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row:
            conn.execute(
                """UPDATE bot_users
                   SET username = ?, first_name = ?, last_active = ?
                   WHERE telegram_id = ?""",
                (username, first_name, now, telegram_id),
            )
        else:
            conn.execute(
                """INSERT INTO bot_users
                   (telegram_id, username, first_name, first_seen, last_active)
                   VALUES (?, ?, ?, ?, ?)""",
                (telegram_id, username, first_name, now, now),
            )


def get_total_users() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM bot_users").fetchone()
        return int(row["c"]) if row else 0


def get_monthly_active_users() -> int:
    month = _month_start()
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM bot_users WHERE last_active >= ?",
            (month,),
        ).fetchone()
        return int(row["c"]) if row else 0


def _users_word(n: int) -> str:
    n_abs = abs(n) % 100
    n_mod = n_abs % 10
    if n_mod == 1 and n_abs != 11:
        return "пользователь"
    if n_mod in (2, 3, 4) and n_abs not in (12, 13, 14):
        return "пользователя"
    return "пользователей"


def format_mau_count(n: int) -> str:
    formatted = f"{n:,}".replace(",", ".")
    return f"{formatted} {_users_word(n)}"


def format_mau_line() -> str:
    return format_mau_count(get_monthly_active_users())


def find_suspicious(username: str | None = None, user_id: int | None = None) -> dict | None:
    with get_db() as conn:
        if username:
            row = conn.execute(
                "SELECT * FROM suspicious WHERE target_username = ? COLLATE NOCASE",
                (_norm_username(username),),
            ).fetchone()
            if row:
                return dict(row)
        if user_id:
            row = conn.execute(
                "SELECT * FROM suspicious WHERE target_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return dict(row)
    return None


def add_suspicious(
    *,
    target_username: str | None,
    target_id: int | None,
    reason: str = "",
    referrer: str | None = None,
    added_by: int = 0,
    scam_count: int = 0,
    photo_file: str | None = None,
    profile_text: str | None = None,
) -> bool:
    if not target_username and not target_id:
        return False
    if target_username:
        target_username = target_username.lower().lstrip("@")
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO suspicious
                   (target_id, target_username, reason, referrer, scam_count, photo_file,
                    profile_text, added_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target_id,
                    target_username,
                    reason or "",
                    referrer,
                    int(scam_count or 0),
                    photo_file,
                    profile_text,
                    added_by,
                    _now(),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def remove_suspicious(username: str | None = None, user_id: int | None = None) -> bool:
    with get_db() as conn:
        if username:
            cur = conn.execute(
                "DELETE FROM suspicious WHERE target_username = ? COLLATE NOCASE",
                (username.lower().lstrip("@"),),
            )
            if cur.rowcount:
                return True
        if user_id:
            cur = conn.execute(
                "DELETE FROM suspicious WHERE target_id = ?",
                (user_id,),
            )
            if cur.rowcount:
                return True
    return False


def count_suspicious() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM suspicious").fetchone()
        return int(row["c"]) if row else 0


def find_blacklist(username: str | None = None, user_id: int | None = None) -> dict | None:
    with get_db() as conn:
        if username:
            row = conn.execute(
                "SELECT * FROM blacklist WHERE target_username = ? COLLATE NOCASE",
                (_norm_username(username),),
            ).fetchone()
            if row:
                return dict(row)
        if user_id:
            row = conn.execute(
                "SELECT * FROM blacklist WHERE target_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return dict(row)
    return None


def add_blacklist(
    *,
    target_username: str | None,
    target_id: int | None,
    reason: str,
    added_by: int,
    scam_count: int | None = None,
    photo_file: str | None = None,
    profile_text: str | None = None,
) -> bool:
    if not target_username and not target_id:
        return False
    if target_username:
        target_username = target_username.lower()
    count = scam_count
    if count is None and reason:
        count = sum(1 for line in reason.splitlines() if line.strip())
    if count is None:
        count = 0
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO blacklist
                   (target_id, target_username, reason, scam_count, photo_file, profile_text,
                    added_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target_id,
                    target_username,
                    reason or "",
                    int(count),
                    photo_file,
                    profile_text,
                    added_by,
                    _now(),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def update_blacklist_reason(entry_id: int, reason: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "UPDATE blacklist SET reason = ? WHERE id = ?",
            (reason, entry_id),
        )
        return cur.rowcount > 0


def remove_blacklist(username: str | None = None, user_id: int | None = None) -> bool:
    with get_db() as conn:
        if username:
            cur = conn.execute(
                "DELETE FROM blacklist WHERE target_username = ? COLLATE NOCASE",
                (username.lower(),),
            )
            if cur.rowcount:
                return True
        if user_id:
            cur = conn.execute(
                "DELETE FROM blacklist WHERE target_id = ?",
                (user_id,),
            )
            if cur.rowcount:
                return True
    return False


def list_blacklist(limit: int = 10, offset: int = 0) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM blacklist ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def count_blacklist() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM blacklist").fetchone()
        return int(row["c"]) if row else 0


def get_blacklist_entry(entry_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM blacklist WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None


ENTRY_TYPE_TABLES = {
    "scammer": "blacklist",
    "suspicious": "suspicious",
    "garant": "catalog_garants",
}


def get_entry_by_type(entry_type: str, entry_id: int) -> dict | None:
    table = ENTRY_TYPE_TABLES.get(entry_type)
    if not table:
        return None
    with get_db() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (entry_id,)).fetchone()
        if not row:
            return None
        if entry_type == "garant":
            return _garant_row_to_dict(row)
        return dict(row)


def list_entries_by_type(entry_type: str, *, limit: int = 10, offset: int = 0) -> list[dict]:
    table = ENTRY_TYPE_TABLES.get(entry_type)
    if not table:
        return []
    order = "sort_order, id" if entry_type == "garant" else "id DESC"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY {order} LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        if entry_type == "garant":
            return [_garant_row_to_dict(r) for r in rows]
        return [dict(r) for r in rows]


def count_entries_by_type(entry_type: str) -> int:
    table = ENTRY_TYPE_TABLES.get(entry_type)
    if not table:
        return 0
    with get_db() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"]) if row else 0


def delete_entry_by_type(entry_type: str, entry_id: int) -> bool:
    table = ENTRY_TYPE_TABLES.get(entry_type)
    if not table:
        return False
    with get_db() as conn:
        cur = conn.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
        return cur.rowcount > 0


def update_entry_field(entry_type: str, entry_id: int, **fields) -> bool:
    table = ENTRY_TYPE_TABLES.get(entry_type)
    if not table or not fields:
        return False
    allowed = {
        "scammer": {"reason", "photo_file", "profile_text", "scam_count", "target_id"},
        "suspicious": {"reason", "photo_file", "profile_text", "scam_count", "target_id"},
        "garant": {
            "photo_file", "profile_text", "channel", "tier", "subgroup", "role_label",
            "rating", "deal_price", "proofs", "flag", "handlers", "handler", "telegram_id",
            "warns", "senior_admin", "scammers_added", "deals_count", "rating_votes",
        },
    }.get(entry_type, set())
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    if entry_type == "garant" and "handlers" in updates:
        handlers = updates.pop("handlers")
        if isinstance(handlers, list):
            updates["handlers"] = _serialize_handlers({"handlers": handlers})
            updates["handler"] = handlers[0] if handlers else None
    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [entry_id]
    with get_db() as conn:
        cur = conn.execute(f"UPDATE {table} SET {cols} WHERE id = ?", values)
        return cur.rowcount > 0


def _stats_row_by_username(conn, username: str):
    return conn.execute(
        "SELECT * FROM target_stats WHERE target_username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()


def _stats_row_by_id(conn, user_id: int):
    return conn.execute(
        "SELECT * FROM target_stats WHERE target_id = ?",
        (user_id,),
    ).fetchone()


def increment_target_search(username: str | None, user_id: int | None) -> int:
    if not username and not user_id:
        return 0
    if username:
        username = username.lower()
    now = _now()
    with get_db() as conn:
        by_name = _stats_row_by_username(conn, username) if username else None
        by_id = _stats_row_by_id(conn, user_id) if user_id else None

        if by_name and by_id and by_name["id"] != by_id["id"]:
            merged = int(by_name["search_count"]) + int(by_id["search_count"]) + 1
            keep_id = by_name["id"]
            drop_id = by_id["id"]
            conn.execute("DELETE FROM target_stats WHERE id = ?", (drop_id,))
            conn.execute(
                """UPDATE target_stats
                   SET search_count = ?, last_checked = ?,
                       target_username = COALESCE(?, target_username),
                       target_id = COALESCE(?, target_id)
                   WHERE id = ?""",
                (merged, now, username, user_id, keep_id),
            )
            return merged

        row = by_name or by_id
        if row:
            count = int(row["search_count"]) + 1
            new_username = username if username and not row["target_username"] else None
            new_id = user_id if user_id and not row["target_id"] else None
            if new_username:
                clash = _stats_row_by_username(conn, new_username)
                if clash and clash["id"] != row["id"]:
                    new_username = None
            if new_id:
                clash = _stats_row_by_id(conn, new_id)
                if clash and clash["id"] != row["id"]:
                    new_id = None
            conn.execute(
                """UPDATE target_stats
                   SET search_count = ?, last_checked = ?,
                       target_username = COALESCE(?, target_username),
                       target_id = COALESCE(?, target_id)
                   WHERE id = ?""",
                (count, now, new_username, new_id, row["id"]),
            )
            return count

        safe_username = username
        safe_id = user_id
        if safe_username and _stats_row_by_username(conn, safe_username):
            safe_username = None
        if safe_id and _stats_row_by_id(conn, safe_id):
            safe_id = None
        if not safe_username and not safe_id:
            return get_target_search_count(username, user_id)

        try:
            conn.execute(
                """INSERT INTO target_stats
                   (target_username, target_id, search_count, last_checked)
                   VALUES (?, ?, 1, ?)""",
                (safe_username, safe_id, now),
            )
            return 1
        except sqlite3.IntegrityError:
            row = (by_name or by_id) or (
                _stats_row_by_username(conn, username) if username else None
            ) or (
                _stats_row_by_id(conn, user_id) if user_id else None
            )
            if not row:
                return 0
            count = int(row["search_count"]) + 1
            conn.execute(
                "UPDATE target_stats SET search_count = ?, last_checked = ? WHERE id = ?",
                (count, now, row["id"]),
            )
            return count


def get_target_search_count(username: str | None, user_id: int | None) -> int:
    with get_db() as conn:
        if username:
            row = conn.execute(
                "SELECT search_count FROM target_stats WHERE target_username = ? COLLATE NOCASE",
                (username.lower(),),
            ).fetchone()
            if row:
                return int(row["search_count"])
        if user_id:
            row = conn.execute(
                "SELECT search_count FROM target_stats WHERE target_id = ?",
                (user_id,),
            ).fetchone()
            if row:
                return int(row["search_count"])
    return 0


def log_check(checker_id: int, username: str | None, user_id: int | None, found: bool):
    increment_target_search(username, user_id)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO check_log
               (checker_id, target_username, target_id, found, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (checker_id, username, user_id, int(found), _now()),
        )


def log_admin(admin_id: int, action: str, details: str = ""):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO admin_logs (admin_id, action, details, created_at)
               VALUES (?, ?, ?, ?)""",
            (admin_id, action, details[:500], _now()),
        )


def get_stats() -> dict[str, int]:
    month = _month_start()
    with get_db() as conn:
        blacklist_count = conn.execute("SELECT COUNT(*) AS c FROM blacklist").fetchone()["c"]
        checks_month = conn.execute(
            "SELECT COUNT(*) AS c FROM check_log WHERE created_at >= ?",
            (month,),
        ).fetchone()["c"]
        checks_total = conn.execute("SELECT COUNT(*) AS c FROM check_log").fetchone()["c"]
        complaints_pending = conn.execute(
            "SELECT COUNT(*) AS c FROM complaints WHERE status = ?",
            (COMPLAINT_PENDING,),
        ).fetchone()["c"]
        complaints_total = conn.execute("SELECT COUNT(*) AS c FROM complaints").fetchone()["c"]
    return {
        "total_users": get_total_users(),
        "blacklist_count": int(blacklist_count),
        "checks_month": int(checks_month),
        "checks_total": int(checks_total),
        "complaints_pending": int(complaints_pending),
        "complaints_total": int(complaints_total),
    }


def create_complaint(
    reporter_id: int,
    reporter_username: str | None,
    target_username: str | None,
    target_id: int | None,
    description: str,
) -> int:
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO complaints
               (reporter_id, reporter_username, target_username, target_id,
                description, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                reporter_id,
                reporter_username,
                target_username,
                target_id,
                description or "",
                COMPLAINT_PENDING,
                _now(),
            ),
        )
        return int(cur.lastrowid)


def get_complaint(complaint_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return dict(row) if row else None


def list_complaints(
    status: str | None = COMPLAINT_PENDING,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    with get_db() as conn:
        if status:
            rows = conn.execute(
                """SELECT * FROM complaints
                   WHERE status = ?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM complaints ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]


def count_complaints(status: str | None = COMPLAINT_PENDING) -> int:
    with get_db() as conn:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM complaints WHERE status = ?",
                (status,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS c FROM complaints").fetchone()
        return int(row["c"]) if row else 0


def set_complaint_status(complaint_id: int, status: str, reviewed_by: int) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            """UPDATE complaints
               SET status = ?, reviewed_by = ?, reviewed_at = ?
               WHERE id = ?""",
            (status, reviewed_by, _now(), complaint_id),
        )
        return cur.rowcount > 0


def get_all_user_ids() -> list[int]:
    with get_db() as conn:
        rows = conn.execute("SELECT telegram_id FROM bot_users").fetchall()
        return [int(r["telegram_id"]) for r in rows]


def log_broadcast(admin_id: int, message: str, sent: int, failed: int):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO broadcast_log
               (admin_id, message, sent_count, failed_count, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (admin_id, message[:2000], sent, failed, _now()),
        )


def clear_blacklist() -> int:
    with get_db() as conn:
        cur = conn.execute("DELETE FROM blacklist")
        return cur.rowcount


def count_catalog_garants() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM catalog_garants").fetchone()
        return int(row["c"]) if row else 0


def count_catalog_admins() -> int:
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM catalog_admins").fetchone()
        return int(row["c"]) if row else 0


def replace_catalog_garants(entries: list[dict]) -> int:
    with get_db() as conn:
        preserved: dict[str, dict[str, object]] = {}
        for row in conn.execute(
            "SELECT username, telegram_id, photo_file FROM catalog_garants"
        ).fetchall():
            key = _norm_username(row["username"])
            if not key:
                continue
            preserved[key] = {
                "telegram_id": row["telegram_id"],
                "photo_file": row["photo_file"],
            }

        conn.execute("DELETE FROM catalog_garants")
        for i, e in enumerate(entries):
            username = e.get("username", "")
            if not username.startswith("@"):
                username = f"@{username}"
            handlers = _serialize_handlers(e)
            keep = preserved.get(_norm_username(username), {})
            telegram_id = e.get("telegram_id") or keep.get("telegram_id")
            photo_file = e.get("photo_file") or keep.get("photo_file")
            conn.execute(
                """INSERT INTO catalog_garants
                   (flag, username, proofs, channel, rating, deal_price, handler, handlers,
                    subgroup, tier, role_label, rating_votes, deals_count,
                    senior_admin, scammers_added, warns, photo_file, telegram_id, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    e.get("flag", "🇷🇺"),
                    username,
                    e.get("proofs", "0+"),
                    e.get("channel"),
                    e.get("rating", "5.0/5"),
                    e.get("deal_price", "0₽"),
                    e.get("handler") or (e.get("handlers") or [None])[0],
                    handlers,
                    e.get("subgroup", "Элитные гаранты"),
                    e.get("tier", "elite"),
                    e.get("role_label"),
                    e.get("rating_votes", 0),
                    e.get("deals_count"),
                    e.get("senior_admin"),
                    e.get("scammers_added"),
                    e.get("warns"),
                    photo_file,
                    telegram_id,
                    i,
                ),
            )
        return len(entries)


def replace_catalog_admins(entries: list[dict]) -> int:
    with get_db() as conn:
        conn.execute("DELETE FROM catalog_admins")
        for i, e in enumerate(entries):
            username = e.get("username", "")
            if not username.startswith("@"):
                username = f"@{username}"
            conn.execute(
                """INSERT INTO catalog_admins
                   (username, channel, is_main, scammers_count, sort_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    username,
                    e.get("channel"),
                    1 if e.get("main") else 0,
                    e.get("scammers_count"),
                    i,
                ),
            )
        return len(entries)


def append_catalog_garant(entry: dict) -> bool:
    username = entry.get("username", "")
    if not username:
        return False
    if not username.startswith("@"):
        username = f"@{username}"
    handlers = _serialize_handlers(entry)
    try:
        with get_db() as conn:
            row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) AS m FROM catalog_garants").fetchone()
            order = int(row["m"]) + 1 if row else 0
            conn.execute(
                """INSERT INTO catalog_garants
                   (flag, username, proofs, channel, rating, deal_price, handler, handlers,
                    subgroup, tier, role_label, rating_votes, deals_count,
                    senior_admin, scammers_added, warns, photo_file, profile_text,
                    telegram_id, sort_order)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.get("flag", "🇷🇺"),
                    username,
                    entry.get("proofs", "0+"),
                    entry.get("channel"),
                    entry.get("rating", "5.0/5"),
                    entry.get("deal_price", "0"),
                    entry.get("handler") or (entry.get("handlers") or [None])[0],
                    handlers,
                    entry.get("subgroup", "Гаранты"),
                    entry.get("tier", "regular"),
                    entry.get("role_label", "Гарант"),
                    entry.get("rating_votes", 0),
                    entry.get("deals_count"),
                    entry.get("senior_admin"),
                    entry.get("scammers_added"),
                    entry.get("warns"),
                    entry.get("photo_file"),
                    entry.get("profile_text"),
                    entry.get("telegram_id"),
                    order,
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def count_garants_by_tier(tier: str) -> int:
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM catalog_garants WHERE tier = ?",
            (tier,),
        ).fetchone()
        return int(row["c"]) if row else 0


def list_garants_by_tier(tier: str, *, limit: int = 10, offset: int = 0) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM catalog_garants WHERE tier = ? ORDER BY sort_order, id LIMIT ? OFFSET ?",
            (tier, limit, offset),
        ).fetchall()
        return [_garant_row_to_dict(r) for r in rows]


def get_catalog_garants() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM catalog_garants ORDER BY sort_order, id"
        ).fetchall()
        return [_garant_row_to_dict(r) for r in rows]


def find_catalog_garant(username: str | None) -> dict | None:
    if not username:
        return None
    uname = username.lstrip("@").lower()
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM catalog_garants WHERE LOWER(REPLACE(username, '@', '')) = ?",
            (uname,),
        ).fetchone()
        return _garant_row_to_dict(row) if row else None


def get_catalog_admins() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM catalog_admins ORDER BY sort_order, id"
        ).fetchall()
        return [
            {
                "username": r["username"],
                "channel": r["channel"],
                "main": bool(r["is_main"]),
                "scammers_count": r["scammers_count"],
            }
            for r in rows
        ]