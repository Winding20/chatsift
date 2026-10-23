from app.qq_collector import QQMessageCollector


def test_qq_group_message_conversion():
    event = {
        "post_type": "message",
        "message_type": "group",
        "message_id": 123456,
        "group_id": "group_001",
        "group_name": "测试群",
        "user_id": "user_001",
        "nickname": "张三",
        "message": "明天下午三点开会",
    }

    message = QQMessageCollector.from_event(event)

    assert message is not None
    assert message.id == "123456"
    assert message.source == "qq"
    assert message.chat_id == "group_001"
    assert message.chat_name == "测试群"
    assert message.sender_id == "user_001"
    assert message.sender_name == "张三"
    assert message.content == "明天下午三点开会"