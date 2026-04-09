import asyncio
import contextlib
import json
import logging
import uuid
from typing import Optional

import websockets
from websockets.asyncio.client import ClientConnection
from websockets.protocol import State

from bot_base import BotBase
from config import WECOM_BOT_ID, WECOM_BOT_SECRET

logger = logging.getLogger("wecom")


class WeComWS(BotBase):
    WSS_URL = "wss://openws.work.weixin.qq.com"
    HEARTBEAT_INTERVAL = 30

    def __init__(self):
        super().__init__()
        self.ws: Optional[ClientConnection] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._retry_delay = 1
        self._send_lock = asyncio.Lock()

    def _req_id(self) -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _is_ws_open(ws: Optional[ClientConnection]) -> bool:
        return ws is not None and ws.state is State.OPEN

    async def connect(self):
        self._running = True
        while self._running:
            ws = None
            try:
                async with websockets.connect(
                    self.WSS_URL,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=8 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    logger.info("WebSocket connected")
                    await self._cancel_heartbeat()
                    await self._subscribe(ws)
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    self._retry_delay = 1
                    await self._receive_loop(ws)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning(f"Disconnected: {e}, retrying in {self._retry_delay}s")
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, 60)
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                await asyncio.sleep(self._retry_delay)
            finally:
                await self._cleanup_connection(ws)

    async def _cancel_heartbeat(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

    async def _cleanup_connection(self, ws: Optional[ClientConnection]):
        await self._cancel_heartbeat()
        if self.ws is ws:
            self.ws = None

    async def _send_json(self, ws: ClientConnection, msg: dict):
        async with self._send_lock:
            if ws is not self.ws or not self._is_ws_open(ws):
                raise RuntimeError("WebSocket is closed")
            await ws.send(json.dumps(msg, ensure_ascii=False))

    async def _subscribe(self, ws: ClientConnection):
        msg = {
            "cmd": "aibot_subscribe",
            "headers": {"req_id": self._req_id()},
            "body": {"bot_id": WECOM_BOT_ID, "secret": WECOM_BOT_SECRET}
        }
        await self._send_json(ws, msg)
        resp = await asyncio.wait_for(ws.recv(), timeout=15)
        data = json.loads(resp)
        if data.get("errcode") == 0:
            logger.info("Subscribed successfully")
        else:
            logger.error(f"Subscribe failed: {data}")

    async def _heartbeat_loop(self, ws: ClientConnection):
        while self._running:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                if self.ws is not ws or not self._is_ws_open(ws):
                    break
                msg = {"cmd": "ping", "headers": {"req_id": self._req_id()}}
                await self._send_json(ws, msg)
                logger.debug("Heartbeat sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
                if self.ws is ws and self._is_ws_open(ws):
                    with contextlib.suppress(Exception):
                        await ws.close()
                break

    async def _receive_loop(self, ws: ClientConnection):
        async for raw in ws:
            data = json.loads(raw)
            cmd = data.get("cmd", "")
            if cmd == "aibot_msg_callback":
                if self.on_message:
                    try:
                        await self.on_message(data)
                    except Exception:
                        logger.exception("Message handler failed")
            elif cmd == "aibot_event_callback":
                event_type = data.get("body", {}).get("event", {}).get("eventtype", "")
                if event_type == "disconnected_event":
                    logger.warning("Received disconnected_event, closing")
                    break
                if self.on_event:
                    try:
                        await self.on_event(data)
                    except Exception:
                        logger.exception("Event handler failed")
            elif cmd == "pong":
                logger.debug("Pong received")

    async def send_respond_msg(self, req_id: str, content: str,
                               stream_id: str, finish: bool = False):
        ws = self.ws
        if not self._is_ws_open(ws):
            raise RuntimeError("WebSocket is not connected")
        msg = {
            "cmd": "aibot_respond_msg",
            "headers": {"req_id": req_id},
            "body": {
                "msgtype": "stream",
                "stream": {"id": stream_id, "finish": finish, "content": content}
            }
        }
        await self._send_json(ws, msg)

    async def send_welcome(self, req_id: str, text: str):
        ws = self.ws
        if not self._is_ws_open(ws):
            raise RuntimeError("WebSocket is not connected")
        msg = {
            "cmd": "aibot_respond_welcome_msg",
            "headers": {"req_id": req_id},
            "body": {"msgtype": "text", "text": {"content": text}}
        }
        await self._send_json(ws, msg)

    async def send_text_message(self, chat_id: str, text: str):
        """WeCom sends via WebSocket streaming, not REST."""
        raise NotImplementedError("WeCom uses send_respond_msg for streaming")

    async def stop(self):
        self._running = False
        await self._cancel_heartbeat()
        if self.ws:
            await self.ws.close()
