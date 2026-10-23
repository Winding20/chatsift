
import json
from datetime import datetime

from app.database import get_connection, init_database
from app.models import Message


def _parse_list(value: str | None) -> list:
    if not value:
        return []

    try:
        result = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []

    return result if isinstance(result, list) else []


class MessageRepository:
    def __init__(self) -> None:
        init_database()

    def save(self, message: Message) -> bool:
        """保存新消息；返回是否为首次插入。"""
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO messages (
                    id, source, chat_id, chat_name, sender_id,
                    sender_name, content, timestamp, account_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.id,
                    message.source,
                    message.chat_id,
                    message.chat_name,
                    message.sender_id,
                    message.sender_name,
                    message.content,
                    message.timestamp.isoformat(),
                    getattr(message, "account_id", None),
                ),
            )

            inserted = cursor.rowcount == 1

            if inserted:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO analysis_queue (
                        message_id, chat_id, status
                    )
                    VALUES (?, ?, 'pending')
                    """,
                    (message.id, message.chat_id),
                )

            return inserted

    def get_recent(self, limit: int = 100) -> list[Message]:
        limit = max(1, min(int(limit), 5000))

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [self._row_to_message(row) for row in rows]

    def get_by_chat(
        self,
        chat_id: str,
        limit: int = 100,
    ) -> list[Message]:
        limit = max(1, min(int(limit), 5000))

        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (chat_id, limit),
            ).fetchall()

        # 返回的消息按时间从早到晚排列。
        return [
            self._row_to_message(row)
            for row in reversed(rows)
        ]

    def get_pending_chat_ids(self) -> list[str]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT chat_id
                FROM analysis_queue
                WHERE status = 'pending'
                ORDER BY chat_id
                """
            ).fetchall()

        return [row["chat_id"] for row in rows]

    def get_pending_by_chat(self, chat_id: str) -> list[Message]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT m.*
                FROM messages AS m
                INNER JOIN analysis_queue AS q
                    ON q.message_id = m.id
                WHERE q.chat_id = ?
                  AND q.status = 'pending'
                ORDER BY m.timestamp ASC, m.id ASC
                """,
                (chat_id,),
            ).fetchall()

        return [self._row_to_message(row) for row in rows]

    def get_pending_attempts(self, chat_id: str) -> int:
        """该群待分析消息里最高的重试次数。"""
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(attempts), 0) AS attempts
                FROM analysis_queue
                WHERE chat_id = ? AND status = 'pending'
                """,
                (chat_id,),
            ).fetchone()

        return int(row["attempts"])

    def mark_failed(self, message_ids: list[str], error: str) -> None:
        """超过重试上限后停放，避免每轮都重复失败。"""
        if not message_ids:
            return

        with get_connection() as connection:
            connection.executemany(
                """
                UPDATE analysis_queue
                SET status = 'failed', last_error = ?
                WHERE message_id = ?
                """,
                [(error[:2000], message_id) for message_id in message_ids],
            )

    def mark_analyzed(self, message_ids: list[str]) -> None:
        """仅在该批次分析和事件处理全部成功后调用。"""
        if not message_ids:
            return

        with get_connection() as connection:
            connection.executemany(
                """
                DELETE FROM analysis_queue
                WHERE message_id = ? AND status = 'pending'
                """,
                [(message_id,) for message_id in message_ids],
            )

    def record_analysis_failure(
        self,
        message_ids: list[str],
        error: str,
    ) -> None:
        if not message_ids:
            return

        with get_connection() as connection:
            connection.executemany(
                """
                UPDATE analysis_queue
                SET attempts = attempts + 1,
                    last_error = ?
                WHERE message_id = ? AND status = 'pending'
                """,
                [
                    (error[:2000], message_id)
                    for message_id in message_ids
                ],
            )

    @staticmethod
    def _row_to_message(row) -> Message:
        timestamp = datetime.fromisoformat(row["timestamp"])

        return Message(
            id=row["id"],
            source=row["source"],
            chat_id=row["chat_id"],
            chat_name=row["chat_name"],
            sender_id=row["sender_id"],
            sender_name=row["sender_name"],
            content=row["content"],
            timestamp=timestamp,
            account_id=(
                row["account_id"]
                if "account_id" in row.keys()
                else None
            ),
        )


class ChatSummaryRepository:
    def __init__(self) -> None:
        init_database()

    def save(
        self,
        chat_id: str,
        chat_name: str,
        summary: str,
        message_ids: list[str],
    ) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO chat_summaries (
                    chat_id, chat_name, summary, message_ids, updated_at
                )
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    chat_name = excluded.chat_name,
                    summary = excluded.summary,
                    message_ids = excluded.message_ids,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chat_id,
                    chat_name,
                    summary,
                    json.dumps(
                        list(dict.fromkeys(message_ids)),
                        ensure_ascii=False,
                    ),
                ),
            )

    def get_by_chat(self, chat_id: str) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM chat_summaries
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()

        if row is None:
            return None

        result = dict(row)
        result["message_ids"] = _parse_list(result["message_ids"])
        return result

    def get_all(self) -> list[dict]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM chat_summaries
                ORDER BY updated_at DESC
                """
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["message_ids"] = _parse_list(item["message_ids"])
            result.append(item)

        return result
