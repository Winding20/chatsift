from datetime import datetime

from app.models import Message


def test_message_creation():
    message = Message(
        id="1",
        source="test",
        chat_id="group_001",
        chat_name="测试群",
        sender_id="user_001",
        sender_name="张三",
        content="你好",
        timestamp=datetime.now(),
    )

    assert message.id == "1"
    assert message.chat_name == "测试群"
    assert message.sender_name == "张三"
    assert message.content == "你好"
