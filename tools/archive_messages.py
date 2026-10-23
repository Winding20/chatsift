"""把很久以前的消息搬到归档表，主表保持轻量。

用法：
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\archive_messages.py --days 180
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\archive_messages.py --days 180 --apply

归档只是搬家，不删数据：消息会进 messages_archive 表，主表查不到，
需要时还能从归档表里翻。
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.database import DATABASE_PATH, get_connection  # noqa: E402


def ensure_archive_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS messages_archive (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_name TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            account_id TEXT,
            archived_at TEXT NOT NULL
                DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
        )
        """
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="归档老消息")
    parser.add_argument("--days", type=int, default=180, help="保留最近多少天")
    parser.add_argument("--apply", action="store_true", help="真正执行")
    args = parser.parse_args()

    cutoff = (datetime.now() - timedelta(days=args.days)).isoformat()
    print(f"数据库  {DATABASE_PATH}")
    print(f"保留    {args.days} 天，早于 {cutoff[:16]} 的消息会被归档")

    with get_connection() as connection:
        ensure_archive_table(connection)
        total = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        old = connection.execute(
            "SELECT COUNT(*) FROM messages WHERE timestamp < ?", (cutoff,)
        ).fetchone()[0]
        print(f"消息    {total} 条，其中 {old} 条会被归档")

        if not args.apply:
            print("\n这是预览。加 --apply 才会真正搬家。")
            return 0

        if old == 0:
            print("没有需要归档的消息。")
            return 0

        connection.execute(
            """
            INSERT OR IGNORE INTO messages_archive (
                id, source, chat_id, chat_name, sender_id,
                sender_name, content, timestamp, account_id
            )
            SELECT id, source, chat_id, chat_name, sender_id,
                   sender_name, content, timestamp, account_id
            FROM messages WHERE timestamp < ?
            """,
            (cutoff,),
        )
        connection.execute(
            """
            DELETE FROM analysis_queue WHERE message_id IN (
                SELECT id FROM messages WHERE timestamp < ?
            )
            """,
            (cutoff,),
        )
        connection.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))

        remaining = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        archived = connection.execute(
            "SELECT COUNT(*) FROM messages_archive"
        ).fetchone()[0]

    print(f"完成    主表剩 {remaining} 条，归档表共 {archived} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
