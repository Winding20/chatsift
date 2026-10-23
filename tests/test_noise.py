from datetime import datetime, timedelta

from app.models import Message
from app.noise import detect_bot_senders, strip_bots


BASE = datetime(2026, 10, 20, 21, 0, 0)


def make(index, sender_id, name, content):
    return Message(
        id=f"m{index}",
        source="qq",
        chat_id="g1",
        chat_name="测试群",
        sender_id=sender_id,
        sender_name=name,
        content=content,
        timestamp=BASE + timedelta(seconds=index),
    )


def test_named_bot_is_detected():
    messages = [
        make(0, "bot1", "签到机器人", "签到成功"),
        make(1, "bot1", "签到机器人", "签到成功"),
        make(2, "bot1", "签到机器人", "签到成功"),
        make(3, "u1", "老王", "这游戏真好玩"),
    ]

    bots = detect_bot_senders(messages)

    assert "bot1" in bots
    assert "u1" not in bots


def test_long_template_spam_is_detected():
    template = "抓到一只新猪猪啦！快来看看它长什么样子"
    messages = [make(i, "bot2", "小明", template) for i in range(4)]
    messages.append(make(5, "u1", "老王", "今天天气不错"))

    bots = detect_bot_senders(messages)

    assert "bot2" in bots
    assert "u1" not in bots


def test_repeating_short_phrase_is_not_bot():
    """真人连发几次"哈哈哈"不算机器人。"""
    messages = [
        make(0, "u1", "老王", "哈哈哈"),
        make(1, "u1", "老王", "哈哈哈"),
        make(2, "u1", "老王", "哈哈哈"),
        make(3, "u1", "老王", "哈哈哈"),
        make(4, "u1", "老王", "这支线太离谱了"),
    ]

    assert detect_bot_senders(messages) == {}


def test_quoting_replies_is_not_bot():
    """真人连续引用回复也不算。"""
    messages = [
        make(i, f"u{i}", "群友", f"[reply]你说的第{i}点我同意")
        for i in range(6)
    ]
    messages += [
        make(10 + i, "u0", "群友", f"[reply]那我再说一句{i}") for i in range(4)
    ]

    assert detect_bot_senders(messages) == {}


def test_normal_people_are_kept():
    messages = [
        make(0, "u1", "老王", "明天十点开黑"),
        make(1, "u2", "小李", "我可以"),
        make(2, "u3", "阿强", "K90 max 风扇很大"),
    ]

    assert detect_bot_senders(messages) == {}


def test_strip_bots_records_stats():
    messages = [
        make(0, "bot1", "签到机器人", "签到成功"),
        make(1, "bot1", "签到机器人", "签到成功"),
        make(2, "bot1", "签到机器人", "签到成功"),
        make(3, "u1", "老王", "人呢"),
    ]

    kept = strip_bots(messages)

    assert [m.sender_id for m in kept] == ["u1"]
    assert detect_bot_senders(messages).get("bot1") == 3
