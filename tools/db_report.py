"""只读数据库体检脚本：不写库、不调用 AI。"""

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "assistant.db"


def main() -> None:
    if not DB_PATH.exists():
        print(f"数据库不存在：{DB_PATH}")
        return

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    print(f"DB={DB_PATH}  size={DB_PATH.stat().st_size} bytes")

    tables = [
        row["name"]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print(f"tables={tables}")

    for table in ("messages", "events", "chat_summaries", "analysis_queue"):
        if table in tables:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"  {table:16s} rows={count}")

    if "analysis_queue" in tables:
        print("analysis_queue status:")
        for row in con.execute(
            "SELECT status, COUNT(*) AS c FROM analysis_queue GROUP BY status"
        ):
            print(f"    {row['status']}: {row['c']}")
        row = con.execute(
            "SELECT COALESCE(MAX(attempts),0) AS m, COALESCE(SUM(attempts),0) AS s "
            "FROM analysis_queue"
        ).fetchone()
        print(f"  attempts max={row['m']} sum={row['s']}")

    print("chats:")
    for row in con.execute(
        """
        SELECT m.chat_id,
               MAX(m.chat_name) AS chat_name,
               COUNT(*) AS n,
               MIN(m.timestamp) AS first_ts,
               MAX(m.timestamp) AS last_ts
        FROM messages AS m
        GROUP BY m.chat_id
        ORDER BY last_ts DESC
        """
    ):
        print(
            f"  {row['chat_id']} | {row['chat_name']} | {row['n']} 条 | "
            f"{row['first_ts']} -> {row['last_ts']}"
        )

    if "chat_summaries" in tables:
        print("chat_summaries:")
        for row in con.execute(
            "SELECT * FROM chat_summaries ORDER BY updated_at DESC"
        ):
            ids = row["message_ids"] or "[]"
            try:
                import json

                ids = json.loads(ids)
            except Exception:
                pass
            text = (row["summary"] or "").replace("\n", " ⏎ ")
            print(
                f"  chat_id={row['chat_id']} name={row['chat_name']} "
                f"updated_at={row['updated_at']} ids={len(ids) if isinstance(ids, list) else '?'} "
                f"len={len(row['summary'] or '')}"
            )
            print(f"    {text[:300]}")

    print("events 最近 15 条标题:")
    for row in con.execute(
        "SELECT id, chat_id, title, time, location FROM events ORDER BY id DESC LIMIT 15"
    ):
        print(
            f"  #{row['id']} chat={row['chat_id']} title={row['title']!r} "
            f"time={row['time']!r} loc={row['location']!r}"
        )

    noise = [
        "[image]", "[表情]", "[图片]", "冒泡", "打人", "分享音乐",
        "发送图片", "发送表情", "表达不满",
    ]
    placeholders = ",".join("?" * len(noise))
    bad = con.execute(
        f"SELECT COUNT(*) FROM events WHERE title IN ({placeholders})", noise
    ).fetchone()[0]
    print(f"events 命中已知噪声标题={bad}")

    con.close()


if __name__ == "__main__":
    main()
