import asyncio
import contextlib
import json
import logging
import uuid
from typing import Optional

import httpx
import websockets
from websockets.asyncio.client import ClientConnection
from websockets.protocol import State

from bot_base import BotBase
from config import FEISHU_APP_ID, FEISHU_APP_SECRET

logger = logging.getLogger("feishu")

# Feishu WS constants
FEISHU_DOMAIN = "https://open.feishu.cn"
GEN_ENDPOINT_URI = "/callback/ws/endpoint"
HEADER_TYPE = "type"
HEADER_MESSAGE_ID = "message_id"
HEADER_TRACE_ID = "trace_id"
HEADER_SUM = "sum"
HEADER_SEQ = "seq"
UTF_8 = "utf-8"

# FrameType enum values
FRAME_CONTROL = 0
FRAME_DATA = 1

# MessageType enum values
MSG_EVENT = "event"
MSG_PING = "ping"
MSG_PONG = "pong"


def _get_header(headers, key: str) -> str:
    for h in headers:
        if h.key == key:
            return h.value
    return ""


class FeishuWS(BotBase):
    def __init__(self):
        super().__init__()
        self.ws: Optional[ClientConnection] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._retry_delay = 1
        self._send_lock = asyncio.Lock()
        self._ping_interval: int = 30
        self._service_id: str = ""
        self._response_cache: dict = {}  # stream_id -> accumulated text + chat_id
        self._lark_client = None

        if FEISHU_APP_ID and FEISHU_APP_SECRET:
            try:
                from lark_oapi import Client
                self._lark_client = Client.builder() \
                    .app_id(FEISHU_APP_ID) \
                    .app_secret(FEISHU_APP_SECRET) \
                    .build()
            except ImportError:
                logger.warning("lark-oapi not installed; REST message sending will not work")

    def _is_ws_open(self, ws: Optional[ClientConnection]) -> bool:
        return ws is not None and ws.state is State.OPEN

    async def _get_ws_url(self) -> str:
        """Fetch WebSocket connection URL from Feishu endpoint API."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                FEISHU_DOMAIN + GEN_ENDPOINT_URI,
                headers={"locale": "zh"},
                json={"AppID": FEISHU_APP_ID, "AppSecret": FEISHU_APP_SECRET},
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"Feishu endpoint error: {data}")
            endpoint = data.get("data", {})
            url = endpoint.get("URL", "")
            if not url:
                raise RuntimeError(f"No URL in Feishu endpoint response: {data}")
            # Extract service_id from URL query params
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(url)
            qs = parse_qs(parsed.query)
            self._service_id = qs.get("service_id", ["0"])[0]
            # Apply client config if present
            cc = endpoint.get("ClientConfig")
            if cc:
                ping = cc.get("ping_interval")
                if ping:
                    self._ping_interval = int(ping)
                    logger.info("Feishu ping interval set to %ds", self._ping_interval)
            return url

    def _new_ping_frame(self) -> bytes:
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame
        frame = Frame()
        header = frame.headers.add()
        header.key = HEADER_TYPE
        header.value = MSG_PING
        frame.service = int(self._service_id) if self._service_id else 0
        frame.method = FRAME_CONTROL
        frame.SeqID = 0
        frame.LogID = 0
        return frame.SerializeToString()

    def _new_response_frame(self, original_frame, payload: bytes) -> bytes:
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame
        frame = Frame()
        frame.service = original_frame.service
        frame.method = FRAME_DATA
        frame.SeqID = original_frame.SeqID
        frame.LogID = original_frame.LogID
        # Copy headers
        for h in original_frame.headers:
            nh = frame.headers.add()
            nh.key = h.key
            nh.value = h.value
        frame.payload = payload
        return frame.SerializeToString()

    async def connect(self):
        self._running = True
        while self._running:
            ws = None
            try:
                ws_url = await self._get_ws_url()
                async with websockets.connect(
                    ws_url,
                    ping_interval=None,
                    ping_timeout=None,
                    close_timeout=5,
                    max_size=8 * 1024 * 1024,
                ) as ws:
                    self.ws = ws
                    logger.info("Feishu WebSocket connected")
                    await self._cancel_heartbeat()
                    self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))
                    self._retry_delay = 1
                    await self._receive_loop(ws)
            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning("Disconnected: %s, retrying in %ds", e, self._retry_delay)
                await asyncio.sleep(self._retry_delay)
                self._retry_delay = min(self._retry_delay * 2, 60)
            except Exception as e:
                logger.error("Unexpected error: %s", e)
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

    async def _heartbeat_loop(self, ws: ClientConnection):
        while self._running:
            try:
                await asyncio.sleep(self._ping_interval)
                if self.ws is not ws or not self._is_ws_open(ws):
                    break
                async with self._send_lock:
                    await ws.send(self._new_ping_frame())
                logger.debug("Ping sent")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Ping failed: %s", e)
                break

    async def _receive_loop(self, ws: ClientConnection):
        from lark_oapi.ws.pb.pbbp2_pb2 import Frame

        async for raw in ws:
            frame = Frame()
            frame.ParseFromString(raw)
            ft = frame.method

            if ft == FRAME_CONTROL:
                msg_type = _get_header(frame.headers, HEADER_TYPE)
                if msg_type == MSG_PING:
                    # Server-initiated ping, treat as keepalive (no action needed)
                    pass
                elif msg_type == MSG_PONG:
                    logger.debug("Pong received")
                    if frame.payload:
                        try:
                            conf = json.loads(frame.payload.decode(UTF_8))
                            ping = conf.get("ping_interval")
                            if ping:
                                self._ping_interval = int(ping)
                                logger.info("Updated ping interval to %ds", self._ping_interval)
                        except Exception:
                            pass

            elif ft == FRAME_DATA:
                msg_type = _get_header(frame.headers, HEADER_TYPE)
                if msg_type != MSG_EVENT:
                    continue

                sum_ = int(_get_header(frame.headers, HEADER_SUM) or "1")
                seq = int(_get_header(frame.headers, HEADER_SEQ) or "0")
                pl = frame.payload

                # Multi-frame reassembly
                if sum_ > 1:
                    msg_id = _get_header(frame.headers, HEADER_MESSAGE_ID)
                    pl = self._combine_frames(msg_id, sum_, seq, pl)
                    if pl is None:
                        continue

                # Send ACK response frame back
                try:
                    ack_payload = json.dumps({"code": 200}).encode(UTF_8)
                    ack = self._new_response_frame(frame, ack_payload)
                    async with self._send_lock:
                        if self._is_ws_open(ws):
                            await ws.send(ack)
                except Exception:
                    logger.debug("Failed to send ACK frame")

                # Parse event payload
                try:
                    event_data = json.loads(pl.decode(UTF_8))
                except Exception:
                    logger.warning("Failed to parse event payload")
                    continue

                event_type = event_data.get("header", {}).get("event_type", "")

                if event_type == "im.message.receive_v1":
                    if self.on_message:
                        try:
                            await self.on_message(event_data)
                        except Exception:
                            logger.exception("Message handler failed")
                else:
                    if self.on_event:
                        try:
                            await self.on_event(event_data)
                        except Exception:
                            logger.exception("Event handler failed")

    def _combine_frames(self, msg_id: str, total: int, seq: int, payload: bytes) -> Optional[bytes]:
        # Simple cache for multi-frame reassembly
        if not hasattr(self, '_frame_cache'):
            self._frame_cache: dict = {}
        cache_key = msg_id
        if cache_key not in self._frame_cache:
            self._frame_cache[cache_key] = {}
        self._frame_cache[cache_key][seq] = payload
        if len(self._frame_cache[cache_key]) == total:
            parts = [self._frame_cache[cache_key][i] for i in sorted(self._frame_cache[cache_key])]
            del self._frame_cache[cache_key]
            return b"".join(parts)
        return None

    async def send_respond_msg(self, req_id: str, content: str,
                               stream_id: str, finish: bool = False):
        """Accumulate text and send via REST API when finish=True.
        Returns the Feishu message_id when finish=True, else None."""
        if stream_id not in self._response_cache:
            self._response_cache[stream_id] = {"chat_id": req_id, "text": ""}
        if content:
            self._response_cache[stream_id]["text"] += content

        if finish:
            cache = self._response_cache.pop(stream_id, None)
            if cache and cache["text"]:
                return await self.send_text_message(cache["chat_id"], cache["text"])
        return None

    async def send_welcome(self, req_id: str, text: str):
        """Send a welcome message (req_id is chat_id for Feishu)."""
        await self.send_text_message(req_id, text)

    async def send_text_message(self, chat_id: str, text: str):
        """Send a text message to a Feishu chat via REST API.
        Returns the Feishu message_id on success, or None."""
        if not self._lark_client:
            logger.error("lark-oapi client not initialized, cannot send message")
            return None

        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
        )

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": text}))
                .build()
            )
            .build()
        )

        try:
            response = await asyncio.to_thread(
                self._lark_client.im.v1.message.create, request
            )
            if not response.success():
                logger.error("Feishu send failed: code=%s msg=%s",
                             response.code, response.msg)
                return None
            msg_id = response.data.message_id if response.data else None
            logger.info("Feishu message sent, msg_id=%s", msg_id)
            return msg_id
        except Exception as e:
            logger.error("Feishu send exception: %s", e)
            return None

    async def get_user_name(self, open_id: str) -> str:
        """Resolve Feishu open_id to user name via Contact API."""
        if not self._lark_client or not open_id:
            return open_id or "unknown"
        try:
            from lark_oapi.api.contact.v3 import GetUserRequest
            request = GetUserRequest.builder().user_id(open_id).user_id_type("open_id").build()
            response = await asyncio.to_thread(
                self._lark_client.contact.v3.user.get, request
            )
            if response.success() and response.data and response.data.user:
                return response.data.user.name or open_id
        except Exception as e:
            logger.debug("Failed to resolve user name for %s: %s", open_id, e)
        return open_id

    async def stop(self):
        self._running = False
        await self._cancel_heartbeat()
        if self.ws:
            await self.ws.close()
