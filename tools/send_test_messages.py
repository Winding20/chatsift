"""手工测试脚本：往本地接收端发几条假的 QQ 群消息。

用法（先启动 run.py）：
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\send_test_messages.py
"""

import asyncio
import json

import websockets


MESSAGES = [
    {
        "post_type": "message",
        "message_type": "group",
        "group_id": "group_A",
        "group_name": "测试群A",
        "user_id": "user_001",
        "nickname": "张三",
        "message": "明天开会",
    },
    {
        "post_type": "message",
        "message_type": "group",
        "group_id": "group_A",
        "group_name": "测试群A",
        "user_id": "user_002",
        "nickname": "李四",
        "message": "下午三点",
    },
    {
        "post_type": "message",
        "message_type": "group",
        "group_id": "group_B",
        "group_name": "测试群B",
        "user_id": "user_003",
        "nickname": "王五",
        "message": "今晚聚餐",
    },
    {
        "post_type": "message",
        "message_type": "group",
        "group_id": "group_B",
        "group_name": "测试群B",
        "user_id": "user_004",
        "nickname": "赵六",
        "message": "晚上八点开始",
    },
    {
        "post_type": "message",
        "message_type": "group",
        "group_id": "group_A",
        "group_name": "测试群A",
        "user_id": "user_001",
        "nickname": "张三",
        "message": "会议室A",
    },
]


async def main() -> None:
    async with websockets.connect("ws://127.0.0.1:8765") as websocket:
        for message in MESSAGES:
            await websocket.send(json.dumps(message, ensure_ascii=False))
            print(
                f"已发送 [{message['group_name']}] "
                f"{message['nickname']}: {message['message']}"
            )
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
