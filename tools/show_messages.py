"""只读：打印某个群最近 N 条消息，用来判断 AI 的"无内容"结论是否合理。"""

import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assistant.db"


def main() -> None:
    chat_id = sys.argv[1] if len(sys.argv) > 1 else ""
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 40

    if not chat_id:
        print("用法: python tools/show_messages.py <chat_id> [limit]")
        return

    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    rows = con.execute(
        """
        SELECT timestamp, sender_name, content
        FROM messages
        WHERE chat_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (chat_id, limit),
    ).fetchall()

    for timestamp, sender, content in reversed(rows):
        text = (content or "").replace("\n", " ")
        print(f"{timestamp} | {sender} | {text[:120]}")

    con.close()


if __name__ == "__main__":
    main()
