"""WebSocket 接收端：只负责把 QQ 消息写进数据库。

分析不在这里做——那是 app/scheduler.py 的事。
这样"采集"和"花钱的分析"可以各自独立跑、独立停。
"""

from __future__ import annotations

import asyncio
import json
import logging

import websockets
from websockets.exceptions import ConnectionClosed

from app import session_log
from app.config import get_ws_host, get_ws_port
from app.qq_collector import QQMessageCollector
from app.repositories import MessageRepository


log = logging.getLogger("assistant.receiver")

repository = MessageRepository()


async def handle_connection(websocket) -> None:
    try:
        event_id = session_log.open_connection()
    except Exception as exc:  # noqa: BLE001 — 记不上连接也不能挡住收消息
        log.warning("连接记录写入失败：%s", exc)
        event_id = None

    log.info("QQ 接入端已连接")

    try:
        async for raw in websocket:
            await _handle_message(raw)
    except ConnectionClosed as exc:
        # 客户端换号或重启时会这样断开，属正常现象，不必打堆栈
        log.info("QQ 接入端连接中断：%s", exc)
    finally:
        if event_id is not None:
            try:
                session_log.close_connection(event_id)
            except Exception:  # noqa: BLE001
                log.exception("连接断开记录失败")
        log.info("QQ 接入端已断开")


async def _handle_message(raw) -> None:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("收到非 JSON 消息，已忽略")
        return

    try:
        message = QQMessageCollector.from_event(event)
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("消息格式转换失败：%s", exc)
        return

    if message is None:
        return

    try:
        repository.save(message)
    except Exception as exc:  # noqa: BLE001 — 单条坏消息不能拖垮连接
        log.error("消息入库失败：%s", exc)


async def serve() -> None:
    host = get_ws_host()
    port = get_ws_port()

    async with websockets.serve(handle_connection, host, port):
        log.info("WebSocket 接收端：ws://%s:%s", host, port)
        await asyncio.Future()
