"""一条命令启动全部：网页面板 + QQ 接收端 + 后台分析。

用法：
    python run.py            启动全部
    python run.py --once     只跑一轮分析（把积压的消息处理掉）
    python run.py --no-scheduler   只开接收端和面板，不自动花钱
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import threading

from app.config import (
    get_analysis_interval,
    get_analysis_max_attempts,
    get_analysis_window,
    get_auto_analysis,
    get_web_host,
    get_web_port,
)
from app.database import init_database
from app.scheduler import AnalysisScheduler
from app.service import serve
from app.web_app import app


log = logging.getLogger("assistant")


def _start_web(host: str, port: int) -> None:
    app.run(
        host=host,
        port=port,
        debug=False,
        use_reloader=False,
        threaded=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="个人 AI 助手")
    parser.add_argument(
        "--once",
        action="store_true",
        help="只跑一轮后台分析，然后退出",
    )
    parser.add_argument(
        "--no-scheduler",
        action="store_true",
        help="不启动后台自动分析",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    init_database()

    # 每天第一次启动时备份一次数据库
    try:
        from app.backup import maybe_daily_backup

        saved = maybe_daily_backup()
        if saved:
            log.info("已备份数据库：%s", saved)
    except Exception as exc:  # noqa: BLE001 — 备份失败不该挡住启动
        log.warning("备份失败：%s", exc)

    scheduler = AnalysisScheduler(
        interval=get_analysis_interval(),
        window=get_analysis_window(),
        max_attempts=get_analysis_max_attempts(),
    )

    if args.once:
        stats = scheduler.run_once()
        log.info("本轮结果：%s", stats)
        return

    if not args.no_scheduler and get_auto_analysis():
        scheduler.start()
        log.info("后台分析已启动，每 %s 秒一轮", int(get_analysis_interval()))

    host, port = get_web_host(), get_web_port()
    threading.Thread(
        target=_start_web,
        args=(host, port),
        name="web",
        daemon=True,
    ).start()
    log.info("面板：http://%s:%s", host, port)

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        log.info("收到中断，正在退出")
    finally:
        scheduler.stop()


if __name__ == "__main__":
    main()
