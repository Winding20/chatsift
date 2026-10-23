"""只读：队列积压与数据卫生检查。"""

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assistant.db"


def main() -> None:
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    print("queue by chat (top 12):")
    for row in con.execute(
        """
        SELECT chat_id, COUNT(*) AS n, MAX(attempts) AS max_attempts,
               MIN(created_at) AS oldest
        FROM analysis_queue
        WHERE status = 'pending'
        GROUP BY chat_id
        ORDER BY n DESC
        LIMIT 12
        """
    ):
        print(
            f"  {row['chat_id']:12s} n={row['n']:3d} "
            f"max_attempts={row['max_attempts']} oldest={row['oldest']}"
        )

    print("attempts distribution:")
    for row in con.execute(
        "SELECT attempts, COUNT(*) AS n FROM analysis_queue GROUP BY attempts"
    ):
        print(f"  attempts={row['attempts']}: {row['n']}")

    print("recent failure reasons:")
    for row in con.execute(
        """
        SELECT substr(last_error, 1, 160) AS err, COUNT(*) AS n
        FROM analysis_queue
        WHERE last_error IS NOT NULL
        GROUP BY err
        ORDER BY n DESC
        LIMIT 5
        """
    ):
        print(f"  {row['n']}x  {row['err']}")

    print("test groups still in db:")
    for row in con.execute(
        """
        SELECT chat_id, MAX(chat_name) AS name, COUNT(*) AS n
        FROM messages
        WHERE chat_id LIKE 'group%' OR chat_name LIKE '%测试%'
        GROUP BY chat_id
        """
    ):
        print(f"  {row['chat_id']} | {row['name']} | {row['n']} 条")

    counts = {}
    for key, sql in {
        "analysis_reports": "SELECT COUNT(*) FROM analysis_reports",
        "chat_summaries": "SELECT COUNT(*) FROM chat_summaries",
        "events": "SELECT COUNT(*) FROM events",
        "events_without_time_and_location": (
            "SELECT COUNT(*) FROM events WHERE time IS NULL AND location IS NULL"
        ),
        "events_no_cited_messages": (
            "SELECT COUNT(*) FROM events WHERE message_ids = '[]'"
        ),
    }.items():
        counts[key] = con.execute(sql).fetchone()[0]

    for key, value in counts.items():
        print(f"{key}={value}")

    con.close()


if __name__ == "__main__":
    main()
