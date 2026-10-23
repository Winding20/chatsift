
from datetime import datetime
from uuid import uuid4

from app.models import Message


class QQMessageCollector:
    @staticmethod
    def from_event(event: dict) -> Message | None:
        if event.get("post_type") != "message":
            return None

        if event.get("message_type") != "group":
            return None

        group_id = event.get("group_id")
        user_id = event.get("user_id")

        # 群号和发送者 ID 是识别消息所必需的。
        if group_id is None or user_id is None:
            raise ValueError("群消息缺少 group_id 或 user_id")

        message_id = event.get("message_id")
        if message_id is None:
            message_id = str(uuid4())
        else:
            message_id = str(message_id)

        group_name = event.get("group_name") or str(group_id)
        sender = event.get("sender") or {}
        nickname = (
            event.get("nickname")
            or sender.get("card")
            or sender.get("nickname")
            or str(user_id)
        )

        raw_content = event.get("message", "")

        # OneBot 消息可能是普通文本，也可能是消息段列表。
        if isinstance(raw_content, str):
            content = raw_content
        elif isinstance(raw_content, list):
            parts = []
            for segment in raw_content:
                if not isinstance(segment, dict):
                    continue

                if segment.get("type") == "text":
                    text_data = segment.get("data") or {}
                    parts.append(str(text_data.get("text", "")))
                else:
                    parts.append(f"[{segment.get('type', 'unknown')}]")

            content = "".join(parts)
        else:
            content = str(raw_content)

        return Message(
            id=message_id,
            source="qq",
            chat_id=str(group_id),
            chat_name=str(group_name),
            sender_id=str(user_id),
            sender_name=str(nickname),
            content=content,
            timestamp=datetime.now(),
            # OneBot 每个事件都带 self_id，代表当前登录的 QQ 号
            account_id=(
                str(event["self_id"])
                if event.get("self_id") is not None
                else None
            ),
        )
