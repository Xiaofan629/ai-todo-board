import aiosqlite
import os
from datetime import datetime
from config import DB_PATH

# Map internal DB statuses to frontend statuses
# DB stores: pending, doing, completed, failed
# Frontend shows: pending, doing, done
_STATUS_MAP = {
    "pending": "pending",
    "doing": "doing",
    "completed": "done",
    "failed": "done",
}


def _map_todo(t: dict) -> dict:
    t["status"] = _STATUS_MAP.get(t["status"], t["status"])
    t["is_processing"] = bool(t.get("is_processing", 0))
    return t


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            userid TEXT DEFAULT '',
            chatid TEXT DEFAULT '',
            chattype TEXT DEFAULT 'single',
            claude_session_id TEXT DEFAULT '',
            is_processing INTEGER NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            todo_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT DEFAULT '',
            tool_name TEXT DEFAULT '',
            tool_input TEXT DEFAULT '',
            event_type TEXT DEFAULT '',
            event_subtype TEXT DEFAULT '',
            payload TEXT DEFAULT '',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (todo_id) REFERENCES todos(id)
        );
    """)
    await _ensure_column(db, "todos", "claude_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "todos", "is_processing", "INTEGER NOT NULL DEFAULT 0")
    await _ensure_column(db, "messages", "event_type", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "event_subtype", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "payload", "TEXT DEFAULT ''")
    await db.commit()
    await db.close()


async def _ensure_column(db, table: str, column: str, definition: str):
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in rows}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def _rebalance_open_todos(db) -> dict[int, str]:
    now = datetime.now().isoformat()
    rows = await db.execute_fetchall(
        "SELECT id FROM todos WHERE status != 'completed' ORDER BY created_at ASC, id ASC"
    )
    status_map: dict[int, str] = {}
    updates: list[tuple[str, str, int]] = []
    for index, row in enumerate(rows):
        status = "doing" if index == 0 else "pending"
        status_map[row["id"]] = status
        updates.append((status, now, row["id"]))

    if updates:
        await db.executemany(
            "UPDATE todos SET status = ?, updated_at = ? WHERE id = ?",
            updates,
        )
    return status_map


async def create_todo(title: str, content: str, userid: str = "",
                      chatid: str = "", chattype: str = "single") -> dict:
    db = await get_db()
    now = datetime.now().isoformat()
    cursor = await db.execute(
        "INSERT INTO todos (title, content, userid, chatid, chattype, claude_session_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (title, content, userid, chatid, chattype, "", now, now)
    )
    todo_id = cursor.lastrowid
    status_map = await _rebalance_open_todos(db)
    await db.commit()
    await db.close()
    return _map_todo({"id": todo_id, "title": title, "content": content,
            "status": status_map.get(todo_id, "pending"),
            "userid": userid, "chatid": chatid, "chattype": chattype,
            "claude_session_id": "", "is_processing": False,
            "created_at": now, "updated_at": now})


async def get_todos(status: str = None) -> list:
    db = await get_db()
    if status:
        # Support comma-separated statuses for frontend filter mapping
        statuses = [s.strip() for s in status.split(",")]
        if len(statuses) == 1:
            rows = await db.execute_fetchall(
                "SELECT * FROM todos WHERE status = ? ORDER BY created_at ASC",
                (statuses[0],))
        else:
            placeholders = ",".join("?" for _ in statuses)
            rows = await db.execute_fetchall(
                f"SELECT * FROM todos WHERE status IN ({placeholders}) ORDER BY created_at ASC",
                statuses)
    else:
        rows = await db.execute_fetchall("SELECT * FROM todos ORDER BY created_at ASC")
    await db.close()
    return [_map_todo(dict(r)) for r in rows]


async def get_todo(todo_id: int) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM todos WHERE id = ?", (todo_id,))
    await db.close()
    return _map_todo(dict(rows[0])) if rows else None


async def update_todo_status(todo_id: int, status: str):
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute("UPDATE todos SET status = ?, updated_at = ? WHERE id = ?",
                     (status, now, todo_id))
    await db.commit()
    await db.close()


async def sync_todo_queue(todo_id: int | None = None) -> str | None:
    db = await get_db()
    status_map = await _rebalance_open_todos(db)
    await db.commit()
    await db.close()
    if todo_id is None:
        return None
    return status_map.get(todo_id)


async def set_todo_claude_session_id(todo_id: int, session_id: str):
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute(
        "UPDATE todos SET claude_session_id = ?, updated_at = ? WHERE id = ?",
        (session_id, now, todo_id),
    )
    await db.commit()
    await db.close()


async def set_todo_processing(todo_id: int, is_processing: bool):
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute(
        "UPDATE todos SET is_processing = ?, updated_at = ? WHERE id = ?",
        (1 if is_processing else 0, now, todo_id),
    )
    await db.commit()
    await db.close()


async def complete_todo(todo_id: int) -> int | None:
    """Mark a todo as completed and auto-promote the next pending todo to doing.
    Returns the id of the newly promoted todo, or None."""
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute("UPDATE todos SET status = 'completed', updated_at = ? WHERE id = ?",
                     (now, todo_id))
    status_map = await _rebalance_open_todos(db)
    await db.commit()
    await db.close()
    next_id = next((tid for tid, status in status_map.items() if status == "doing"), None)
    return next_id


async def add_message(todo_id: int, role: str, content: str,
                      tool_name: str = "", tool_input: str = "",
                      event_type: str = "", event_subtype: str = "",
                      payload: str = "") -> dict:
    db = await get_db()
    now = datetime.now().isoformat()
    cursor = await db.execute(
        "INSERT INTO messages (todo_id, role, content, tool_name, tool_input, event_type, event_subtype, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (todo_id, role, content, tool_name, tool_input, event_type, event_subtype, payload, now)
    )
    msg_id = cursor.lastrowid
    await db.commit()
    await db.close()
    return {"id": msg_id, "todo_id": todo_id, "role": role, "content": content,
            "tool_name": tool_name, "tool_input": tool_input,
            "event_type": event_type, "event_subtype": event_subtype,
            "payload": payload, "created_at": now}


async def get_messages(todo_id: int) -> list:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM messages WHERE todo_id = ? ORDER BY created_at ASC", (todo_id,))
    await db.close()
    return [dict(r) for r in rows]


async def get_stats() -> dict:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT status, COUNT(*) as count FROM todos GROUP BY status")
    await db.close()
    stats = {"pending": 0, "doing": 0, "done": 0}
    for r in rows:
        mapped = _STATUS_MAP.get(r["status"], r["status"])
        if mapped in stats:
            stats[mapped] += r["count"]
    return stats
