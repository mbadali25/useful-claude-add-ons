# pylint: disable=logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""SQLite message store of the Bridge: history and offline delivery."""

import json
import logging
import os
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from bridge_time import bridge_timestamp

logger = logging.getLogger(__name__)

StoredCallback = Callable[[dict], Awaitable[None]]
DEFAULT_DB_PATH = "~/.config/ai-connect/messages.db"

_COLUMNS = "id, from_peer, to_peer, content, context, timestamp"


def _create_owner_only(path: Path) -> None:
    """Create the database file readable by its owner only, and tighten an old one.

    On Windows chmod only sets the read-only flag; there the file keeps the
    ACL of its directory (the user profile), which is the best effort.
    """
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists():
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
    try:
        os.chmod(path, 0o600)
    except OSError as error:
        logger.warning(f"Could not restrict {path} to its owner: {error}")


def _row_to_message(row: sqlite3.Row) -> dict:
    return {
        "id": row[0],
        "from": row[1],
        "to": row[2],
        "content": row[3],
        "context": json.loads(row[4]) if row[4] else None,
        "timestamp": row[5]
    }


class MessageStore:
    """Stores every message; direct messages to offline peers wait here."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH, max_stored_per_peer: int = 0):
        self.db_path = Path(db_path).expanduser()
        # Per sender; beyond it the sender's oldest messages go. 0 = no cap
        self.max_stored_per_peer = max_stored_per_peer
        self._db: aiosqlite.Connection | None = None
        self._on_stored: StoredCallback | None = None

    def on_stored(self, callback: StoredCallback) -> None:
        """Call back with every message once it is stored (the observers' feed)."""
        self._on_stored = callback

    async def connect(self) -> None:
        """Open the database and create the table."""
        _create_owner_only(self.db_path)
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                from_peer TEXT NOT NULL,
                to_peer TEXT NOT NULL,
                content TEXT NOT NULL,
                context TEXT,
                timestamp TEXT NOT NULL,
                delivered INTEGER DEFAULT 0
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_to_peer ON messages(to_peer, delivered)
        """)
        await self._db.execute("CREATE INDEX IF NOT EXISTS idx_from_peer ON messages(from_peer)")
        await self._db.commit()

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("MessageStore not connected, call connect() first")
        return self._db

    async def close(self) -> None:
        """Close the database."""
        if self._db:
            await self._db.close()
            self._db = None

    async def store(
        self,
        from_peer: str,
        to_peer: str,
        content: str,
        context: dict | None,
        delivered: bool
    ) -> dict:
        """Store a message and return it as sent to peers."""
        msg_id = str(uuid.uuid4())
        timestamp = bridge_timestamp(datetime.now(timezone.utc))
        context_json = json.dumps(context) if context else None

        await self._conn.execute(
            """
            INSERT INTO messages (id, from_peer, to_peer, content, context, timestamp, delivered)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (msg_id, from_peer, to_peer, content, context_json, timestamp, int(delivered))
        )
        await self._enforce_cap(from_peer)
        await self._conn.commit()
        message = {
            "id": msg_id,
            "from": from_peer,
            "to": to_peer,
            "content": content,
            "context": context,
            "timestamp": timestamp
        }
        if self._on_stored:
            await self._on_stored(message)
        return message

    async def _enforce_cap(self, from_peer: str) -> None:
        """Delete the sender's oldest messages beyond max_stored_per_peer."""
        if not self.max_stored_per_peer:
            return
        cursor = await self._conn.execute(
            """
            DELETE FROM messages WHERE from_peer = ? AND rowid NOT IN (
                SELECT rowid FROM messages WHERE from_peer = ? ORDER BY rowid DESC LIMIT ?
            )
            """,
            (from_peer, from_peer, self.max_stored_per_peer)
        )
        if cursor.rowcount > 0:
            logger.warning(json.dumps({
                "event": "store_cap", "peer": from_peer, "deleted": cursor.rowcount,
                "cap": self.max_stored_per_peer,
            }))

    async def get_unread(self, peer: str) -> list[dict]:
        """Direct messages to this peer that have not been delivered yet."""
        cursor = await self._conn.execute(
            f"""
            SELECT {_COLUMNS}
            FROM messages
            WHERE to_peer = ? AND delivered = 0
            ORDER BY timestamp ASC
            """,
            (peer,)
        )
        return [_row_to_message(row) for row in await cursor.fetchall()]

    async def mark_delivered(self, message_ids: list[str]) -> None:
        """Mark messages as delivered."""
        if not message_ids:
            return
        placeholders = ",".join("?" * len(message_ids))
        await self._conn.execute(
            f"UPDATE messages SET delivered = 1 WHERE id IN ({placeholders})",
            message_ids
        )
        await self._conn.commit()

    async def delete_older_than(self, days: int) -> int:
        """Delete messages older than days; return how many."""
        # Compare the date only: older rows use "YYYY-MM-DD HH:MM:SS",
        # newer ones ISO with "T" and "Z"
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        cursor = await self._conn.execute(
            "DELETE FROM messages WHERE substr(timestamp, 1, 10) < ?", (cutoff,)
        )
        await self._conn.commit()
        return cursor.rowcount

    async def latest_to_since(self, peer: str, since: str) -> dict | None:
        """The newest message to peer (or to everyone, from someone else) after since."""
        cursor = await self._conn.execute(
            f"""
            SELECT {_COLUMNS}
            FROM messages
            WHERE (to_peer = ? OR (to_peer = '*' AND from_peer != ?)) AND timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (peer, peer, since)
        )
        row = await cursor.fetchone()
        return _row_to_message(row) if row else None

    async def get_history(
        self,
        peer1: str,
        peer2: str,
        limit: int = 50
    ) -> list[dict]:
        """The latest messages between two peers, oldest first."""
        cursor = await self._conn.execute(
            f"""
            SELECT * FROM (
                SELECT {_COLUMNS}
                FROM messages
                WHERE (from_peer = ? AND to_peer = ?)
                   OR (from_peer = ? AND to_peer = ?)
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp
            """,
            (peer1, peer2, peer2, peer1, limit)
        )
        return [_row_to_message(row) for row in await cursor.fetchall()]

    async def history_all(self, since: str, before: str | None, limit: int) -> list[dict]:
        """The latest messages between any peers after since, oldest first.

        before (exclusive) pages further back: pass the timestamp of the
        oldest message of the previous page.
        """
        cursor = await self._conn.execute(
            f"""
            SELECT * FROM (
                SELECT {_COLUMNS}
                FROM messages
                WHERE timestamp > ? AND (? IS NULL OR timestamp < ?)
                ORDER BY timestamp DESC
                LIMIT ?
            )
            ORDER BY timestamp
            """,
            (since, before, before, limit)
        )
        return [_row_to_message(row) for row in await cursor.fetchall()]
