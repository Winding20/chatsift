from datetime import datetime

from app.models import Message
from app.repositories import MessageRepository


def create_message() -> Message:
    return Message(
        id="dedup-test-001",
        source="qq",
        chat_id="dedup-group",
        chat_name="去重测试群",
        sender_id="user-001",
        sender_name="张三",
        content="这是一条重复测试消息",
        timestamp=datetime.now(),
    )


def test_duplicate_message_is_ignored():
    repository = MessageRepository()

    message = create_message()

    repository.save(message)
    repository.save(message)

    messages = repository.get_by_chat(
        "dedup-group",
        limit=100,
    )

    matching_messages = [
        item
        for item in messages
        if item["id"] == "dedup-test-001"
    ]

    assert len(matching_messages) == 1