from app.qq_collector import QQMessageCollector


def test_same_qq_message_has_same_id():
    event = {
        "post_type": "message",
        "message_type": "group",
        "message_id": "123456789",
        "group_id": "group_001",
        "group_name": "测试群",
        "user_id": "user_001",
        "nickname": "张三",
        "message": "明天下午三点开会",
    }

    message_1 = QQMessageCollector.from_event(event)
    message_2 = QQMessageCollector.from_event(event)

    assert message_1 is not None
    assert message_2 is not None

    assert message_1.id == "123456789"
    assert message_2.id == "123456789"
    assert message_1.id == message_2.id