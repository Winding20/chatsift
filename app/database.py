
import sqlite3
from pathlib import Path

from app.config import BASE_DIR, get_data_dir


DATABASE_PATH = get_data_dir() / "assistant.db"


def get_connection() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    return connection


def init_database() -> None:
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                chat_name TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                sender_name TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                account_id TEXT
            )
        """)

        # 老库补列：记录收到这条消息时登录的 QQ 号
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(messages)")
        }
        if "account_id" not in columns:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN account_id TEXT"
            )

        connection.execute("""
            CREATE TABLE IF NOT EXISTS chat_summaries (
                chat_id TEXT PRIMARY KEY,
                chat_name TEXT NOT NULL,
                summary TEXT NOT NULL,
                message_ids TEXT NOT NULL DEFAULT '[]',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS analysis_queue (
                message_id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id)
                    REFERENCES messages(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_analysis_queue_chat_status
            ON analysis_queue (chat_id, status, created_at)
        """)

        # 结构化分析报告：每次生成追加一行，不覆盖历史，便于回看。
        # 与旧的 chat_summaries 表并存，旧表不做任何修改。
        connection.execute("""
            CREATE TABLE IF NOT EXISTS analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                chat_name TEXT NOT NULL,
                generated_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime')),
                window_start TEXT,
                window_end TEXT,
                message_count INTEGER NOT NULL DEFAULT 0,
                model TEXT,
                dropped INTEGER NOT NULL DEFAULT 0,
                payload TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_analysis_reports_chat_id
            ON analysis_reports (chat_id, id DESC)
        """)

        # 用户对卡片的反馈：有用 / 无聊
        connection.execute("""
            CREATE TABLE IF NOT EXISTS card_feedback (
                card_key TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL DEFAULT '',
                quote TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL DEFAULT '',
                vote INTEGER NOT NULL,
                created_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now', 'localtime'))
            )
        """)

        # 老库补列：记录卡片类型，用来统计口味
        feedback_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(card_feedback)")
        }
        if "type" not in feedback_columns:
            connection.execute(
                "ALTER TABLE card_feedback ADD COLUMN type TEXT NOT NULL DEFAULT ''"
            )

        # 接收端每次连接/断开都记一行：这是判断"哪段时间没有数据"的唯一依据。
        connection.execute("""
            CREATE TABLE IF NOT EXISTS connection_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connected_at TEXT NOT NULL,
                disconnected_at TEXT
            )
        """)

        # 每个群"上次总结到哪"：手动按钮和后台定时共用这一个游标。
        connection.execute("""
            CREATE TABLE IF NOT EXISTS analysis_cursors (
                chat_id TEXT PRIMARY KEY,
                last_analyzed_at TEXT NOT NULL
            )
        """)

        # 页面上的开关：是否自动总结、间隔多少分钟。存在库里，重启不丢。
        connection.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        connection.commit()
