"""
database.py — SQLite store for admin-scheduled feed posts.
"""
import sqlite3
import os
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "feeds.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create and migrate the feeds and graduates tables if they don't exist."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_feeds (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                message  TEXT    NOT NULL,
                post_at  TEXT,               -- ISO 8601 datetime string for one-time
                posted   INTEGER NOT NULL DEFAULT 0,
                is_recurring     INTEGER NOT NULL DEFAULT 0,
                recurrence_days  TEXT,       -- e.g. "mon,wed,fri"
                recurrence_time  TEXT,       -- e.g. "10:00"
                last_posted_at   TEXT        -- e.g. "2026-06-15" (prevents double posts)
            )
        """)
        
        # Safe migration if columns are missing from existing DB
        try:
            conn.execute("ALTER TABLE scheduled_feeds ADD COLUMN is_recurring INTEGER NOT NULL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE scheduled_feeds ADD COLUMN recurrence_days TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE scheduled_feeds ADD COLUMN recurrence_time TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE scheduled_feeds ADD COLUMN last_posted_at TEXT")
        except sqlite3.OperationalError:
            pass

        # Table to track already announced graduates
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_graduates (
                email        TEXT,
                course       TEXT,
                processed_at TEXT NOT NULL,
                PRIMARY KEY (email, course)
            )
        """)
        conn.commit()


def add_feed(
    message: str, 
    post_at: Optional[datetime] = None, 
    is_recurring: int = 0, 
    recurrence_days: Optional[str] = None, 
    recurrence_time: Optional[str] = None
) -> int:
    """Insert a new scheduled feed (either one-time or recurring). Returns the new feed ID."""
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO scheduled_feeds 
            (message, post_at, is_recurring, recurrence_days, recurrence_time) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                message,
                post_at.isoformat() if post_at else None,
                is_recurring,
                recurrence_days,
                recurrence_time
            ),
        )
        conn.commit()
        return cur.lastrowid


def get_pending_feeds(as_of: Optional[datetime] = None) -> list[sqlite3.Row]:
    """Return all pending one-time feeds whose post_at <= now."""
    if as_of is None:
        as_of = datetime.now(timezone.utc).replace(tzinfo=None)
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_feeds WHERE is_recurring=0 AND posted=0 AND post_at <= ? ORDER BY post_at",
            (as_of.isoformat(),),
        ).fetchall()


def get_active_recurring_feeds(day_name: str, time_str: str) -> list[sqlite3.Row]:
    """Return recurring feeds matching the day of week and time that haven't been posted today."""
    with _connect() as conn:
        # We query for matches where the day name is in recurrence_days (lowercased) and time matches
        # and last_posted_at is not today
        today_date = datetime.utcnow().strftime("%Y-%m-%d")
        all_recur = conn.execute(
            "SELECT * FROM scheduled_feeds WHERE is_recurring=1 AND recurrence_time = ?",
            (time_str,),
        ).fetchall()
        
        matches = []
        for row in all_recur:
            days = [d.strip().lower() for d in (row["recurrence_days"] or "").split(",") if d.strip()]
            if day_name.lower() in days and row["last_posted_at"] != today_date:
                matches.append(row)
        return matches


def mark_recurring_posted(feed_id: int, date_str: str):
    """Mark a recurring feed as posted today to prevent double-posting."""
    with _connect() as conn:
        conn.execute(
            "UPDATE scheduled_feeds SET last_posted_at=? WHERE id=?",
            (date_str, feed_id),
        )
        conn.commit()


def get_all_pending_feeds() -> list[sqlite3.Row]:
    """Return all future/active feeds (both one-time and recurring) for display."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM scheduled_feeds WHERE (is_recurring=0 AND posted=0) OR (is_recurring=1) ORDER BY id"
        ).fetchall()


def mark_posted(feed_id: int):
    """Mark a one-time feed as published."""
    with _connect() as conn:
        conn.execute(
            "UPDATE scheduled_feeds SET posted=1 WHERE id=?", (feed_id,)
        )
        conn.commit()


def delete_feed(feed_id: int) -> bool:
    """Delete a feed by ID. Returns True if a row was deleted."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM scheduled_feeds WHERE id=? AND (posted=0 OR is_recurring=1)", (feed_id,)
        )
        conn.commit()
        return cur.rowcount > 0


# ─── Processed LMS Graduates Helpers ──────────────────────────────────────────

def is_graduate_processed(email: str, course: str) -> bool:
    """Check if this graduate-course combo has already been posted to the channel."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_graduates WHERE email=? AND course=?",
            (email.strip().lower(), course.strip().lower()),
        ).fetchone()
        return row is not None


def mark_graduate_processed(email: str, course: str):
    """Save graduate as processed so they won't be announced again."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_graduates (email, course, processed_at) VALUES (?, ?, ?)",
            (email.strip().lower(), course.strip().lower(), datetime.utcnow().isoformat()),
        )
        conn.commit()
