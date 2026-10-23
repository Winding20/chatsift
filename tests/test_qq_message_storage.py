from app.models import Message
from app.qq_collector import QQMessageCollector
from app.repositories import MessageRepository


def test_qq_message_can_be_stored():
    event = {
        "post_type": "message",
        "message_type": "group",
        "message_id": "qq-storage-test-001",
        "group_id": "group_001",
        "group_name": "测试群",
        "user_id": "user_001",
        "nickname": "张三",
        "message": "这是一条来自QQ的测试消息",
    }

    message = QQMessageCollector.from_event(event)

    assert isinstance(message, Message)

    repository = MessageRepository()
    repository.save(message)

    messages = repository.get_by_chat("group_001")

    assert any(
        item["id"] == "qq-storage-test-001"
        and item["content"] == "这是一条来自QQ的测试消息"
        for item in messages
    )