"""结构化分析报告的存取。新表，与旧的 chat_summaries 完全独立。"""

from __future__ import annotations

import json
from datetime import datetime

from app.database import get_connection, init_database
from app.models import Message


def _load_payload(raw: str) -> dict:
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}

    return payload if isinstance(payload, dict) else {}


def _row_to_report(row) -> dict:
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "chat_name": row["chat_name"],
        "generated_at": row["generated_at"],
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "message_count": row["message_count"],
        "model": row["model"],
        "dropped": row["dropped"],
        "payload": _load_payload(row["payload"]),
    }


class AnalysisReportRepository:
    def __init__(self) -> None:
        init_database()

    def save(
        self,
        chat_id: str,
        chat_name: str,
        report,
    ) -> int:
        with get_connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO analysis_reports (
                    chat_id, chat_name, window_start, window_end,
                    message_count, model, dropped, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    chat_name,
                    report.window_start,
                    report.window_end,
                    report.message_count,
                    report.model,
                    report.dropped,
                    json.dumps(report.payload, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def get_latest(self, chat_id: str) -> dict | None:
        """优先返回最新一份"有内容"的结果，避免空报告盖掉之前挑到的。"""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_reports
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (chat_id,),
            ).fetchall()

        if not rows:
            return None

        fallback = _row_to_report(rows[0])
        for row in rows:
            report = _row_to_report(row)
            if (report.get("payload") or {}).get("cards"):
                return report

        return fallback

    def get_latest_digests(self) -> list[dict]:
        """每个群最新一份带"时段纪要"的报告，卡片有没有内容都算。"""
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM analysis_reports ORDER BY id DESC"
            ).fetchall()

        best: dict[str, dict] = {}
        for row in rows:
            report = _row_to_report(row)
            chat_id = report["chat_id"]
            if chat_id in best:
                continue
            if (report.get("payload") or {}).get("digest"):
                best[chat_id] = report

        return sorted(best.values(), key=lambda item: item["id"], reverse=True)

    def recent_reports(self, limit: int = 60) -> list[dict]:
        """最近的若干份报告，供"历史"时间轴用。空报告不列。"""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_reports
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()

        result = []
        for row in rows:
            report = _row_to_report(row)
            payload = report.get("payload") or {}
            if not payload.get("cards") and not payload.get("digest"):
                continue
            result.append(report)

        return result

    def get_by_id(self, report_id: int) -> dict | None:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM analysis_reports WHERE id = ?",
                (report_id,),
            ).fetchone()

        return None if row is None else _row_to_report(row)

    def get_all_latest(self) -> list[dict]:
        """每个群取"最新一份有卡片的结果"；全空时退回最新一份。"""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM analysis_reports
                ORDER BY id DESC
                """
            ).fetchall()

        best: dict[str, dict] = {}
        fallback: dict[str, dict] = {}
        for row in rows:
            report = _row_to_report(row)
            chat_id = report["chat_id"]
            fallback.setdefault(chat_id, report)
            has_cards = bool((report.get("payload") or {}).get("cards"))
            if has_cards and chat_id not in best:
                best[chat_id] = report

        merged = [
            best.get(chat_id) or fallback[chat_id] for chat_id in fallback
        ]
        merged.sort(key=lambda report: report["id"], reverse=True)
        return merged

    def get_sources(self, message_ids: list[str]) -> list[Message]:
        """按 ID 取原始消息，供页面展示"这条结论依据哪句话"。"""
        if not message_ids:
            return []

        placeholders = ",".join("?" * len(message_ids))
        with get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT * FROM messages
                WHERE id IN ({placeholders})
                ORDER BY timestamp ASC, id ASC
                """,
                tuple(message_ids),
            ).fetchall()

        return [
            Message(
                id=row["id"],
                source=row["source"],
                chat_id=row["chat_id"],
                chat_name=row["chat_name"],
                sender_id=row["sender_id"],
                sender_name=row["sender_name"],
                content=row["content"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]
