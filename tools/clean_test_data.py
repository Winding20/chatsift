"""清理测试数据。

会挑出明显的测试群（群号或群名里带 test / 测试 / group_ / demo），
先把要删的东西列出来，加 --apply 才真正删。

用法：
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\clean_test_data.py
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\clean_test_data.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.database import get_connection  # noqa: E402

PATTERN = (
    "chat_id LIKE 'group\\_%' ESCAPE '\\' "
    "OR chat_id LIKE 'test%' "
    "OR chat_id LIKE 'demo%' "
    "OR chat_id LIKE 'import-%' "
    "OR chat_name LIKE '%测试%' "
    "OR chat_name LIKE '%test%' "
    "OR chat_name LIKE '%demo%'"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理测试群数据")
    parser.add_argument("--apply", action="store_true", help="真正删除")
    args = parser.parse_args()

    with get_connection() as connection:
        chats = connection.execute(
            f"""
            SELECT chat_id, MAX(chat_name) AS chat_name,
                   COUNT(*) AS messages
            FROM messages
            WHERE {PATTERN}
            GROUP BY chat_id
            ORDER BY messages DESC
            """
        ).fetchall()

        if not chats:
            print("没有发现测试群。")
            return 0

        print("将要清理的群：")
        total_messages = 0
        for row in chats:
            reports = connection.execute(
                "SELECT COUNT(*) FROM analysis_reports WHERE chat_id = ?",
                (row["chat_id"],),
            ).fetchone()[0]
            total_messages += row["messages"]
            print(
                f"  {row['chat_id']:<16} {row['chat_name']:<20} "
                f"消息 {row['messages']:>5} 条 · 报告 {reports} 份"
            )
        print(f"\n合计 {len(chats)} 个群、{total_messages} 条消息会从主库删除")

        if not args.apply:
            print("\n这是预览。加 --apply 才会真正删除。")
            return 0

        chat_ids = [row["chat_id"] for row in chats]
        placeholders = ",".join("?" for _ in chat_ids)
        for table, column in (
            ("messages", "chat_id"),
            ("analysis_queue", "chat_id"),
            ("analysis_reports", "chat_id"),
            ("analysis_cursors", "chat_id"),
            ("events", "chat_id"),
        ):
            try:
                connection.execute(
                    f"DELETE FROM {table} WHERE {column} IN ({placeholders})",
                    chat_ids,
                )
            except Exception as exc:  # noqa: BLE001 — 表可能不存在
                print(f"  跳过 {table}: {exc}")

    print("清理完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
