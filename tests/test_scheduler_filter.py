from __future__ import annotations

import pytest

from app.models import Message
from app.scheduler import AnalysisScheduler
from tests.test_scheduler import (
    FakeClient,
    FakeReports,
    FakeRepository,
    FakeReport,
    make_messages,
)

FILTER_ERROR = (
    "Error code: 400 - {'contentFilter': [{'level': 1}], "
    "'error': {'code': '1301', 'message': '内容可能包含不安全或敏感内容'}}"
)


def build(messages, **kwargs):
    repository = FakeRepository(messages)
    reports = FakeReports()
    scheduler = AnalysisScheduler(
        repository=repository,
        reports=reports,
        client_factory=lambda: FakeClient(),
        window=100,
        **kwargs,
    )
    return scheduler, repository, reports


def test_filter_error_splits_and_salvages(monkeypatch):
    """整批被过滤时，对半拆开，把没问题的部分救回来。"""
    calls = []

    def fake_generate(client, batch):
        calls.append(len(batch))
        if any(m.content == "敏感" for m in batch):
            raise RuntimeError(FILTER_ERROR)
        return FakeReport(len(batch))

    monkeypatch.setattr("app.scheduler.generate", fake_generate)
    monkeypatch.setattr("app.scheduler.session_log.set_analyzed", lambda *a, **k: None)

    messages = make_messages(64)
    messages[10] = Message(
        id=messages[10].id,
        source="qq",
        chat_id=messages[10].chat_id,
        chat_name=messages[10].chat_name,
        sender_id="u1",
        sender_name="老王",
        content="敏感",
        timestamp=messages[10].timestamp,
    )

    scheduler, repository, reports = build(messages, batches_per_chat=10)
    stats = scheduler.run_once()

    # 拆到最后一层，那条敏感消息被单独跳过
    assert stats["skipped"] >= 1
    assert stats["analyzed"] >= 1
    assert len(calls) > 1
    assert len(repository.pending) == 0


def test_filter_error_on_tiny_batch_is_skipped(monkeypatch):
    def fake_generate(client, batch):
        raise RuntimeError(FILTER_ERROR)

    monkeypatch.setattr("app.scheduler.generate", fake_generate)

    scheduler, repository, reports = build(make_messages(3))
    stats = scheduler.run_once()

    assert stats["skipped"] == 1
    assert len(repository.pending) == 0      # 小批次直接放弃，不卡住队列
    assert reports.saved == 0


def test_non_filter_error_still_counts_as_failure(monkeypatch):
    def fake_generate(client, batch):
        raise RuntimeError("连接超时")

    monkeypatch.setattr("app.scheduler.generate", fake_generate)

    scheduler, repository, _ = build(make_messages(20))
    stats = scheduler.run_once()

    assert stats["failed"] == 1
    assert len(repository.pending) == 20     # 留在队列里等重试
