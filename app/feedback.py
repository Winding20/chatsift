"""用户对某条内容的"有用 / 无聊"反馈。

两个用途：
1. 记录下来，页面上回显，也方便统计你的口味；
2. 把"无聊"的原文作为反例塞进提示词，下次别再挑类似的。
"""

from __future__ import annotations

import hashlib

from app.database import get_connection

UP = 1
DOWN = -1


def card_key(chat_id: str, message_ids: list[str] | None) -> str:
    """卡片的稳定标识：同一个群 + 同一批消息 = 同一张卡。"""
    raw = (chat_id or "") + "|" + ",".join(sorted(message_ids or []))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def save_vote(
    key: str,
    chat_id: str,
    quote: str,
    vote: int,
    kind: str = "",
) -> None:
    if not key:
        raise ValueError("缺少卡片标识")

    with get_connection() as connection:
        if vote == 0:
            connection.execute(
                "DELETE FROM card_feedback WHERE card_key = ?", (key,)
            )
            return

        connection.execute(
            """
            INSERT INTO card_feedback (card_key, chat_id, quote, type, vote, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(card_key) DO UPDATE SET
                vote = excluded.vote,
                type = excluded.type,
                created_at = excluded.created_at
            """,
            (
                key,
                chat_id or "",
                (quote or "")[:200],
                (kind or "")[:20],
                UP if vote > 0 else DOWN,
            ),
        )


def stats_by_type() -> list[dict]:
    """按卡片类型统计：你喜欢哪类、讨厌哪类。"""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT type,
                   SUM(CASE WHEN vote > 0 THEN 1 ELSE 0 END) AS good,
                   SUM(CASE WHEN vote < 0 THEN 1 ELSE 0 END) AS bad
            FROM card_feedback
            GROUP BY type
            ORDER BY (good + bad) DESC
            """
        ).fetchall()

    return [
        {
            "type": row["type"] or "unknown",
            "good": int(row["good"] or 0),
            "bad": int(row["bad"] or 0),
        }
        for row in rows
    ]


def get_votes() -> dict[str, int]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT card_key, vote FROM card_feedback"
        ).fetchall()

    return {row["card_key"]: row["vote"] for row in rows}


def stats() -> dict[str, int]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                SUM(CASE WHEN vote > 0 THEN 1 ELSE 0 END) AS good,
                SUM(CASE WHEN vote < 0 THEN 1 ELSE 0 END) AS bad
            FROM card_feedback
            """
        ).fetchone()

    return {
        "good": int(row["good"] or 0),
        "bad": int(row["bad"] or 0),
    }


def disliked_examples(limit: int = 5) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT quote FROM card_feedback
            WHERE vote < 0 AND quote != ''
            ORDER BY created_at DESC LIMIT ?
            """,
            (max(0, int(limit)),),
        ).fetchall()

    return [row["quote"] for row in rows]


def liked_examples(limit: int = 3) -> list[str]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT quote FROM card_feedback
            WHERE vote > 0 AND quote != ''
            ORDER BY created_at DESC LIMIT ?
            """,
            (max(0, int(limit)),),
        ).fetchall()

    return [row["quote"] for row in rows]
