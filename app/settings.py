"""运行时可改的设置：自动总结开关、总结间隔。

优先级：数据库里的设置 > .env > 代码默认值。
这样页面上改完立刻生效，重启也不会丢。
"""

from __future__ import annotations

from app.config import get_analysis_interval, get_auto_analysis
from app.database import get_connection, init_database


MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 1440


def _read(key: str) -> str | None:
    init_database()
    with get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()

    return None if row is None else row["value"]


def _write(key: str, value: str) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def auto_enabled() -> bool:
    stored = _read("auto_analysis")
    if stored is None:
        return get_auto_analysis()
    return stored.strip() not in ("0", "false", "no", "off")


def interval_minutes() -> int:
    stored = _read("analysis_interval_minutes")
    if stored is not None:
        try:
            value = int(float(stored))
        except (TypeError, ValueError):
            value = 0
        if MIN_INTERVAL_MINUTES <= value <= MAX_INTERVAL_MINUTES:
            return value

    return max(MIN_INTERVAL_MINUTES, int(round(get_analysis_interval() / 60)))


def interval_seconds() -> float:
    return interval_minutes() * 60.0


def get_all() -> dict:
    return {
        "auto_analysis": auto_enabled(),
        "interval_minutes": interval_minutes(),
        "min_interval_minutes": MIN_INTERVAL_MINUTES,
        "max_interval_minutes": MAX_INTERVAL_MINUTES,
    }


def update(auto_analysis=None, interval: int | None = None) -> dict:
    if auto_analysis is not None:
        _write("auto_analysis", "1" if auto_analysis else "0")

    if interval is not None:
        value = max(MIN_INTERVAL_MINUTES, min(MAX_INTERVAL_MINUTES, int(interval)))
        _write("analysis_interval_minutes", str(value))

    return get_all()
