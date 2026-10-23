"""后台自动分析：把"采集"和"分析"彻底分开。

接收端只负责入库（写 messages + analysis_queue），
这个循环只负责把队列里的消息变成"值得看的内容"。
失败会记录、会退避，超过上限就停放，不再无限重试。

单轮会对每个群连续处理多批（默认 4 批），并且限制整轮的 AI 调用次数，
既能把积压追平，又不会一轮跑飞。
"""

from __future__ import annotations

import logging
import threading

from app import session_log, settings
from app.ai_client import ZhipuAIClient
from app.feed_generator import EmptyBatchError, generate
from app.report_repository import AnalysisReportRepository
from app.repositories import MessageRepository

log = logging.getLogger("assistant.scheduler")

DEFAULT_BATCHES_PER_CHAT = 10
DEFAULT_MAX_CALLS_PER_CYCLE = 24


def _is_content_filter_error(error: Exception) -> bool:
    """识别智谱的内容审查拒绝（HTTP 400 / 1301）。"""
    message = str(error)
    return (
        "1301" in message
        or "contentFilter" in message
        or "内容可能包含不安全" in message
        or "敏感内容" in message
    )


class AnalysisScheduler:
    def __init__(
        self,
        repository: MessageRepository | None = None,
        reports: AnalysisReportRepository | None = None,
        client_factory=ZhipuAIClient,
        interval: float = 300.0,
        window: int = 100,
        max_attempts: int = 5,
        batches_per_chat: int = DEFAULT_BATCHES_PER_CHAT,
        max_calls_per_cycle: int = DEFAULT_MAX_CALLS_PER_CYCLE,
        on_run=None,
    ) -> None:
        self.repository = repository or MessageRepository()
        self.reports = reports or AnalysisReportRepository()
        self.client_factory = client_factory
        self.interval = max(1.0, float(interval))
        self.window = max(1, int(window))
        self.max_attempts = max(1, int(max_attempts))
        self.batches_per_chat = max(1, int(batches_per_chat))
        self.max_calls_per_cycle = max(1, int(max_calls_per_cycle))
        self.on_run = on_run

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # --- 单轮 ---------------------------------------------------------

    def run_once(self) -> dict:
        """跑一轮，返回统计。异常不会抛出，只记日志。"""
        stats = {
            "chats": 0,
            "batches": 0,
            "analyzed": 0,
            "failed": 0,
            "parked": 0,
            "skipped": 0,
            "cards": 0,
        }

        try:
            client = self.client_factory()
        except Exception as exc:  # 配置缺失 / 网络不可用
            log.error("AI 客户端初始化失败，本轮跳过：%s", exc)
            return stats

        budget = [self.max_calls_per_cycle]

        for chat_id in self.repository.get_pending_chat_ids():
            if budget[0] <= 0:
                log.info("本轮调用额度用完，剩下的留到下一轮")
                break

            pending = self.repository.get_pending_by_chat(chat_id)
            if not pending:
                continue

            stats["chats"] += 1

            attempts = self.repository.get_pending_attempts(chat_id)
            if attempts >= self.max_attempts:
                self.repository.mark_failed(
                    [message.id for message in pending],
                    f"已重试 {attempts} 次仍未成功，暂停处理",
                )
                stats["parked"] += 1
                log.warning("群 %s 重试 %s 次，已停放 %s 条", chat_id, attempts, len(pending))
                continue

            # 连续处理多批，追平积压；每批都重新取，避免重复分析
            for _ in range(self.batches_per_chat):
                if budget[0] <= 0:
                    break

                pending = self.repository.get_pending_by_chat(chat_id)
                if not pending:
                    break

                batch = pending[: self.window]
                if not self._run_batch(client, chat_id, batch, attempts, stats, budget):
                    break

        if self.on_run is not None:
            try:
                self.on_run(stats)
            except Exception:  # noqa: BLE001
                log.exception("on_run 回调出错")

        return stats

    def _run_batch(
        self,
        client,
        chat_id: str,
        batch,
        attempts: int,
        stats: dict,
        budget: list[int],
        depth: int = 0,
    ) -> bool:
        if not batch or budget[0] <= 0:
            return False

        budget[0] -= 1
        stats["batches"] += 1

        try:
            report = generate(client, batch)
        except EmptyBatchError:
            # 整批都是占位符/链接：不算失败，直接消费掉，避免无限重试。
            self.repository.mark_analyzed([message.id for message in batch])
            stats["skipped"] += 1
            log.info("群 %s 这批 %s 条全是噪声，跳过", chat_id, len(batch))
            return True
        except Exception as exc:  # noqa: BLE001 — 任何失败都要落库并重试
            # 内容过滤会把整批打回来：对半拆开，把触发的那几条隔离掉
            if _is_content_filter_error(exc) and len(batch) > 4 and depth < 5:
                middle = len(batch) // 2
                log.info(
                    "群 %s 触发内容过滤，拆成 %s + %s 条重试",
                    chat_id, middle, len(batch) - middle,
                )
                left_ok = self._run_batch(
                    client, chat_id, batch[:middle], attempts, stats, budget, depth + 1
                )
                right_ok = self._run_batch(
                    client, chat_id, batch[middle:], attempts, stats, budget, depth + 1
                )
                return left_ok and right_ok

            if _is_content_filter_error(exc) and len(batch) <= 4:
                # 已经拆到很小还是被拦：放弃这几条，别拖累整个群
                self.repository.mark_analyzed([message.id for message in batch])
                stats["skipped"] += 1
                log.warning("群 %s 有 %s 条始终被内容过滤，跳过", chat_id, len(batch))
                return True

            self.repository.record_analysis_failure(
                [message.id for message in batch], str(exc)
            )
            stats["failed"] += 1
            log.warning("群 %s 分析失败（第 %s 次）：%s", chat_id, attempts + 1, exc)
            return False

        if not report.payload.get("cards"):
            # 这批没挑到东西：消费掉消息，但不要用空报告盖掉之前的内容。
            self.repository.mark_analyzed([message.id for message in batch])
            stats["skipped"] += 1
            log.info("群 %s 这批没有值得留的内容，跳过保存", chat_id)
            return True

        self.reports.save(chat_id, batch[-1].chat_name, report)
        session_log.set_analyzed(chat_id, batch[-1].timestamp.isoformat())
        self.repository.mark_analyzed([message.id for message in batch])

        stats["analyzed"] += 1
        stats["cards"] += len(report.payload.get("cards") or [])
        log.info(
            "群 %s 产出 %s 条内容（覆盖 %s 条消息）",
            chat_id,
            len(report.payload.get("cards") or []),
            report.message_count,
        )
        return True

    # --- 循环 ---------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="analysis-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            # 每轮都重新读设置：页面上改完开关/间隔，下一轮就生效。
            try:
                enabled = settings.auto_enabled()
            except Exception:  # noqa: BLE001
                log.exception("读取设置失败，按开启处理")
                enabled = True

            if enabled:
                try:
                    self.run_once()
                except Exception:  # noqa: BLE001
                    log.exception("调度器单轮异常")

            try:
                wait = settings.interval_seconds()
            except Exception:  # noqa: BLE001
                wait = self.interval

            if self._stop.wait(wait):
                break
