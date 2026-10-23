"""自检：把"现在到底怎么了"整理成结构化结果。

网页的「自检」按钮和命令行 tools/doctor.py 都调用这里，只有一份逻辑。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from app import feedback, noise
from app.database import DATABASE_PATH, init_database


EXPECTED_TABLES = {
    "messages",
    "analysis_queue",
    "analysis_reports",
    "connection_events",
    "analysis_cursors",
    "settings",
}


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _ago(seconds: float) -> str:
    if seconds < 90:
        return f"{int(seconds)} 秒前"
    if seconds < 5400:
        return f"{int(seconds / 60)} 分钟前"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} 小时前"
    return f"{seconds / 86400:.1f} 天前"


def _span(seconds: float) -> str:
    if seconds < 3600:
        return f"{int(seconds / 60)} 分钟"
    if seconds < 172800:
        return f"{seconds / 3600:.1f} 小时"
    return f"{seconds / 86400:.1f} 天"


def report() -> dict:
    init_database()
    now = datetime.now()
    items: list[dict] = []
    warnings: list[str] = []

    def add(key: str, label: str, state: str, value: str) -> None:
        items.append({"key": key, "label": label, "state": state, "value": value})

    if not DATABASE_PATH.exists():
        return {
            "ok": False,
            "checked_at": now.isoformat(),
            "items": [
                {
                    "key": "db",
                    "label": "数据库",
                    "state": "error",
                    "value": "不存在",
                }
            ],
            "warnings": ["数据库文件不存在"],
        }

    con = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    def setting(key: str, default: str) -> str:
        row = con.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return default if row is None else row["value"]

    auto_on = setting("auto_analysis", "1").strip() not in (
        "0",
        "false",
        "no",
        "off",
    )

    add("db", "数据库", "ok", f"{DATABASE_PATH.stat().st_size / 1024:.0f} KB")

    # 数据表
    tables = {
        row["name"]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = EXPECTED_TABLES - tables
    add(
        "tables",
        "数据表",
        "error" if missing else "ok",
        f"{len(tables)} 张" + (f"，缺 {', '.join(sorted(missing))}" if missing else ""),
    )
    if missing:
        warnings.append(f"缺少数据表：{', '.join(sorted(missing))}")

    # 消息
    total = con.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    chats = con.execute("SELECT COUNT(DISTINCT chat_id) FROM messages").fetchone()[0]
    latest = _parse(con.execute("SELECT MAX(timestamp) FROM messages").fetchone()[0])
    idle = (now - latest).total_seconds() if latest else None
    add(
        "messages",
        "消息",
        "ok",
        f"{total} 条 / {chats} 个群" + (f"，最新 {_ago(idle)}" if idle is not None else ""),
    )
    if idle is not None and idle > 86400:
        warnings.append(f"已经 {_span(idle)} 没有新消息，检查 NapCat 是否还连着")

    # 接收端
    event = con.execute(
        "SELECT connected_at, disconnected_at FROM connection_events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if event is None:
        add("receiver", "接收端", "warn", "没有连接记录")
        warnings.append("接收端从未连接过（NapCat 可能没连上）")
    else:
        online = event["disconnected_at"] is None
        since = _parse(event["connected_at"])
        text = "在线" if online else "离线"
        if online and since:
            text += f"（连接于 {_ago((now - since).total_seconds())}）"
        if not online:
            down = _parse(event["disconnected_at"])
            if down:
                text += f"（{_ago((now - down).total_seconds())}）"
                warnings.append(f"接收端已离线 {_span((now - down).total_seconds())}")
        add("receiver", "接收端", "ok" if online else "warn", text)

    # 当前登录的 QQ（OneBot 的 self_id）
    account_row = con.execute(
        """
        SELECT account_id, MAX(timestamp) AS last
        FROM messages
        WHERE account_id IS NOT NULL AND account_id != ''
        GROUP BY account_id
        ORDER BY last DESC
        LIMIT 1
        """
    ).fetchone()
    if account_row is None:
        add("account", "接收账号", "info", "还没记录（旧消息没有账号信息）")
    else:
        last = _parse(account_row["last"])
        ago = _ago((now - last).total_seconds()) if last else ""
        add("account", "接收账号", "ok", f"{account_row['account_id']}（最近消息 {ago}）")
        history_accounts = con.execute(
            """
            SELECT COUNT(DISTINCT account_id) FROM messages
            WHERE account_id IS NOT NULL AND account_id != ''
            """
        ).fetchone()[0]
        if history_accounts > 1:
            add(
                "accounts",
                "账号历史",
                "info",
                f"库里有 {history_accounts} 个账号收过消息",
            )

    # 机器人过滤（最近一批的统计）
    if noise.LAST.get("count"):
        names = "、".join(noise.LAST.get("senders") or [])[:40]
        add(
            "bots",
            "机器人",
            "info",
            f"最近一批过滤了 {noise.LAST['count']} 条（{names}）",
        )

    # 口味反馈
    try:
        counts = feedback.stats()
        if counts["good"] or counts["bad"]:
            add(
                "feedback",
                "反馈",
                "info",
                f"有用 {counts['good']} 条 · 无聊 {counts['bad']} 条",
            )
    except Exception:  # noqa: BLE001 — 反馈读不出来不影响其它检查
        pass

    # 队列
    pending = con.execute(
        "SELECT COUNT(*) FROM analysis_queue WHERE status='pending'"
    ).fetchone()[0]
    failed = con.execute(
        "SELECT COUNT(*) FROM analysis_queue WHERE status='failed'"
    ).fetchone()[0]
    oldest = _parse(
        con.execute(
            "SELECT MIN(created_at) FROM analysis_queue WHERE status='pending'"
        ).fetchone()[0]
    )
    text = f"待分析 {pending} 条，失败停放 {failed} 条"
    state = "ok"
    if oldest and pending:
        waited = (now - oldest).total_seconds()
        text += f"，最老等了 {_span(waited)}"
        if auto_on and waited > 7200:
            state = "warn"
            warnings.append(f"{pending} 条消息等了超过 2 小时还没分析")
    if failed:
        state = "warn"
        warnings.append(f"有 {failed} 条消息分析失败后被停放")
    add("queue", "队列", state, text)

    # 游标落后
    lag: list[tuple[str, int]] = []
    for row in con.execute(
        """
        SELECT m.chat_id, MAX(m.chat_name) AS name
        FROM messages AS m GROUP BY m.chat_id
        """
    ):
        cursor = con.execute(
            "SELECT last_analyzed_at FROM analysis_cursors WHERE chat_id = ?",
            (row["chat_id"],),
        ).fetchone()
        if cursor is None:
            behind = con.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ?", (row["chat_id"],)
            ).fetchone()[0]
        else:
            behind = con.execute(
                "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND timestamp > ?",
                (row["chat_id"], cursor["last_analyzed_at"]),
            ).fetchone()[0]
        if behind:
            lag.append((row["name"] or row["chat_id"], behind))

    lag.sort(key=lambda item: item[1], reverse=True)
    if lag:
        top = "、".join(f"{name} {count} 条" for name, count in lag[:2])
        add("cursor", "游标", "info", f"{len(lag)} 个群未总结，最多：{top}")
        if auto_on and lag[0][1] > 200:
            warnings.append(f"{lag[0][0]} 积压 {lag[0][1]} 条未总结")
    else:
        add("cursor", "游标", "ok", "所有群都已总结到最新")

    # 报告
    reports = con.execute("SELECT COUNT(*) FROM analysis_reports").fetchone()[0]
    covered = con.execute(
        "SELECT COUNT(DISTINCT chat_id) FROM analysis_reports"
    ).fetchone()[0]
    newest = _parse(
        con.execute("SELECT MAX(generated_at) FROM analysis_reports").fetchone()[0]
    )
    text = f"{reports} 份，覆盖 {covered} 个群"
    if newest:
        text += f"，最新 {_ago((now - newest).total_seconds())}"
        if (now - newest).total_seconds() > 172800:
            warnings.append("已经两天没有生成过新报告")
    add("reports", "报告", "ok", text)

    # 设置
    interval = setting("analysis_interval_minutes", "未设置")
    add(
        "settings",
        "设置",
        "ok",
        f"自动总结：{'开' if auto_on else '关'}，间隔 {interval} 分钟",
    )

    con.close()

    return {
        "ok": not warnings,
        "checked_at": now.isoformat(),
        "items": items,
        "warnings": warnings,
    }
