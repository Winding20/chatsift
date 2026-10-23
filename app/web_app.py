"""本地只读面板 + 按需触发一次 AI 分析。

页面上的每一条结论都必须能点回原始消息，所以这里把
"报告正文"和"它引用的原始消息"一起返回，前端并排展示。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from collections import Counter
from datetime import datetime, timedelta

from flask import Flask, Response, jsonify, redirect, render_template, request

from app.ai_client import ZhipuAIClient
from app import feedback, session_log, settings
from app.health import report as health_report
from app.config import get_web_password
from app.database import get_connection
from app.feed_generator import (
    EVAL_RE,
    MAX_MESSAGES,
    FeedGenerationError,
    generate as generate_feed,
)
from app.models import Message

MAX_CARDS_PER_CHAT = 4

from app.report_repository import AnalysisReportRepository
from app.repositories import MessageRepository

app = Flask(__name__)

_repository: AnalysisReportRepository | None = None
_generation_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def repository() -> AnalysisReportRepository:
    global _repository
    if _repository is None:
        _repository = AnalysisReportRepository()
    return _repository


def _lock_for(chat_id: str) -> threading.Lock:
    with _locks_guard:
        return _generation_locks.setdefault(chat_id, threading.Lock())


def _serialize_message(row) -> dict:
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "chat_name": row["chat_name"],
        "sender_id": row["sender_id"],
        "sender_name": row["sender_name"],
        "content": row["content"],
        "timestamp": row["timestamp"],
    }


PLACEHOLDER_ONLY = re.compile(r"^\s*(\[[a-zA-Z]+\]\s*)+$")


def _context_for(
    connection,
    chat_id: str,
    timestamp: str | None,
    message_id: str | None,
    limit: int = 2,
    minutes: int = 10,
) -> dict:
    """从数据库现算上下文，老报告也能有上下文，不必重新生成。"""
    empty = {"before": [], "after": []}
    if not chat_id or not timestamp:
        return empty

    try:
        anchor = datetime.fromisoformat(timestamp)
    except (TypeError, ValueError):
        return empty

    low = (anchor - timedelta(minutes=minutes)).isoformat()
    high = (anchor + timedelta(minutes=minutes)).isoformat()

    rows = connection.execute(
        """
        SELECT id, sender_name, content, timestamp
        FROM messages
        WHERE chat_id = ? AND timestamp BETWEEN ? AND ?
        ORDER BY timestamp ASC, id ASC
        """,
        (chat_id, low, high),
    ).fetchall()

    before: list[dict] = []
    after: list[dict] = []
    for row in rows:
        if message_id and row["id"] == message_id:
            continue
        text = (row["content"] or "").strip().replace("\n", " ")
        if not text or PLACEHOLDER_ONLY.match(text):
            continue

        item = {"sender": row["sender_name"], "content": text[:120]}
        try:
            moment = datetime.fromisoformat(row["timestamp"])
        except (TypeError, ValueError):
            continue

        if moment < anchor:
            before.append(item)
        else:
            after.append(item)

    return {"before": before[-limit:], "after": after[:limit]}


def _sources_for(report: dict | None) -> list[dict]:
    if not report:
        return []

    payload = report.get("payload") or {}
    wanted: list[str] = []

    if payload.get("v") == 2:
        for card in payload.get("cards") or []:
            for message_id in card.get("message_ids") or []:
                if message_id not in wanted:
                    wanted.append(message_id)
    else:
        for item in (payload.get("highlights") or []) + (
            payload.get("open_items") or []
        ):
            for message_id in item.get("message_ids") or []:
                if message_id not in wanted:
                    wanted.append(message_id)

    if not wanted:
        return []

    placeholders = ",".join("?" * len(wanted))
    with get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT * FROM messages
            WHERE id IN ({placeholders})
            ORDER BY timestamp ASC, id ASC
            """,
            tuple(wanted),
        ).fetchall()

    return [_serialize_message(row) for row in rows]


app.secret_key = os.environ.get("WEB_SECRET") or "chatsift-local-secret"


def _auth_token(password: str) -> str:
    return hashlib.sha1((password + app.secret_key).encode("utf-8")).hexdigest()[:24]


@app.before_request
def _require_login():
    """设了 WEB_PASSWORD 就必须登录；没设就只当本机工具用。"""
    password = get_web_password()
    if not password:
        return None
    if request.path.startswith("/static") or request.path == "/login":
        return None
    if request.cookies.get("chatsift_auth") == _auth_token(password):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "需要登录"}), 401
    return redirect("/login")


@app.route("/login", methods=["GET", "POST"])
def login():
    password = get_web_password()
    if not password:
        return redirect("/")

    error = ""
    if request.method == "POST":
        if (request.form.get("password") or "") == password:
            response = redirect("/")
            response.set_cookie(
                "chatsift_auth",
                _auth_token(password),
                max_age=30 * 24 * 3600,
                httponly=True,
                samesite="Lax",
            )
            return response
        error = "密码不对"

    return render_template("login.html", error=error)


@app.route("/api/export")
def export_markdown():
    """把某个群最新一批分析导出成 Markdown。"""
    chat_id = (request.args.get("chat_id") or "").strip()
    if not chat_id:
        return jsonify({"error": "缺少 chat_id"}), 400

    report = next(
        (r for r in repository().get_all_latest() if r["chat_id"] == chat_id),
        None,
    )
    if report is None:
        return jsonify({"error": "这个群还没有分析结果"}), 404

    payload = report.get("payload") or {}
    lines = [
        f"# {report['chat_name']}",
        "",
        f"> 覆盖 {str(report.get('window_start') or '')[:16]} ~ "
        f"{str(report.get('window_end') or '')[:16]}，"
        f"{report.get('message_count', 0)} 条消息",
        "",
    ]

    if payload.get("digest"):
        lines.append("## 群里发生了什么")
        lines.append("")
        for topic in payload["digest"]:
            lines.append(f"### {topic.get('title', '')}")
            if topic.get("summary"):
                lines.append(topic["summary"])
            meta = [topic.get("range_label"), "、".join(topic.get("participants") or [])]
            meta = [item for item in meta if item]
            if meta:
                lines.append("")
                lines.append(f"*{' · '.join(meta)}*")
            lines.append("")

    if payload.get("cards"):
        lines.append("## 值得看的")
        lines.append("")
        for card in payload["cards"]:
            lines.append(f"- **{card.get('type_label', '')}** 「{card.get('quote', '')}」")
            if card.get("why"):
                lines.append(f"  - {card['why']}")
        lines.append("")

    body = "\n".join(lines)
    return Response(
        body,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=chatsift.md"},
    )


@app.route("/")
def index():
    return render_template("feed.html")


@app.route("/api/feed")
def feed():
    """所有群的最新一批"值得看的内容"，合并成一条信息流。"""
    reports = repository().get_all_latest()
    reports = [r for r in reports if (r.get("payload") or {}).get("v") == 2]

    cards: list[dict] = []
    votes = feedback.get_votes()
    for report in reports:
        for card in (report.get("payload") or {}).get("cards") or []:
            item = dict(card)
            item["chat_id"] = report["chat_id"]
            item["chat_name"] = report["chat_name"]
            item["generated_at"] = report["generated_at"]
            item["key"] = feedback.card_key(
                report["chat_id"], card.get("message_ids")
            )
            item["vote"] = votes.get(item["key"], 0)
            cards.append(item)

    # 时段纪要：每个群一段"这段时间发生了什么"（和卡片分开取，互不影响）。
    digests: list[dict] = []
    for report in repository().get_latest_digests():
        topics = (report.get("payload") or {}).get("digest") or []
        if not topics:
            continue
        # 老报告里的话题没有 range_label，这里按 start/end 补一个，避免页面空白
        for topic in topics:
            if not topic.get("range_label") and topic.get("start"):
                start, end = topic["start"], topic.get("end") or topic["start"]
                topic["range_label"] = start if start == end else f"{start}–{end}"

        digests.append(
            {
                "chat_id": report["chat_id"],
                "chat_name": report["chat_name"],
                "generated_at": report["generated_at"],
                "window_start": report.get("window_start"),
                "window_end": report.get("window_end"),
                "message_count": report.get("message_count", 0),
                "topics": topics,
            }
        )
    digests.sort(key=lambda item: item.get("generated_at") or "", reverse=True)

    # 先按时间倒序，再按分数稳定排序：同分时新的在前。
    cards.sort(key=lambda c: c.get("timestamp") or "", reverse=True)
    cards.sort(key=lambda c: -int(c.get("score") or 0))

    # 历史数据里可能残留机器人模板：开头相同的不重复展示。
    prefixes = Counter((card.get("quote") or "")[:8] for card in cards)
    cards = [
        card
        for card in cards
        if prefixes[(card.get("quote") or "")[:8]] < 2
        # 老报告里存下的"骂人当知识点"，读取时也挡掉
        and not (
            card.get("type") == "knowledge"
            and EVAL_RE.search(card.get("quote") or "")
        )
    ]

    # 每群最多留 4 条：一个活跃群不该占满整条信息流
    per_chat: Counter = Counter()
    limited: list[dict] = []
    for card in cards:
        chat_key = card.get("chat_id")
        if per_chat[chat_key] >= MAX_CARDS_PER_CHAT:
            continue
        per_chat[chat_key] += 1
        limited.append(card)
    cards = limited

    with get_connection() as connection:
        chats = [
            dict(row)
            for row in connection.execute(
                """
                SELECT m.chat_id,
                       MAX(m.chat_name) AS chat_name,
                       COUNT(*) AS message_count,
                       MAX(m.timestamp) AS last_message_time
                FROM messages AS m
                GROUP BY m.chat_id
                ORDER BY last_message_time DESC
                """
            ).fetchall()
        ]

        # 老报告没有存上下文，这里现算一次，保证每张卡都能展开看到前后文。
        for card in cards:
            context = card.get("context") or {}
            if context.get("before") or context.get("after"):
                continue
            source_id = (card.get("message_ids") or [None])[0]
            card["context"] = _context_for(
                connection,
                card.get("chat_id"),
                card.get("timestamp"),
                source_id,
            )

    # 同一个群里上下文有重叠的，只留一条：避免同一段对话出现好几张卡。
    seen: dict[str, set[str]] = {}
    unique_cards = []
    for card in cards:
        chat_key = card.get("chat_id") or ""
        context = card.get("context") or {}
        lines = [card.get("quote") or ""]
        lines += [line.get("content", "") for line in context.get("before", [])]
        lines += [line.get("content", "") for line in context.get("after", [])]
        fingerprint = {re.sub(r"\s+", "", line)[:40] for line in lines if line}

        bucket = seen.setdefault(chat_key, set())
        if fingerprint & bucket:
            continue
        bucket |= fingerprint
        unique_cards.append(card)

    cards = unique_cards

    with_feed = {report["chat_id"]: report for report in reports}

    for chat in chats:
        report = with_feed.get(chat["chat_id"])
        chat["has_feed"] = report is not None
        chat["feed_generated_at"] = (
            report["generated_at"] if report else None
        )

    return jsonify({
        "cards": cards,
        "digests": digests,
        "chats": chats,
        "stats": {
            "chats_with_feed": len(reports),
            "chat_count": len(chats),
            "card_count": len(cards),
        },
    })


@app.route("/api/history")
def history():
    """按日期分组的分析记录，用来补看之前的时间段。"""
    try:
        limit = int(request.args.get("limit", 60))
    except (TypeError, ValueError):
        limit = 60

    groups: dict[str, list[dict]] = {}
    for report in repository().recent_reports(limit):
        payload = report.get("payload") or {}
        topics = payload.get("digest") or []
        cards = payload.get("cards") or []
        moment = report.get("window_end") or report.get("generated_at") or ""
        day = moment[:10] or "未知"

        headline = ""
        if topics:
            headline = topics[0].get("title", "")
        elif cards:
            headline = (cards[0].get("quote") or "")[:30]

        groups.setdefault(day, []).append({
            "id": report["id"],
            "chat_id": report["chat_id"],
            "chat_name": report["chat_name"],
            "generated_at": report["generated_at"],
            "window_start": report.get("window_start"),
            "window_end": report.get("window_end"),
            "message_count": report.get("message_count", 0),
            "topic_count": len(topics),
            "card_count": len(cards),
            "headline": headline,
        })

    ordered = [
        {"date": day, "items": items}
        for day, items in sorted(groups.items(), reverse=True)
    ]
    return jsonify({"groups": ordered, "total": sum(len(i) for i in groups.values())})


@app.route("/api/reports/<int:report_id>")
def report_detail(report_id):
    """某一批报告的完整内容（话题 + 卡片 + 引用的原文）。"""
    report = repository().get_by_id(report_id)
    if report is None:
        return jsonify({"error": "没有这份报告"}), 404

    return jsonify({"report": report, "sources": _sources_for(report)})


@app.route("/api/feedback", methods=["POST"])
def feedback_vote():
    """给某条内容投"有用 / 无聊"。vote 传 0 表示取消。"""
    data = request.get_json(silent=True) or {}
    key = (data.get("key") or "").strip()
    if not key:
        return jsonify({"error": "缺少卡片标识"}), 400

    try:
        vote = int(data.get("vote") or 0)
    except (TypeError, ValueError):
        vote = 0

    feedback.save_vote(
        key,
        data.get("chat_id") or "",
        data.get("quote") or "",
        vote,
        data.get("type") or "",
    )
    return jsonify({"ok": True, "stats": feedback.stats()})


@app.route("/api/feedback/stats")
def feedback_stats():
    """你的口味：各类内容被点赞/点踩的次数。"""
    return jsonify(
        {
            "total": feedback.stats(),
            "by_type": feedback.stats_by_type(),
        }
    )


@app.route("/api/search")
def search():
    """按关键词搜消息和卡片。"""
    keyword = (request.args.get("q") or "").strip()
    if len(keyword) < 1:
        return jsonify({"query": "", "messages": [], "cards": [], "topics": []})

    try:
        limit = int(request.args.get("limit", 40))
    except (TypeError, ValueError):
        limit = 40
    limit = max(1, min(limit, 100))

    needle = keyword.lower()
    cards: list[dict] = []
    topics: list[dict] = []

    for report in repository().recent_reports(120):
        payload = report.get("payload") or {}
        for card in payload.get("cards") or []:
            haystack = f"{card.get('quote','')} {card.get('why','')}".lower()
            if needle in haystack:
                item = dict(card)
                item["chat_id"] = report["chat_id"]
                item["chat_name"] = report["chat_name"]
                item["generated_at"] = report["generated_at"]
                item["key"] = feedback.card_key(
                    report["chat_id"], card.get("message_ids")
                )
                cards.append(item)
        for topic in payload.get("digest") or []:
            haystack = f"{topic.get('title','')} {topic.get('summary','')}".lower()
            if needle in haystack:
                item = dict(topic)
                item["chat_id"] = report["chat_id"]
                item["chat_name"] = report["chat_name"]
                item["generated_at"] = report["generated_at"]
                topics.append(item)

    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT * FROM messages
            WHERE content LIKE ?
            ORDER BY timestamp DESC LIMIT ?
            """,
            (f"%{keyword}%", limit),
        ).fetchall()

    votes = feedback.get_votes()
    for card in cards:
        card["vote"] = votes.get(card["key"], 0)

    return jsonify(
        {
            "query": keyword,
            "cards": cards[:limit],
            "topics": topics[:limit],
            "messages": [_serialize_message(row) for row in rows],
        }
    )


@app.route("/api/health")
def health():
    """自检：数据表、接收端、队列、游标、报告、设置。"""
    return jsonify(health_report())


@app.route("/api/settings", methods=["GET", "POST"])
def app_settings():
    """自动总结开关与间隔，改完下一轮生效，重启不丢。"""
    if request.method == "GET":
        return jsonify(settings.get_all())

    payload = request.get_json(silent=True) or {}

    auto = payload.get("auto_analysis")
    interval = payload.get("interval_minutes")

    try:
        interval_value = None if interval is None else int(interval)
    except (TypeError, ValueError):
        return jsonify({"error": "间隔必须是整数（分钟）"}), 400

    return jsonify(
        settings.update(
            auto_analysis=None if auto is None else bool(auto),
            interval=interval_value,
        )
    )


@app.route("/api/chats/<chat_id>/coverage")
def coverage(chat_id):
    """这个群"从哪开始总结、还有多少条没看、哪几段时间没数据"。"""
    with get_connection() as connection:
        chat = connection.execute(
            """
            SELECT chat_id, MAX(chat_name) AS chat_name,
                   MIN(timestamp) AS first_message,
                   MAX(timestamp) AS last_message,
                   COUNT(*) AS total
            FROM messages WHERE chat_id = ? GROUP BY chat_id
            """,
            (chat_id,),
        ).fetchone()

        if chat is None:
            return jsonify({"error": "没有找到这个群聊"}), 404

        start = session_log.last_analyzed(chat_id) or chat["first_message"]
        pending = connection.execute(
            """
            SELECT COUNT(*) FROM messages
            WHERE chat_id = ? AND timestamp > ?
            """,
            (chat_id, start),
        ).fetchone()[0]

        account = connection.execute(
            """
            SELECT account_id FROM messages
            WHERE chat_id = ? AND account_id IS NOT NULL AND account_id != ''
            ORDER BY timestamp DESC LIMIT 1
            """,
            (chat_id,),
        ).fetchone()

    return jsonify({
        "chat_id": chat_id,
        "chat_name": chat["chat_name"],
        "from": start,
        "to": chat["last_message"],
        "pending": pending,
        "total": chat["total"],
        "account_id": account["account_id"] if account else None,
        "last_analyzed": session_log.last_analyzed(chat_id),
        "gaps": session_log.gaps(),
    })


@app.route("/api/chats/<chat_id>/summarize", methods=["POST"])
def summarize(chat_id):
    """按游标总结：只处理"上次总结之后"的新消息。"""
    lock = _lock_for(chat_id)
    if not lock.acquire(blocking=False):
        return jsonify({"error": "该群正在生成，请稍候"}), 409

    try:
        with get_connection() as connection:
            chat = connection.execute(
                "SELECT chat_id, MAX(chat_name) AS chat_name, MIN(timestamp) AS first_message "
                "FROM messages WHERE chat_id = ? GROUP BY chat_id",
                (chat_id,),
            ).fetchone()

            if chat is None:
                return jsonify({"error": "没有找到这个群聊"}), 404

            start = session_log.last_analyzed(chat_id) or chat["first_message"]
            if start is None:
                return jsonify({"error": "这个群还没有消息"}), 400

            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE chat_id = ? AND timestamp > ?
                ORDER BY timestamp ASC LIMIT 300
                """,
                (chat_id, start),
            ).fetchall()

        if not rows:
            return jsonify({
                "message": "上次总结之后没有新消息",
                "from": start,
                "covered": 0,
            })

        messages = [
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

        # 从"最旧的未总结消息"往前推进：离开很久回来时，先看最早那段，再一批批往后。
        window = messages[:MAX_MESSAGES]

        try:
            client = ZhipuAIClient()
        except ValueError as exc:
            return jsonify({"error": f"AI 配置不完整：{exc}"}), 400

        try:
            report = generate_feed(client, window)
        except FeedGenerationError as exc:
            return jsonify({"error": f"分析失败：{exc}"}), 502
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": f"调用 AI 失败：{exc}"}), 502

        report_id = repository().save(chat_id, chat["chat_name"], report)
        session_log.set_analyzed(chat_id, window[-1].timestamp.isoformat())
        MessageRepository().mark_analyzed([message.id for message in window])

        return jsonify({
            "report": repository().get_latest(chat_id),
            "report_id": report_id,
            "from": start,
            "to": window[-1].timestamp.isoformat(),
            "covered": len(window),
            "remaining": max(0, len(messages) - len(window)),
            "gaps": session_log.gaps(),
        })
    finally:
        lock.release()


@app.route("/api/chats/<chat_id>")
def chat_detail(chat_id):
    limit = request.args.get("limit", default=100, type=int)
    limit = max(1, min(limit, 500))

    with get_connection() as connection:
        chat = connection.execute(
            """
            SELECT
                chat_id,
                MAX(chat_name) AS chat_name,
                COUNT(*) AS message_count,
                MAX(timestamp) AS last_message_time
            FROM messages
            WHERE chat_id = ?
            GROUP BY chat_id
            """,
            (chat_id,),
        ).fetchone()

        if chat is None:
            return jsonify({"error": "没有找到这个群聊"}), 404

        messages = connection.execute(
            """
            SELECT * FROM messages
            WHERE chat_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()

    report = repository().get_latest(chat_id)

    return jsonify({
        "chat": dict(chat),
        # 按时间正序返回，和聊天记录阅读顺序一致。
        "messages": [
            _serialize_message(row) for row in reversed(messages)
        ],
        "report": report,
        "sources": _sources_for(report),
    })


@app.route("/api/chats/<chat_id>/analyze", methods=["POST"])
def analyze_chat(chat_id):
    payload = request.get_json(silent=True) or {}
    requested = payload.get("limit", MAX_MESSAGES)
    try:
        limit = max(1, min(int(requested), 200))
    except (TypeError, ValueError):
        limit = MAX_MESSAGES

    lock = _lock_for(chat_id)
    if not lock.acquire(blocking=False):
        return jsonify({"error": "该群正在生成分析，请稍候再试"}), 409

    try:
        with get_connection() as connection:
            chat = connection.execute(
                """
                SELECT chat_id, MAX(chat_name) AS chat_name
                FROM messages
                WHERE chat_id = ?
                GROUP BY chat_id
                """,
                (chat_id,),
            ).fetchone()

            if chat is None:
                return jsonify({"error": "没有找到这个群聊"}), 404

            rows = connection.execute(
                """
                SELECT * FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (chat_id,),
            ).fetchall()

        messages = [
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

        if not messages:
            return jsonify({"error": "这个群还没有消息，无法分析"}), 400

        try:
            client = ZhipuAIClient()
        except ValueError as exc:
            return jsonify({"error": f"AI 配置不完整：{exc}"}), 400

        try:
            report = generate_feed(client, messages[-limit:])
        except FeedGenerationError as exc:
            return jsonify({"error": f"分析失败：{exc}"}), 502
        except Exception as exc:  # 网络 / 鉴权 / 限流等
            return jsonify({"error": f"调用 AI 失败：{exc}"}), 502

        report_id = repository().save(
            chat_id,
            chat["chat_name"],
            report,
        )

        saved = repository().get_latest(chat_id)

        return jsonify({
            "report": saved,
            "report_id": report_id,
            "sources": _sources_for(saved),
        })

    except sqlite3.Error as exc:
        return jsonify({"error": f"数据库错误：{exc}"}), 500
    finally:
        lock.release()
