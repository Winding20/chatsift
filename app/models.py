from dataclasses import dataclass
from datetime import datetime


@dataclass
class Message:
    id: str
    source: str
    chat_id: str
    chat_name: str
    sender_id: str
    sender_name: str
    content: str
    timestamp: datetime
    # 收到这条消息时登录的 QQ 号（OneBot 的 self_id）；历史导入时为空
    account_id: str | None = None

    def __getitem__(self, key: str):
        return getattr(self, key)
