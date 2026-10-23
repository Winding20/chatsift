from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.feed_generator import EmptyBatchError
from app.models import Message
from app.scheduler import AnalysisScheduler


BASE = datetime(2026, 10, 23, 20, 0, 0)


def make_messages(count: int, chat_id: str = "c1", offset: int = 0) -> list[Message]:
    return [
        Message(
            id=f"{chat_id}-{index + offset}",
            source="qq",
            chat_id=chat_id,
            chat_name="测试群",
            sender_id="u1",
            sender_name="老王",
            content=f"消息 {index + offset}",
            timestamp=BASE + timedelta(seconds=index + offset),
        )
        for index in range(count)
    ]


class FakeRepository:
    def __init__(self, messages: list[Message]) -> None:
        self.pending = {message.id: message for message in messages}
        self.analyzed: list[str] = []
        self.failed: list[str] = []

    def get_pending_chat_ids(self):
        return sorted({message.chat_id for message in self.pending.values()})

    def get_pending_by_chat(self, chat_id):
        return sorted(
            (m for m in self.pending.values() if m.chat_id == chat_id),
            key=lambda m: (m.timestamp, m.id),
        )

    def get_pending_attempts(self, chat_id):
        return 0

    def mark_analyzed(self, ids):
        for message_id in ids:
            self.pending.pop(message_id, None)
            self.analyzed.append(message_id)

    def mark_failed(self, ids, reason):
        self.failed.extend(ids)

    def record_analysis_failure(self, ids, error):
        self.failed.extend(ids)


class FakeReport:
    def __init__(self, count: int) -> None:
        self.payload = {"cards": [{"type": "knowledge"}]}
        self.message_count = count


class FakeReports:
    def __init__(self) -> None:
        self.saved = 0

    def save(self, chat_id, chat_name, report):
        self.saved += 1


class FakeClient:
    pass


@pytest.fixture
def factory():
    return lambda: FakeClient()


def build(messages, factory, **kwargs):
    repository = FakeRepository(messages)
    reports = FakeReports()
    scheduler = AnalysisScheduler(
        repository=repository,
        reports=reports,
        client_factory=factory,
        window=100,
        **kwargs,
    )
    return scheduler, repository, reports


def test_processes_multiple_batches_per_chat(monkeypatch):
    calls = []

    def fake_generate(client, batch):
        calls.append(len(batch))
        return FakeReport(len(batch))

    monkeypatch.setattr("app.scheduler.generate", fake_generate)
    monkeypatch.setattr("app.scheduler.session_log.set_analyzed", lambda *a, **k: None)

    scheduler, repository, reports = build(
        make_messages(250), lambda: FakeClient(), batches_per_chat=4
    )
    stats = scheduler.run_once()

    assert len(calls) == 3          # 250 → 100 + 100 + 50
    assert stats["batches"] == 3
    assert stats["analyzed"] == 3
    assert reports.saved == 3
    assert len(repository.pending) == 0


def test_call_budget_stops_cycle(monkeypatch):
    calls = []

    def fake_generate(client, batch):
        calls.append(len(batch))
        return FakeReport(len(batch))

    monkeypatch.setattr("app.scheduler.generate", fake_generate)
    monkeypatch.setattr("app.scheduler.session_log.set_analyzed", lambda *a, **k: None)

    scheduler, repository, _ = build(
        make_messages(300), lambda: FakeClient(),
        batches_per_chat=4, max_calls_per_cycle=2,
    )
    stats = scheduler.run_once()

    assert len(calls) == 2
    assert stats["batches"] == 2
    assert len(repository.pending) == 100   # 剩下的留到下一轮


def test_empty_batch_is_consumed(monkeypatch):
    def fake_generate(client, batch):
        raise EmptyBatchError("全是噪声")

    monkeypatch.setattr("app.scheduler.generate", fake_generate)

    scheduler, repository, reports = build(make_messages(30), lambda: FakeClient())
    stats = scheduler.run_once()

    assert stats["skipped"] == 1
    assert len(repository.pending) == 0
    assert reports.saved == 0


def test_no_cards_does_not_save_report(monkeypatch):
    class EmptyReport:
        payload = {"cards": []}
        message_count = 10

    monkeypatch.setattr("app.scheduler.generate", lambda c, b: EmptyReport())

    scheduler, repository, reports = build(make_messages(10), lambda: FakeClient())
    stats = scheduler.run_once()

    assert stats["skipped"] == 1
    assert reports.saved == 0
    assert len(repository.pending) == 0
