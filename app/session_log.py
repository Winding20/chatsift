"""接收端连接记录 + 分析游标。

为什么需要：消息只在接收端在线时才有，中间断过的那段就是"数据缺口"。
不把缺口说出来，用户会以为总结覆盖了他离开的整段时间。
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.database import get_connection, init_database


GAP_SECONDS = 120


def _now() -> str:
    return datetime.now().isoformat()


def open_connection() -> int:
    init_database()
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO connection_events (connected_at) VALUES (?)",
            (_now(),),
        )
        return int(cursor.lastrowid)


def close_connection(event_id: int) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE connection_events
            SET disconnected_at = ?
            WHERE id = ? AND disconnected_at IS NULL
            """,
            (_now(), event_id),
        )


def gaps(days: int = 7) -> list[dict]:
    """返回最近若干天里"接收端不在线"的时段。"""
    since = (datetime.now() - timedelta(days=days)).isoformat()

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT connected_at, disconnected_at
            FROM connection_events
            WHERE connected_at >= ?
            ORDER BY connected_at ASC
            """,
            (since,),
        ).fetchall()

    result: list[dict] = []
    for index, row in enumerate(rows):
        closed_at = row["disconnected_at"]
        if closed_at is None:
            continue

        next_start = rows[index + 1]["connected_at"] if index + 1 < len(rows) else _now()
        gap = (
            datetime.fromisoformat(next_start)
            - datetime.fromisoformat(closed_at)
        ).total_seconds()

        if gap > GAP_SECONDS:
            result.append({"from": closed_at, "to": next_start})

    return result


def last_analyzed(chat_id: str) -> str | None:
    init_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT last_analyzed_at FROM analysis_cursors WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()

    return None if row is None else row["last_analyzed_at"]


def set_analyzed(chat_id: str, moment: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO analysis_cursors (chat_id, last_analyzed_at)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                last_analyzed_at = MAX(last_analyzed_at, excluded.last_analyzed_at)
            """,
            (chat_id, moment),
        )
