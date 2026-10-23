"""换分析逻辑后，把历史失败计数清零，让积压消息再试一次。

用法：
    python tools/reset_queue.py          # 只重置重试过的
    python tools/reset_queue.py --failed # 只重置已停放的
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import DATABASE_PATH, get_connection, init_database  # noqa: E402


def main() -> None:
    only_failed = "--failed" in sys.argv

    init_database()

    with get_connection() as connection:
        if only_failed:
            cursor = connection.execute(
                """
                UPDATE analysis_queue
                SET status = 'pending', attempts = 0, last_error = NULL
                WHERE status = 'failed'
                """
            )
        else:
            cursor = connection.execute(
                """
                UPDATE analysis_queue
                SET status = 'pending', attempts = 0, last_error = NULL
                WHERE attempts > 0
                """
            )
        remaining = connection.execute(
            "SELECT COUNT(*) FROM analysis_queue WHERE status = 'pending'"
        ).fetchone()[0]

    print(f"数据库：{DATABASE_PATH}")
    print(f"重置 {cursor.rowcount} 条，当前待分析 {remaining} 条")


if __name__ == "__main__":
    main()
