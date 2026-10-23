"""从群聊消息里"捡宝"：挑出值得花 10 秒看的内容。

与旧的总结不同，这里产出的每条内容都自带原话（逐字），
原话就是正文，点评只是注解——因为段子、观点、经验一旦被改写就失去价值。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

from app.models import Message
from app.noise import strip_bots


MAX_MESSAGES = 100
MAX_CARDS = 8
MAX_DIGEST = 5
MAX_QUOTE_CHARS = 300
MAX_WHY_CHARS = 120

PLACEHOLDER_RE = re.compile(
    r"\[(image|face|voice|file|video|forward|link|at|reply|表情|图片|语音|文件|视频|转发)\]",
    re.IGNORECASE,
)

TYPE_LABELS = {
    "knowledge": "知识点",
    "joke": "段子",
    "view": "观点",
    "intel": "情报",
    "deal": "约定",
}

CONFIDENCE_LABELS = {
    "fact": "群友陈述",
    "claim": "群友说法（未核实）",
    "meme": "玩梗",
}

STATUS_LABELS = {
    "done": "有结论",
    "ongoing": "还在聊",
    "open": "没人答",
}

PROMPT = """你在帮一个没时间看群的人"捡宝"：从一堆群聊消息里，挑出真正值得他花 10 秒看的内容。

只挑这五类，其它一律不要：
- knowledge 知识点：可以拿去复用的经验、参数、原理、技巧、避坑、对比。例："K90 max玩端游风扇比拯救者还大，应该是撞温度墙之后才全速运行"。
  必须同时满足两条：①有具体对象（型号、软件、地点、价格、步骤、参数）；②读完能改变做法或判断。
  反例（都不算）：「拍照耗电」「新手机在光照好的情况下都很清楚吧其实」「两边都打得好傻逼」——这些都是评价或感觉，没有可复用的东西。
  正例：「镜像的话自己挂个 cdn 买个服务器」「K90 max 玩端游风扇比拯救者还大，应该是撞温度墙之后才全速运行」。
  每条 knowledge 还要给 reusable：true（能拿去复用）/ false（只是条评论）。给 false 的会被丢弃。
- joke 段子：必须有转折、反差、双关、神回复，或者对上一句的巧妙接下茬。例："黑白滤镜拍出来有种凶宅即视感"（反差）、"欧皇挨我c"（接下茬）。
  以下**不算**段子：单独的语气词、脏话、口头禅、单字、"哈哈哈/喵喵喵"这类纯笑声、没有回应对象的自言自语、只是骂了一句。
  判断方法：这条必须能被"上一句"解释。找不到上一句，就不要选它当段子。
- view 观点：至少两个人对同一件事有不同看法或争论。例：一方说"台湾人就这样纯翻译啊"，另一方说"这个还好，我能理解"
- intel 情报：活动、维护、开源发布、涨价、报名、新东西上线
- deal 约定：明确的时间、地点、人数、截止日期

绝对不能出现的：纯寒暄、纯表情、[image]/[face] 这类占位符、机器人自动回复、没有信息量的单个词、**没有笑点的单纯抱怨**（"今天网络不好""该升级了"这种）、没有上下文的半句话。不要为了凑数硬写，但也不要因为话题"不重要"就放过段子和经验。

判断标准只有一条：**这条能让人"哦，原来如此"，或者"哈哈"吗？** 两者都没有，就不要选。吐槽可以是好段子，只要它有反差或者神转折；只是抱怨就不算。

注意：严格不等于什么都不给。选之前把五类各扫一遍——有可复用的经验就写知识点，有明确的活动/维护/开源就写情报，有两个人在争就写观点。确实都没有时，cards 返回空数组。

每条必须满足：
1. quote 必须**整条复制**原消息（连标点、表情、括号一起照抄），不要自己截断、改写或拼接。这是要直接展示给用户看的原文，改动就失去价值。程序会逐字核对，对不上的会被丢弃。
   **只填消息正文本身**，不要带上面的时间、消息 id 或说话人名字。
2. why 是一句点评，不超过 40 字，说明好在哪：好笑 / 能学到 / 有分歧 / 能省钱省时间。
3. verdict 是"值不值得花 10 秒看"：worth（值得）/ meh（一般，扫一眼就行）。不值得的直接不要写进来。score 是 0-5 的辅助分，同档内用它排序。
4. confidence 三选一：fact（明确陈述）、claim（群友说法，未核实）、meme（玩梗）。
5. message_ids 只放 quote 所在的那条消息的 id。
6. 机器人反复刷的模板消息（每次只换括号里的词，比如“抓到一只新猪猪啦！【…”）最多留一条。

另外，用 digest 记一段"这段时间群里到底发生了什么"，让人不看原消息也能读懂：
- **digest 是必填项**：除非整批消息全是表情、图片占位符或机器人模板，否则至少要写 1 条。即使一条值得推荐的卡片都没有，也要用它记下群里聊了什么——它是"知道的底线"，不是"精选"。
- 按话题分组，不要逐条复述；一个话题一条，最多 5 条，按发生时间先后排。
- **一个话题 = 一段连续的对话**。同一时间、同一批人聊的同一件事，只写一条，不要按关键词拆成"设备讨论 / 摄影技巧 / 购买建议"这种碎片。只有话题明显换了（换了对象或换了目的），才另起一条。
- summary 用 1-2 句说清：谁提的、聊了什么、目前结论是什么。平淡话题也要记。
- status 三选一：done（聊完了/有结论）、ongoing（还在聊）、open（抛出了问题没人答）。
- 每条必须引用真实消息 id，程序会核对。

只输出严格 JSON，不要 Markdown，不要解释：
{"cards":[{"type":"knowledge|joke|view|intel|deal","quote":"逐字原话","why":"点评","score":4,"verdict":"worth","confidence":"fact","reusable":true,"message_ids":["消息id"]}],"digest":[{"title":"话题标题，不超过 15 字","summary":"1-2 句，说清谁说了什么、结论如何","status":"done|ongoing|open","message_ids":["消息id"]}]}

一条都没有时返回 {"cards": [], "digest": []}。cards 最多 8 条，按 score 从高到低排列。

消息如下（按时间顺序）：
"""


@dataclass
class FeedReport:
    payload: dict
    message_count: int
    window_start: str | None
    window_end: str | None
    model: str | None = None
    dropped: int = 0
    source_ids: list[str] = field(default_factory=list)


class FeedGenerationError(RuntimeError):
    pass


class EmptyBatchError(FeedGenerationError):
    """这批消息全是占位符/链接/超长文案，不值得送去分析。"""


def _noise(message: Message) -> bool:
    """进模型前先扔掉纯占位、分享链接和超长机器人文案。"""
    content = (message.content or "").strip()
    if not content or _placeholder_only(content):
        return True
    if len(content) > 160:
        return True
    if "qfile.qq.com" in content or "http://" in content or "https://" in content:
        return True
    return False


def select_messages(messages: list[Message], limit: int = MAX_MESSAGES) -> list[Message]:
    if limit <= 0:
        return []
    ordered = sorted(messages, key=lambda m: (m.timestamp, m.id))

    # 先干掉机器人（签到、欢迎、接话机器人），再按开头去重
    ordered = strip_bots(ordered)

    # 同一开头出现三次以上的，多半是机器人刷的模板，整条丢掉。
    prefixes = Counter(
        (message.content or "").strip()[:8] for message in ordered
    )
    cleaned = [
        message
        for message in ordered
        if not _noise(message)
        and prefixes[(message.content or "").strip()[:8]] < 3
    ]
    return cleaned[-limit:]


def build_context(messages: list[Message]) -> str:
    lines = []
    for message in messages:
        content = (message.content or "").strip().replace("\n", " ")
        if len(content) > 240:
            content = content[:240] + "…"
        timestamp = message.timestamp.strftime("%m-%d %H:%M")
        lines.append(f"[{timestamp}] ({message.id}) {message.sender_name}: {content}")
    return "\n".join(lines)


def _taste_hints() -> str:
    """把用户点过"有用 / 无聊"的原文，作为口味参考塞进提示词。

    反馈太少时不注入——一两条投票不足以代表口味，
    反而会让模型过度收敛（实测会一条都不选）。
    """
    try:
        from app import feedback

        disliked = feedback.disliked_examples(3)
        liked = feedback.liked_examples(3)
    except Exception:  # noqa: BLE001 — 读不到反馈不影响正常分析
        return ""

    if len(disliked) + len(liked) < 3:
        return ""

    parts: list[str] = []
    if disliked:
        parts.append(
            "用户点过“无聊”的内容，别选类似的：\n"
            + "\n".join(f"- {quote}" for quote in disliked)
        )
    if liked:
        parts.append(
            "用户点过“有用”的内容，可以往这个方向找：\n"
            + "\n".join(f"- {quote}" for quote in liked)
        )

    return "【参考】" + "\n".join(parts) + "\n（仅作偏好参考，不要因此漏掉真正有价值的内容）"


def build_prompt(messages: list[Message]) -> str:
    prompt = PROMPT + f"（共 {len(messages)} 条）\n" + build_context(messages)
    hints = _taste_hints()
    if hints:
        prompt += "\n\n" + hints
    return prompt


def _text(value, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:limit]


def _span_label(first: datetime, last: datetime) -> str:
    """时间段文案：同一天只显示时分，跨天带上日期。"""
    if first.date() == last.date():
        return f"{first:%H:%M}" if first == last else f"{first:%H:%M}–{last:%H:%M}"
    return f"{first:%m-%d %H:%M} – {last:%m-%d %H:%M}"


_BRACKET_PREFIX_RE = re.compile(r"^\s*\[[^\]]{0,24}\]\s*")
_ID_PREFIX_RE = re.compile(r"^\s*\([^)]{1,40}\)\s*")
_NAME_PREFIX_RE = re.compile(r"^\s*[^:：\n]{1,24}[:：]\s*")


def _quote_candidates(quote: str) -> list[str]:
    """模型有时会把 "[时间] (id) 名字：正文" 整行抄回来，这里列出可能的正文形态。"""
    candidates: list[str] = []

    def push(value: str) -> None:
        value = (value or "").strip()
        if value and value not in candidates:
            candidates.append(value)

    text = (quote or "").strip()
    push(text)

    without_time = _BRACKET_PREFIX_RE.sub("", text)
    push(without_time)
    without_id = _ID_PREFIX_RE.sub("", without_time)
    push(without_id)

    for base in (without_time, without_id):
        match = _NAME_PREFIX_RE.match(base)
        if match:
            push(base[match.end():])

    return candidates


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _citations(value, valid_ids: set[str]) -> list[str]:
    """只保留真实存在的消息 id，去重。"""
    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        message_id = str(item).strip()
        if message_id in valid_ids and message_id not in result:
            result.append(message_id)

    return result


def _placeholder_only(text: str) -> bool:
    cleaned = PLACEHOLDER_RE.sub("", text or "")
    return not re.sub(r"[\W_]+", "", cleaned)


FILLER_RE = re.compile(
    r"^[哈啊呜嗯哦诶嘿呵喵嗷呀吧的呢了嘛额呃哇嘻嘎嗷6?？!！…\.。~～\s]+$"
)

# 纯评价/骂人的话，不管模型怎么标都不能当"知识点"
EVAL_RE = re.compile(r"傻逼|煞笔|弱智|智障|脑残|垃圾|牛逼|无语|搞笑|菜鸡|喷子", re.I)

# 具体对象：型号、参数、价格、版本号这类至少会带数字或字母
CONCRETE_RE = re.compile(r"[0-9A-Za-z]")


def _knowledge_ok(item: dict, quote: str) -> bool:
    """知识点要能复用，不是一句泛泛的评价。"""
    if item.get("reusable") is False:
        return False
    if EVAL_RE.search(quote):
        return False
    if len(quote) < 6:
        return False
    if item.get("reusable") is True:
        return True
    # 没自评时，只有带具体对象（数字/字母/型号）才放行
    return bool(CONCRETE_RE.search(quote))


def _weak_joke(quote: str, context: dict) -> bool:
    """挡住"喵喵喵""指腚湿"这类：短、纯语气词、或者根本没有上一句可接。"""
    text = quote.strip()

    if len(text) < 6:
        return True
    if FILLER_RE.match(text):
        return True
    if not (context.get("before") or []):
        return True

    return False


def _score(value) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 2
    return max(0, min(5, score))


VERDICT_LABELS = {"worth": "值得看", "meh": "一般"}


def _verdict(item: dict, score: int) -> str:
    """三档判断：值得看 / 一般。模型没给就按分数推。"""
    value = str(item.get("verdict") or "").strip().lower()
    if value in VERDICT_LABELS:
        return value
    if value in ("值得", "worth", "must"):
        return "worth"
    if value in ("一般", "worthless", "skip"):
        return "meh"
    return "worth" if score >= 4 else "meh"


def _context(
    messages: list[Message],
    position: dict[str, int],
    message_id: str,
    span: int = 2,
    minutes: int = 10,
) -> dict:
    """取原话前后各几条消息，让"好笑/有分歧"能被看懂。

    只取时间上相邻的：群很安静时，两小时前的一句话不算上下文。
    """
    index = position.get(message_id)
    if index is None:
        return {"before": [], "after": []}

    anchor = messages[index].timestamp

    def pack(subset):
        lines = []
        for message in subset:
            gap = abs((message.timestamp - anchor).total_seconds())
            if gap > minutes * 60:
                continue
            text = (message.content or "").strip().replace("\n", " ")
            if not text or _placeholder_only(text):
                continue
            lines.append(
                {"sender": message.sender_name, "content": text[:120]}
            )
        return lines

    return {
        "before": pack(messages[max(0, index - span):index]),
        "after": pack(messages[index + 1:index + 1 + span]),
    }


def sanitize(raw: dict, messages: list[Message]) -> tuple[dict, int]:
    """只保留原话能逐字对上的卡片，其余丢弃。"""
    texts = {str(m.id): (m.content or "") for m in messages}
    by_id = {str(m.id): m for m in messages}
    position = {str(m.id): index for index, m in enumerate(messages)}

    dropped = 0
    cards = []
    seen = set()

    for item in raw.get("cards") or []:
        if len(cards) >= MAX_CARDS:
            break
        if not isinstance(item, dict):
            dropped += 1
            continue

        quote = _text(item.get("quote"), MAX_QUOTE_CHARS)
        why = _text(item.get("why"), MAX_WHY_CHARS)
        kind = item.get("type")
        confidence = item.get("confidence")

        if kind not in TYPE_LABELS:
            dropped += 1
            continue

        # 知识点必须自评"可复用"，否则丢掉——挡住"两边都打得好傻逼"这类评价
        if kind == "knowledge" and not _knowledge_ok(item, quote):
            dropped += 1
            continue
        if not quote or _placeholder_only(quote):
            dropped += 1
            continue
        if len(quote) > 160:
            dropped += 1
            continue

        raw_ids = item.get("message_ids")
        citations = []
        if isinstance(raw_ids, list):
            for value in raw_ids:
                message_id = str(value).strip()
                if message_id in texts and message_id not in citations:
                    citations.append(message_id)

        if not citations:
            dropped += 1
            continue

        needle = _normalize(quote)
        haystack = _normalize("".join(texts[cid] for cid in citations))
        if needle not in haystack:
            # 模型偶尔会把 "时间 (id) 名字：正文" 整行抄回来，逐个候选再核对
            for candidate in _quote_candidates(quote):
                if _normalize(candidate) in haystack:
                    quote = candidate
                    needle = _normalize(candidate)
                    break
            else:
                dropped += 1
                continue

        key = needle
        if key in seen:
            dropped += 1
            continue
        seen.add(key)

        source = by_id[citations[0]]
        context = _context(messages, position, citations[0])

        # 段子门槛：太短、纯语气词、或者没有上一句可接的，一律不算段子。
        if kind == "joke" and _weak_joke(quote, context):
            dropped += 1
            continue

        score = _score(item.get("score"))
        verdict = _verdict(item, score)
        cards.append(
            {
                "type": kind,
                "type_label": TYPE_LABELS[kind],
                "quote": quote,
                "why": why,
                "score": score,
                "verdict": verdict,
                "verdict_label": VERDICT_LABELS[verdict],
                "confidence": confidence
                if confidence in CONFIDENCE_LABELS
                else "claim",
                "confidence_label": CONFIDENCE_LABELS.get(confidence, "群友说法（未核实）"),
                "sender": source.sender_name,
                "timestamp": source.timestamp.isoformat(),
                "message_ids": citations,
                "context": context,
            }
        )

    cards.sort(key=lambda card: (-card["score"], card["timestamp"]))

    # 同一个对话线程只留一条：上下文有重叠的，视为同一件事。
    thread_seen: set[str] = set()
    thread_unique: list[dict] = []
    for card in cards:
        lines = (card.get("context") or {}).get("before", []) + (
            (card.get("context") or {}).get("after", [])
        )
        fingerprint = {
            _normalize(line.get("content", ""))[:40] for line in lines
        }
        fingerprint.add(_normalize(card["quote"])[:40])

        if fingerprint & thread_seen:
            dropped += 1
            continue

        thread_seen |= fingerprint
        thread_unique.append(card)
    cards = thread_unique

    # 同一发送者最多留两条，且开头相同的模板只留一条：挡住机器人刷屏。
    per_sender: dict[str, int] = {}
    prefixes: set[str] = set()
    unique: list[dict] = []
    for card in cards:
        used = per_sender.get(card["sender"], 0)
        prefix = _normalize(card["quote"])[:12]
        if used >= 2 or prefix in prefixes:
            dropped += 1
            continue
        per_sender[card["sender"]] = used + 1
        prefixes.add(prefix)
        unique.append(card)
    cards = unique

    # 时段纪要：让人不看原消息也知道"这段时间群里发生了什么"。
    valid_ids = set(texts)
    digest: list[dict] = []
    digest_titles: set[str] = set()
    for item in raw.get("digest") or []:
        if len(digest) >= MAX_DIGEST:
            break
        if not isinstance(item, dict):
            continue

        title = _text(item.get("title"), 24)
        summary = _text(item.get("summary"), 200)
        citations = _citations(item.get("message_ids"), valid_ids)

        if not title or not summary or not citations:
            continue

        key = _normalize(title)
        if key in digest_titles:
            continue
        digest_titles.add(key)

        moments = [by_id[cid].timestamp for cid in citations]
        status = item.get("status")
        if status not in STATUS_LABELS:
            status = "ongoing"

        first, last = min(moments), max(moments)
        span = _span_label(first, last)

        digest.append(
            {
                "title": title,
                "summary": summary,
                "status": status,
                "status_label": STATUS_LABELS[status],
                "start": first.strftime("%H:%M"),
                "end": last.strftime("%H:%M"),
                "start_ts": first.isoformat(),
                "end_ts": last.isoformat(),
                "range_label": span,
                "participants": list(
                    dict.fromkeys(by_id[cid].sender_name for cid in citations)
                )[:4],
                "message_ids": citations,
            }
        )

    digest.sort(key=lambda item: item["start_ts"])

    # 时间上重叠的话题合并成一条：模型常把一段连续的对话拆成好几条碎片。
    merged: list[dict] = []
    for item in digest:
        if merged and item["start_ts"] <= merged[-1]["end_ts"]:
            prev = merged[-1]
            prev["end_ts"] = max(prev["end_ts"], item["end_ts"])
            if len(item["summary"]) > len(prev["summary"]):
                prev["summary"] = item["summary"]
            prev["participants"] = list(
                dict.fromkeys(prev["participants"] + item["participants"])
            )[:4]
            prev["message_ids"] = list(
                dict.fromkeys(prev["message_ids"] + item["message_ids"])
            )
            prev["status"] = (
                prev["status"] if prev["status"] == "done" else item["status"]
            )
            prev["status_label"] = STATUS_LABELS[prev["status"]]
            dropped += 1
            continue
        merged.append(item)
    digest = merged

    for item in digest:
        first = datetime.fromisoformat(item["start_ts"])
        last = datetime.fromisoformat(item["end_ts"])
        item["start"] = first.strftime("%H:%M")
        item["end"] = last.strftime("%H:%M")
        item["range_label"] = _span_label(first, last)

    payload = {"v": 2, "cards": cards, "digest": digest}
    return payload, dropped


def generate(ai_client, messages: list[Message]) -> FeedReport:
    selected = select_messages(messages)
    if not selected:
        raise EmptyBatchError("这批消息全是占位符、链接或超长文案")

    prompt = build_prompt(selected)
    raw = ai_client.chat_json(prompt)
    if not isinstance(raw, dict):
        raise FeedGenerationError("AI 返回的不是 JSON 对象")

    payload, dropped = sanitize(raw, selected)

    # 模型偶尔整批返回空（同样的输入时好时坏）。再问一次，仍为空就认了。
    if not payload["cards"] and not payload["digest"]:
        retry_prompt = (
            prompt
            + "\n\n【提醒】这批消息里确实有值得看的内容，请再仔细扫一遍；"
            "即使没有合适的卡片，也至少要给出 1 条 digest。"
        )
        try:
            # 用更高的温度重试一次，跳出"整批返回空"的退化结果
            retry_raw = ai_client.chat_json(retry_prompt, temperature=0.8)
            if isinstance(retry_raw, dict):
                retry_payload, retry_dropped = sanitize(retry_raw, selected)
                if retry_payload["cards"] or retry_payload["digest"]:
                    raw, payload, dropped = retry_raw, retry_payload, retry_dropped
        except Exception:  # noqa: BLE001 — 重试失败就按第一次的结果走
            pass

    source_ids: list[str] = []
    for card in payload["cards"]:
        for message_id in card["message_ids"]:
            if message_id not in source_ids:
                source_ids.append(message_id)

    model = getattr(ai_client, "model", None)

    return FeedReport(
        payload=payload,
        message_count=len(selected),
        window_start=selected[0].timestamp.isoformat(),
        window_end=selected[-1].timestamp.isoformat(),
        model=model if isinstance(model, str) else None,
        dropped=dropped,
        source_ids=source_ids,
    )
