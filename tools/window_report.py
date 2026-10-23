"""只读：算每个群"最近 100 条消息"覆盖多长时间。"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB = Path(__file__).resolve().parent.parent / "data" / "assistant.db"


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    chats = con.execute(
        "SELECT chat_id, MAX(chat_name) AS name, COUNT(*) AS total FROM messages GROUP BY chat_id"
    ).fetchall()

    print(f"{'群':<26}{'总条数':>6}{'最近100条跨度':>16}")
    rows = []
    for chat in chats:
        recent = con.execute(
            """
            SELECT timestamp FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp DESC LIMIT 100
            """,
            (chat["chat_id"],),
        ).fetchall()
        if len(recent) < 2:
            continue
        times = [datetime.fromisoformat(r["timestamp"]) for r in recent]
        span = max(times) - min(times)
        rows.append((chat["name"] or chat["chat_id"], chat["total"], span))

    for name, total, span in sorted(rows, key=lambda r: r[2], reverse=True):
        minutes = int(span.total_seconds() / 60)
        text = f"{minutes} 分钟" if minutes < 180 else f"{minutes / 60:.1f} 小时"
        print(f"{name[:24]:<26}{total:>6}{text:>16}")


if __name__ == "__main__":
    main()
