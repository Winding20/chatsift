"""识别机器人 / 模板消息。

群里的自动回复机器人（签到、欢迎、接话机器人）会把一批消息撑满，
既浪费 token 又干扰判断。

这里只认两个**高置信**信号，宁可漏掉一个机器人，也不误删真人：

1. 昵称里有明显的机器人标记（"小助手"、"签到机器人"、"功能BOT"）；
2. 同一个人反复刷同一条长文案（长度 ≥ 10，出现 ≥ 4 次）。

不认"连续引用回复"——真人也会连着引用，误伤代价太大。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from app.models import Message

BOT_NAME_RE = re.compile(
    r"机器人|助手|精灵|小冰|客服|公告|播报|签到|打卡|"
    r"\[?bot\]?|robot|assistant|notify|notice",
    re.I,
)
PUNCT_RE = re.compile(r"[\s\W_]+", re.U)

TEMPLATE_MIN_LENGTH = 10
TEMPLATE_MIN_REPEAT = 4
NAMED_MIN_MESSAGES = 3

# 最近一次过滤的统计，供自检显示
LAST: dict[str, object] = {"count": 0, "senders": []}


def _signature(text: str) -> str:
    """去掉标点和空白后取前 40 字，用来判断是不是同一条模板。"""
    return PUNCT_RE.sub("", (text or ""))[:40]


def detect_bot_senders(
    messages: list[Message],
    repeat: int = TEMPLATE_MIN_REPEAT,
) -> dict[str, int]:
    """返回 {发送者 id: 该发送者的消息条数}。"""
    grouped: dict[str, list[Message]] = defaultdict(list)
    for message in messages:
        grouped[message.sender_id].append(message)

    result: dict[str, int] = {}
    for sender_id, items in grouped.items():
        name = items[0].sender_name or ""
        signatures = Counter(_signature(m.content) for m in items)
        top_signature, top_count = (
            signatures.most_common(1)[0] if signatures else ("", 0)
        )

        template_spam = (
            top_count >= repeat and len(top_signature) >= TEMPLATE_MIN_LENGTH
        )
        named_bot = bool(BOT_NAME_RE.search(name)) and len(items) >= NAMED_MIN_MESSAGES

        if template_spam or named_bot:
            result[sender_id] = len(items)

    return result


def strip_bots(messages: list[Message]) -> list[Message]:
    """过滤掉机器人消息，并记录这次的统计。"""
    bots = detect_bot_senders(messages)
    if not bots:
        LAST["count"] = 0
        LAST["senders"] = []
        return messages

    names = sorted({m.sender_name for m in messages if m.sender_id in bots})
    LAST["count"] = sum(bots.values())
    LAST["senders"] = names

    return [message for message in messages if message.sender_id not in bots]
