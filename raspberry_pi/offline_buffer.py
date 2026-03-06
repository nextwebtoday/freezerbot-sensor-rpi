"""
Offline buffer for temperature readings using SQLite.

When the API is unreachable due to connectivity failures, readings are stored
locally and sent as a batch once connectivity is restored.
"""
import json
import os
import sqlite3
from datetime import datetime

DB_PATH = '/home/pi/.config/freezerbot/readings_buffer.db'


class OfflineBuffer:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _ensure_db(self):
        """Create the database and table if they don't exist."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payload_json TEXT NOT NULL,
                    taken_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def add_reading(self, payload: dict, timestamp: str) -> None:
        """Store a reading with its original timestamp."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO readings (payload_json, taken_at) VALUES (?, ?)",
                (json.dumps(payload), timestamp),
            )

    def get_buffered_readings(self) -> list:
        """Return all buffered readings in FIFO order."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, payload_json, taken_at FROM readings ORDER BY id ASC"
            ).fetchall()
        return [
            {'id': row[0], 'payload': json.loads(row[1]), 'taken_at': row[2]}
            for row in rows
        ]

    def clear_buffer(self) -> None:
        """Delete all readings after a successful batch send."""
        with self._connect() as conn:
            conn.execute("DELETE FROM readings")

    def prune_to_limit(self, limit: int = 1440) -> None:
        """Drop oldest readings when buffer exceeds the given limit (24h cap at 1/min)."""
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
            excess = count - limit
            if excess > 0:
                conn.execute("""
                    DELETE FROM readings WHERE id IN (
                        SELECT id FROM readings ORDER BY id ASC LIMIT ?
                    )
                """, (excess,))

    def count(self) -> int:
        """Return the number of buffered readings."""
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
