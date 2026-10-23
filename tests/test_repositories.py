from datetime import datetime

from app.models import Message
from app.repositories import MessageRepository


def test_repository_save_and_get_by_chat():
    repository = MessageRepository()

    message = Message(
        id="repo-test-001",
        source="test",
        chat_id="group_001",
        chat_name="测试群",
        sender_id="user_001",
        sender_name="张三",
        content="Repository 测试消息",
        timestamp=datetime.now(),
    )

    repository.save(message)

    messages = repository.get_by_chat("group_001")

    assert len(messages) == 1
    assert messages[0]["id"] == "repo-test-001"
    assert messages[0]["content"] == "Repository 测试消息"

def test_repository_save_adds_message_to_analysis_queue():
    repository = MessageRepository()

    message = Message(
        id="repo-queue-test-001",
        source="test",
        chat_id="group_queue_test",
        chat_name="队列测试群",
        sender_id="user_queue_test",
        sender_name="队列测试用户",
        content="验证消息是否进入待分析队列",
        timestamp=datetime.now(),
    )

    inserted = repository.save(message)

    assert inserted is True

    pending_messages = repository.get_pending_by_chat(
        "group_queue_test"
    )

    assert any(
        item.id == message.id
        for item in pending_messages
    )
