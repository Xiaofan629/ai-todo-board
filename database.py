import aiosqlite
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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
    t["sort_order"] = t.get("sort_order", 0)
    t["reorder_reason"] = t.get("reorder_reason", "")
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
        CREATE TABLE IF NOT EXISTS time_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            todo_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'doing',
            started_at DATETIME NOT NULL,
            ended_at DATETIME,
            FOREIGN KEY (todo_id) REFERENCES todos(id)
        );
    """)
    await _ensure_column(db, "todos", "claude_session_id", "TEXT DEFAULT ''")
    await _ensure_column(db, "todos", "is_processing", "INTEGER NOT NULL DEFAULT 0")
    await _ensure_column(db, "todos", "sort_order", "INTEGER DEFAULT 0")
    await _ensure_column(db, "todos", "reorder_reason", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "event_type", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "event_subtype", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "payload", "TEXT DEFAULT ''")
    await _ensure_column(db, "messages", "platform_msg_id", "TEXT DEFAULT ''")
    await db.commit()
    await db.close()


async def start_time_segment(todo_id: int):
    """Record the start of a 'doing' segment for a todo."""
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute(
        "INSERT INTO time_segments (todo_id, status, started_at) VALUES (?, 'doing', ?)",
        (todo_id, now),
    )
    await db.commit()
    await db.close()


async def end_time_segment(todo_id: int):
    """Close any open (ended_at IS NULL) segment for a todo."""
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute(
        "UPDATE time_segments SET ended_at = ? WHERE todo_id = ? AND ended_at IS NULL",
        (now, todo_id),
    )
    await db.commit()
    await db.close()


async def get_time_segments(todo_id: int) -> list:
    """Return all time segments for a todo, ordered by started_at."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM time_segments WHERE todo_id = ? ORDER BY started_at ASC",
        (todo_id,),
    )
    await db.close()
    return [dict(r) for r in rows]


async def get_all_time_segments(todo_ids: list) -> dict:
    """Return time segments for multiple todos. Returns {todo_id: [segments]}."""
    if not todo_ids:
        return {}
    db = await get_db()
    placeholders = ",".join("?" for _ in todo_ids)
    rows = await db.execute_fetchall(
        f"SELECT * FROM time_segments WHERE todo_id IN ({placeholders}) ORDER BY started_at ASC",
        todo_ids,
    )
    await db.close()
    result: Dict[int, list] = {}
    for r in rows:
        tid = r["todo_id"]
        result.setdefault(tid, []).append(dict(r))
    return result


async def _ensure_column(db, table: str, column: str, definition: str):
    rows = await db.execute_fetchall(f"PRAGMA table_info({table})")
    existing = {row["name"] for row in rows}
    if column not in existing:
        await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


async def _rebalance_open_todos(db) -> Dict[int, str]:
    """Ensure the first non-completed todo (by sort_order) is 'doing', rest are 'pending'.
    Also tracks time_segments when status changes."""
    now = datetime.now().isoformat()
    rows = await db.execute_fetchall(
        "SELECT id, status FROM todos WHERE status != 'completed' AND status != 'failed' "
        "ORDER BY sort_order ASC, created_at ASC, id ASC"
    )
    status_map: Dict[int, str] = {}
    updates: List[Tuple[str, str, int]] = []
    segments_to_close: List[int] = []
    segments_to_start: List[int] = []

    for index, row in enumerate(rows):
        new_status = "doing" if index == 0 else "pending"
        old_status = row["status"]
        status_map[row["id"]] = new_status
        updates.append((new_status, now, row["id"]))

        if old_status != new_status:
            if old_status == "doing":
                segments_to_close.append(row["id"])
            if new_status == "doing":
                segments_to_start.append(row["id"])

    if updates:
        await db.executemany(
            "UPDATE todos SET status = ?, updated_at = ? WHERE id = ?",
            updates,
        )

    # Close/open time segments within the same transaction
    for tid in segments_to_close:
        await db.execute(
            "UPDATE time_segments SET ended_at = ? WHERE todo_id = ? AND ended_at IS NULL",
            (now, tid),
        )
    for tid in segments_to_start:
        await db.execute(
            "INSERT INTO time_segments (todo_id, status, started_at) VALUES (?, 'doing', ?)",
            (tid, now),
        )

    return status_map


async def create_todo(title: str, content: str, userid: str = "",
                      chatid: str = "", chattype: str = "single") -> dict:
    db = await get_db()
    now = datetime.now().isoformat()
    # Place the new todo at the end of the open queue
    max_row = await db.execute_fetchall(
        "SELECT MAX(sort_order) as max_so FROM todos "
        "WHERE status != 'completed' AND status != 'failed'"
    )
    max_so = max_row[0]["max_so"] if max_row and max_row[0]["max_so"] is not None else -1000
    sort_order = max_so + 1000
    cursor = await db.execute(
        "INSERT INTO todos (title, content, userid, chatid, chattype, claude_session_id, sort_order, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (title, content, userid, chatid, chattype, "", sort_order, now, now)
    )
    todo_id = cursor.lastrowid
    status_map = await _rebalance_open_todos(db)
    await db.commit()
    await db.close()
    return _map_todo({"id": todo_id, "title": title, "content": content,
            "status": status_map.get(todo_id, "pending"),
            "userid": userid, "chatid": chatid, "chattype": chattype,
            "claude_session_id": "", "is_processing": False, "sort_order": sort_order,
            "created_at": now, "updated_at": now})


async def get_todos(status: str = None) -> list:
    db = await get_db()
    if status:
        # Support comma-separated statuses for frontend filter mapping
        statuses = [s.strip() for s in status.split(",")]
        if len(statuses) == 1:
            rows = await db.execute_fetchall(
                "SELECT * FROM todos WHERE status = ? ORDER BY sort_order ASC, created_at ASC",
                (statuses[0],))
        else:
            placeholders = ",".join("?" for _ in statuses)
            rows = await db.execute_fetchall(
                f"SELECT * FROM todos WHERE status IN ({placeholders}) ORDER BY sort_order ASC, created_at ASC",
                statuses)
    else:
        rows = await db.execute_fetchall("SELECT * FROM todos ORDER BY sort_order ASC, created_at ASC")
    await db.close()
    return [_map_todo(dict(r)) for r in rows]


async def get_todo(todo_id: int) -> Optional[dict]:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM todos WHERE id = ?", (todo_id,))
    await db.close()
    return _map_todo(dict(rows[0])) if rows else None


async def find_recent_active_todo(chatid: str) -> Optional[dict]:
    """Find the most recent non-completed todo for a given chat_id."""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM todos WHERE chatid = ? AND status != 'done' "
        "ORDER BY created_at DESC LIMIT 1",
        (chatid,),
    )
    await db.close()
    return _map_todo(dict(rows[0])) if rows else None


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting for fuzzy text comparison."""
    import re
    # Remove bold/italic markers
    text = re.sub(r'\*{1,3}', '', text)
    # Remove heading markers
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # Remove link syntax, keep text
    text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


async def find_todo_by_quoted_content(chatid: str, quoted_content: str) -> Optional[dict]:
    """Find an active todo whose messages contain the quoted bot reply text.
    Strips markdown before comparing since platforms (e.g. WeCom) strip it when quoting."""
    if not quoted_content:
        return None
    import logging
    _logger = logging.getLogger("database")
    db = await get_db()

    # Fetch all active assistant messages for this chatid
    all_msgs = await db.execute_fetchall(
        "SELECT m.todo_id, m.content FROM messages m "
        "JOIN todos t ON t.id = m.todo_id "
        "WHERE m.role = 'assistant' AND t.chatid = ? "
        "AND t.status NOT IN ('completed', 'failed') "
        "ORDER BY m.created_at DESC",
        (chatid,),
    )
    await db.close()

    # Match by stripping markdown from both sides
    stripped_quote = _strip_markdown(quoted_content)
    # Use a 30-char prefix of stripped content for matching
    match_prefix = stripped_quote[:30]

    for r in all_msgs:
        stripped_msg = _strip_markdown(r["content"] or "")
        if match_prefix and match_prefix in stripped_msg:
            _logger.info("Matched todo_id=%s by quoted content", r["todo_id"])
            return await get_todo(r["todo_id"])

    _logger.info("No match found for quoted content (prefix=%r)", match_prefix)
    return None


async def set_last_assistant_platform_msg_id(todo_id: int, platform_msg_id: str):
    """Update the most recent assistant message with the platform message ID."""
    if not platform_msg_id:
        return
    db = await get_db()
    await db.execute(
        "UPDATE messages SET platform_msg_id = ? "
        "WHERE id = (SELECT id FROM messages WHERE todo_id = ? AND role = 'assistant' "
        "ORDER BY created_at DESC LIMIT 1)",
        (platform_msg_id, todo_id),
    )
    await db.commit()
    await db.close()


async def find_todo_by_platform_msg_id(platform_msg_id: str) -> Optional[dict]:
    """Find an active todo by a platform message ID stored on one of its messages."""
    if not platform_msg_id:
        return None
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT DISTINCT m.todo_id FROM messages m "
        "JOIN todos t ON t.id = m.todo_id "
        "WHERE m.platform_msg_id = ? "
        "AND t.status NOT IN ('completed', 'failed') "
        "LIMIT 1",
        (platform_msg_id,),
    )
    await db.close()
    if not rows:
        return None
    return await get_todo(rows[0]["todo_id"])


async def delete_todo(todo_id: int):
    """Delete a todo and its messages permanently."""
    db = await get_db()
    await db.execute("DELETE FROM messages WHERE todo_id = ?", (todo_id,))
    await db.execute("DELETE FROM time_segments WHERE todo_id = ?", (todo_id,))
    await db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    await db.commit()
    await db.close()


async def update_todo_title(todo_id: int, title: str):
    db = await get_db()
    now = datetime.now().isoformat()
    await db.execute("UPDATE todos SET title = ?, updated_at = ? WHERE id = ?",
                     (title[:100], now, todo_id))
    await db.commit()
    await db.close()


async def sync_todo_queue(todo_id: Optional[int] = None) -> Optional[str]:
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


async def complete_todo(todo_id: int) -> Optional[int]:
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


async def complete_from_pending(todo_id: int) -> Optional[int]:
    """Mark a pending todo as completed with timing logic.
    Uses last 'doing' segment end time or created_at as start.
    Returns the id of the newly promoted todo, or None."""
    db = await get_db()
    now = datetime.now().isoformat()

    # Find the most recent closed segment for this todo
    last_segment = await db.execute_fetchall(
        "SELECT ended_at FROM time_segments WHERE todo_id = ? AND ended_at IS NOT NULL "
        "ORDER BY ended_at DESC LIMIT 1",
        (todo_id,),
    )

    # Close any open segment
    await db.execute(
        "UPDATE time_segments SET ended_at = ? WHERE todo_id = ? AND ended_at IS NULL",
        (now, todo_id),
    )

    # Determine started_at for the completion segment
    if last_segment:
        started_at = last_segment[0]["ended_at"]
    else:
        todo = await db.execute_fetchall("SELECT created_at FROM todos WHERE id = ?", (todo_id,))
        started_at = todo[0]["created_at"] if todo else now

    # Insert a completion segment
    await db.execute(
        "INSERT INTO time_segments (todo_id, status, started_at, ended_at) VALUES (?, 'completed', ?, ?)",
        (todo_id, started_at, now),
    )

    # Mark todo as completed
    await db.execute("UPDATE todos SET status = 'completed', updated_at = ? WHERE id = ?", (now, todo_id))

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


async def reorder_todo(todo_id: int, reason: str = "", promote_to_doing: bool = False,
                       target_index: Optional[int] = None, target_todo_id: Optional[int] = None,
                       position: str = "bottom") -> bool:
    """Move a todo to a new position and rewrite the open queue order deterministically."""
    db = await get_db()
    now = datetime.now().isoformat()

    todo = await db.execute_fetchall("SELECT id, status FROM todos WHERE id = ?", (todo_id,))
    if not todo:
        await db.close()
        return False

    all_rows = await db.execute_fetchall(
        "SELECT id FROM todos WHERE status != 'completed' AND status != 'failed' "
        "ORDER BY sort_order ASC, created_at ASC, id ASC"
    )
    current_ids = [row["id"] for row in all_rows]
    if todo_id not in current_ids:
        await db.close()
        return False

    next_ids = [current_id for current_id in current_ids if current_id != todo_id]

    if target_todo_id is not None:
        if target_todo_id == todo_id:
            await db.close()
            return True
        if target_todo_id not in next_ids:
            await db.close()
            return False
        anchor_index = next_ids.index(target_todo_id)
        insert_at = anchor_index if position == "top" else anchor_index + 1
    else:
        if target_index is None:
            await db.close()
            return False
        insert_at = max(0, min(target_index, len(next_ids)))

    next_ids.insert(insert_at, todo_id)

    if next_ids != current_ids:
        await db.executemany(
            "UPDATE todos SET sort_order = ?, updated_at = ? WHERE id = ?",
            [(index * 1000, now, current_id) for index, current_id in enumerate(next_ids)],
        )

    await db.execute(
        "UPDATE todos SET reorder_reason = ?, updated_at = ? WHERE id = ?",
        (reason.strip(), now, todo_id),
    )

    await _rebalance_open_todos(db)
    await db.commit()
    await db.close()
    return True
