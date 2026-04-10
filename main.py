import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from langchain_agent import call_agent, call_agent_simple, init_mcp_tools
from config import SERVER_HOST, SERVER_PORT, OWNER_NAME, SPECIAL_USERID, ROOT_PATH, PROJECT_BASE_DIR, BOT_TYPE, LLM_MODEL
from database import (add_message, complete_todo, complete_from_pending,
                      create_todo, find_recent_active_todo, find_todo_by_quoted_content,
                      find_todo_by_platform_msg_id,
                      get_messages, get_todo, get_todos, get_stats,
                      get_time_segments, get_all_time_segments, init_db,
                      reorder_todo, set_todo_processing,
                      set_last_assistant_platform_msg_id,
                      sync_todo_queue, update_todo_title)
from bot_base import BotBase

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")


def create_bot() -> BotBase:
    if BOT_TYPE == "feishu":
        from feishu_ws import FeishuWS
        return FeishuWS()
    else:
        from wecom_ws import WeComWS
        return WeComWS()


bot = create_bot()


def _build_prompt(sender: str, content: str) -> str:
    return f"发送人：{sender}\n内容：{content}"


def _extract_text_from_content(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""

    parts: List[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text", "")
            if text:
                parts.append(text)
        elif block_type == "tool_result":
            inner = _extract_text_from_content(block.get("content"))
            if inner:
                parts.append(inner)
        elif block_type == "compaction":
            text = block.get("content", "")
            if text:
                parts.append(text)
    return "\n".join(part for part in parts if part).strip()


def _extract_event_text(event: dict) -> str:
    event_type = event.get("type")
    if event_type == "assistant":
        return _extract_text_from_content(event.get("message", {}).get("content"))
    if event_type == "result":
        return (event.get("result") or "").strip()
    if event_type == "error":
        return (event.get("message") or event.get("content") or "").strip()
    return ""


def _should_persist_event(event: dict) -> bool:
    event_type = event.get("type", "")
    return event_type in {"assistant", "result", "error"}


async def _run_agent_for_todo(todo_id: int, prompt: str,
                              system_prompt: str = "",
                              include_history: bool = False) -> tuple:
    """Returns (full_response, reply_message). reply_message is from reply_to_user tool."""
    full_response = ""
    reply_message = ""
    history: list = []
    if include_history:
        prev_msgs = await get_messages(todo_id)
        for msg in prev_msgs:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})

    await set_todo_processing(todo_id, True)
    try:
        async for event in call_agent(prompt, system_prompt=system_prompt,
                                      history=history if history else None):
            if not _should_persist_event(event):
                continue

            payload = json.dumps(event, ensure_ascii=False)
            event_type = event.get("type", "")
            role = "assistant" if event_type in {"assistant", "result"} else "system"
            text = _extract_event_text(event)
            # For result events, store reply_message (user-facing text) instead
            # of raw result, so quoted reply content matching works.
            # Raw result is preserved in payload field.
            if event_type == "result" and event.get("reply_message"):
                text = event["reply_message"]
            await add_message(
                todo_id,
                role,
                text,
                event_type=event_type,
                payload=payload,
            )

            # Extract reply_message from final result event
            if event_type == "result" and event.get("reply_message"):
                reply_message = event["reply_message"]

            if event_type in {"assistant", "result"} and text:
                if full_response and not full_response.endswith("\n"):
                    full_response += "\n"
                full_response += text
            elif event_type == "error" and text:
                if full_response and not full_response.endswith("\n"):
                    full_response += "\n"
                full_response += text
    finally:
        await set_todo_processing(todo_id, False)
        await sync_todo_queue(todo_id)

    return full_response, reply_message


async def _stream_keepalive(req_id: str, stream_id: str, interval: int = 15):
    """Periodically send stream messages to prevent WeChat stream timeout."""
    count = 1
    while True:
        await asyncio.sleep(interval)
        try:
            await bot.send_respond_msg(
                req_id, f"还在处理中，请稍候...({count})", stream_id)
            logger.info("Stream keepalive sent for req_id=%s count=%s", req_id, count)
            count += 1
        except Exception as exc:
            logger.warning("Stream keepalive failed for req_id=%s: %s", req_id, exc)
            break


async def _normalize_message(data: dict) -> dict:
    """Normalize platform-specific message data into a common format."""
    if BOT_TYPE == "feishu":
        event = data.get("event", {})
        message = event.get("message", {})
        sender_id = event.get("sender", {}).get("sender_id", {})
        open_id = sender_id.get("user_id") or sender_id.get("open_id") or "unknown"
        sender = await bot.get_user_name(open_id)
        content_str = message.get("content", "{}")
        try:
            content_obj = json.loads(content_str)
            content = content_obj.get("text", content_str)
        except (json.JSONDecodeError, TypeError):
            content = content_str
        chat_id = message.get("chat_id", sender)
        chat_type = message.get("chat_type", "p2p")
        parent_id = message.get("parent_id") or message.get("root_id") or ""
        return {
            "userid": sender,
            "sender": sender,
            "content": content,
            "chatid": chat_id,
            "chattype": chat_type,
            "req_id": chat_id,
            "parent_id": parent_id,
            "quoted_content": "",
        }
    else:
        body = data.get("body", {})
        logger.info("WeCom message body: %s", json.dumps(body, ensure_ascii=False))
        userid = body.get("from", {}).get("userid", "unknown")
        msgtype = body.get("msgtype", "text")
        if msgtype == "text":
            raw_content = body.get("text", {}).get("content", "")
        else:
            raw_content = f"[{msgtype}] (non-text)"

        chatid = body.get("chatid", userid)
        chattype = body.get("chattype", "single")
        req_id = data.get("headers", {}).get("req_id", "")

        # Detect quoted reply: WeCom includes a "quote" field when user
        # quotes a bot message, containing the quoted message content.
        quote_data = body.get("quote")
        parent_id = "quoted" if quote_data else ""
        quoted_content = quote_data.get("text", {}).get("content", "") if quote_data else ""

        if userid == SPECIAL_USERID:
            lines = raw_content.strip().split("\n", 1)
            if len(lines) >= 2:
                sender = lines[0].strip()
                content = lines[1].strip()
                userid = sender
            else:
                sender = userid
                content = raw_content.strip()
        else:
            sender = userid
            content = raw_content

        return {
            "userid": userid,
            "sender": sender,
            "content": content,
            "chatid": chatid,
            "chattype": chattype,
            "req_id": req_id,
            "parent_id": parent_id,
            "quoted_content": quoted_content,
        }


async def _handle_bot_message(data: dict):
    msg = await _normalize_message(data)
    sender = msg["sender"]
    content = msg["content"]
    chatid = msg["chatid"]
    chattype = msg["chattype"]
    req_id = msg["req_id"]
    parent_id = msg.get("parent_id", "")
    quoted_content = msg.get("quoted_content", "")
    stream_id = str(uuid.uuid4())

    # If replying to a bot message (quoted reply), continue existing todo
    existing_todo = None
    if parent_id:
        if BOT_TYPE == "feishu":
            # Feishu: use parent_id (Feishu message_id) for precise lookup
            existing_todo = await find_todo_by_platform_msg_id(parent_id)
        if not existing_todo and quoted_content:
            # WeCom (or Feishu fallback): match by quoted content
            existing_todo = await find_todo_by_quoted_content(chatid, quoted_content)
        if not existing_todo:
            existing_todo = await find_recent_active_todo(chatid)

    if existing_todo:
        # Continue existing conversation
        todo_id = existing_todo["id"]
        is_new_todo = False
        await add_message(todo_id, "user", content)
        await sync_todo_queue(todo_id)
        logger.info("Continuing todo %s (quoted reply)", todo_id)
    else:
        # New conversation
        is_new_todo = True
        title_text = content.split("\n")[0][:50] if content else sender
        todo = await create_todo(title=title_text, content=content, userid=sender,
                                 chatid=chatid, chattype=chattype)
        todo_id = todo["id"]
        await add_message(todo_id, "user", f"发送人：{sender}\n内容：{content}")

    # WeCom: send immediate ack + keepalive; Feishu: no streaming needed
    keepalive_task = None
    if BOT_TYPE == "wecom":
        await bot.send_respond_msg(req_id, "正在处理，请稍候...", stream_id)
        keepalive_task = asyncio.create_task(
            _stream_keepalive(req_id, stream_id, interval=15))

    try:
        prompt = _build_prompt(sender, content)
        full_response, reply_message = await _run_agent_for_todo(
            todo_id, prompt, include_history=True)

        # Enforce reply_to_user tool: if the agent didn't call it, retry once.
        if not reply_message or not reply_message.strip():
            logger.warning("Agent did not call reply_to_user for todo %s; retrying with enforcement prompt", todo_id)
            if full_response and full_response.strip():
                retry_prompt = (
                    f"你刚才的输出内容是：\n{full_response.strip()}\n\n"
                    "注意：因为你没有调用 `reply_to_user` 工具，用户没有收到以上内容。\n"
                    "现在你必须调用 `reply_to_user` 工具，把上述内容完整发送给用户。"
                )
            else:
                retry_prompt = (
                    "注意：你刚才没有调用 `reply_to_user` 工具回复用户，导致用户没有收到任何消息。\n"
                    "现在你必须调用 `reply_to_user` 工具，把结论完整回复给用户。"
                )
            full_response, reply_message = await _run_agent_for_todo(
                todo_id, retry_prompt, include_history=True)

        final = reply_message or full_response
        if not final or not final.strip():
            # Fallback: generate a simple acknowledgment
            final = "已收到您的消息，已为您记录。"
    except Exception as e:
        logger.error(f"Agent processing failed for todo {todo_id}: {e}")
        await add_message(todo_id, "assistant", f"处理失败: {str(e)}")
        await sync_todo_queue(todo_id)
        final = f"处理失败: {str(e)}"
    finally:
        if keepalive_task:
            keepalive_task.cancel()
            with suppress(asyncio.CancelledError):
                await keepalive_task

    try:
        result = await bot.send_respond_msg(req_id, final, stream_id, finish=True)
        # Feishu: store the platform message_id for future quoted reply matching
        if BOT_TYPE == "feishu" and result:
            await set_last_assistant_platform_msg_id(todo_id, result)
        logger.info("Final response sent for todo %s", todo_id)
    except Exception as exc:
        logger.error("Failed to send final response for todo %s: %s", todo_id, exc)

    # Summarize title — only for new todos
    if is_new_todo:
        try:
            summary_prompt = (
                "你是一个标题总结助手。请用不超过20个字总结以下用户消息的标题，"
                "只输出标题文本，不要加引号或其他格式。\n"
                f"发送人：{sender}\n内容：{content}"
            )
            summary = await call_agent_simple(summary_prompt)
            summary = summary.strip()[:50]
            logger.info(f"Todo {todo_id} title summary: {summary!r}")
            if summary:
                await update_todo_title(todo_id, summary)
        except Exception as e:
            logger.warning(f"Failed to generate title for todo {todo_id}: {e}")


async def _handle_bot_event(data: dict):
    if BOT_TYPE == "feishu":
        event_type = data.get("header", {}).get("event_type", "")
        if event_type == "im.chat.member.bot.join_chat_v1":
            chat_id = data.get("event", {}).get("chat", {}).get("chat_id", "")
            if chat_id:
                await bot.send_welcome(chat_id,
                                       "你好！我是 AI 助手，有问题可以直接问我，"
                                       "我会帮你处理并记录为 Todo。")
    else:
        event_type = (data.get("body", {})
                      .get("event", {})
                      .get("eventtype", ""))
        if event_type == "enter_chat":
            req_id = data.get("headers", {}).get("req_id", "")
            await bot.send_welcome(req_id,
                                   "你好！我是 AI 助手，有问题可以直接问我，"
                                   "我会帮你处理并记录为 Todo。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_mcp_tools()  # Pre-load MCP tools at startup
    bot.on_message = _handle_bot_message
    bot.on_event = _handle_bot_event
    ws_task = asyncio.create_task(bot.connect())
    logger.info("Bot server starting (type=%s)...", BOT_TYPE)
    yield
    await bot.stop()
    ws_task.cancel()


app = FastAPI(title="AI Todo Dashboard", lifespan=lifespan, root_path=ROOT_PATH)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


# --- REST API ---


@app.get("/api/todos")
async def api_todos(status: str = None):
    return await get_todos(status)


@app.get("/api/todos/{todo_id}")
async def api_todo_detail(todo_id: int):
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    return todo


@app.delete("/api/todos/{todo_id}")
async def api_delete_todo(todo_id: int):
    from database import delete_todo as db_delete_todo
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    await db_delete_todo(todo_id)
    return {"status": "ok"}


class UpdateTodoRequest(BaseModel):
    title: str


@app.patch("/api/todos/{todo_id}")
async def api_update_todo(todo_id: int, req: UpdateTodoRequest):
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    await update_todo_title(todo_id, req.title)
    return {"status": "ok"}


@app.get("/api/todos/{todo_id}/messages")
async def api_messages(todo_id: int):
    return await get_messages(todo_id)


class ChatRequest(BaseModel):
    content: str


@app.post("/api/todos/{todo_id}/chat")
async def api_chat(todo_id: int, req: ChatRequest):
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")

    await add_message(todo_id, "user", req.content)
    await sync_todo_queue(todo_id)

    full_response, reply_message = await _run_agent_for_todo(
        todo_id,
        req.content,
        include_history=True,
    )
    return {"status": "ok", "response": reply_message or full_response}


@app.post("/api/todos/{todo_id}/complete")
async def api_complete_todo(todo_id: int):
    """Mark a todo as completed and auto-promote the next pending todo to doing."""
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    next_id = await complete_todo(todo_id)
    result = {"status": "ok"}
    if next_id:
        result["next_doing_id"] = next_id
    return result


class ReorderRequest(BaseModel):
    target_index: Optional[int] = None
    target_todo_id: Optional[int] = None
    position: Literal["top", "bottom"] = "bottom"
    reason: str = ""
    promote_to_doing: bool = False


@app.post("/api/todos/{todo_id}/reorder")
async def api_reorder_todo(todo_id: int, req: ReorderRequest):
    """Move a todo to a specific position in the list."""
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")

    success = await reorder_todo(
        todo_id,
        req.reason,
        promote_to_doing=req.promote_to_doing,
        target_index=req.target_index,
        target_todo_id=req.target_todo_id,
        position=req.position,
    )
    if not success:
        raise HTTPException(400, "Failed to reorder")

    return {"status": "ok"}


@app.get("/api/todos/{todo_id}/time-segments")
async def api_time_segments(todo_id: int):
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    return await get_time_segments(todo_id)


@app.post("/api/todos/{todo_id}/complete-from-pending")
async def api_complete_from_pending(todo_id: int):
    """Mark a pending todo as completed with timing logic."""
    todo = await get_todo(todo_id)
    if not todo:
        raise HTTPException(404, "Todo not found")
    if todo["status"] not in ("pending", "doing"):
        raise HTTPException(400, "Only pending or doing todos can be completed")
    next_id = await complete_from_pending(todo_id)
    result = {"status": "ok"}
    if next_id:
        result["next_doing_id"] = next_id
    return result


@app.get("/api/time-segments")
async def api_all_time_segments(todo_ids: str = ""):
    """Get time segments for multiple todos. Pass todo_ids as comma-separated string."""
    if not todo_ids:
        return {}
    ids = [int(x.strip()) for x in todo_ids.split(",") if x.strip().isdigit()]
    return await get_all_time_segments(ids)


@app.get("/api/stats")
async def api_stats():
    return await get_stats()


class WeeklyReportRequest(BaseModel):
    todo_ids: str = ""  # comma-separated IDs


@app.post("/api/weekly-report")
async def api_weekly_report(req: WeeklyReportRequest):
    """Generate a weekly report summary for the given todo IDs."""
    if not req.todo_ids:
        return {"report": ""}

    ids = [int(x.strip()) for x in req.todo_ids.split(",") if x.strip().isdigit()]
    if not ids:
        return {"report": ""}

    # Collect todo info with time segments
    todos_info = []
    for tid in ids:
        todo = await get_todo(tid)
        if not todo:
            continue
        segments = await get_time_segments(tid)
        total_minutes = sum(
            (seg.get("duration_minutes") or 0) for seg in segments
        )
        todos_info.append({
            "title": todo.get("title", ""),
            "status": todo.get("status", ""),
            "userid": todo.get("userid", ""),
            "created_at": todo.get("created_at", ""),
            "content": (todo.get("content") or "")[:200],
            "duration_minutes": round(total_minutes, 1),
        })

    if not todos_info:
        return {"report": ""}

    # Build prompt for LLM
    import json as _json
    todos_json = _json.dumps(todos_info, ensure_ascii=False, indent=2)
    report_prompt = (
        "你是一个工作总结助手。根据以下 Todo 列表，生成一份总结。\n\n"
        "要求：\n"
        "1. 按「需求」「沟通」「分析」「排查」「其他」分类归纳\n"
        "2. 每条注明耗时（如有）和当前状态（进行中/已完成/待处理）\n"
        "3. 详略得当：复杂的分析/排查多写几句，简单的记录一笔带过\n"
        "4. 最后加一个「总结」段落，概括整体进展\n"
        "5. 使用 Markdown 格式，简洁清晰\n\n"
        f"以下是 Todo 数据：\n{todos_json}"
    )

    report = await call_agent_simple(report_prompt)
    return {"report": report}


@app.get("/api/config")
async def api_config():
    return {"owner_name": OWNER_NAME, "project_base_dir": PROJECT_BASE_DIR, "llm_model": LLM_MODEL}


@app.get("/api/debug")
async def api_debug():
    return {
        "root_path": ROOT_PATH,
        "static_dir_exists": STATIC_DIR.exists(),
        "static_dir": str(STATIC_DIR)
    }


# --- Static Files ---
STATIC_DIR = Path(__file__).parent / "frontend" / "dist"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT)
