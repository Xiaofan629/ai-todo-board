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

from agent_bridge import build_transcript_prompt, call_agent
from config import SERVER_HOST, SERVER_PORT, OWNER_NAME, SPECIAL_USERID, ROOT_PATH, PROJECT_BASE_DIR
from database import (add_message, complete_todo, create_todo, get_messages,
                      get_todo, get_todos, get_stats, init_db,
                      reorder_todo, set_todo_claude_session_id,
                      set_todo_processing,
                      sync_todo_queue, update_todo_title)
from wecom_ws import WeComWS

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

wecom = WeComWS()

# System prompt prefix for plan-only mode
PLAN_MODE_PREFIX = (
    "你是一个代码分析助手，请严格按照以下规则工作：\n"
    "1. **绝对不要修改任何文件**，只进行分析和规划\n"
    f"2. 所有项目都在 {PROJECT_BASE_DIR} 目录下，请在该目录下查找和分析项目代码\n"
    "3. 如果分析结果涉及代码改动，请严格按以下格式输出，每个项目一个条目：\n"
    "   【项目名】\n"
    "   原因：为什么要改\n"
    "   改动点：具体改什么文件、改什么内容\n"
    "\n"
    "---\n"
)


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
    if event_type in {"assistant", "user"}:
        return _extract_text_from_content(event.get("message", {}).get("content"))
    if event_type == "result":
        return (event.get("result") or "").strip()
    if event_type == "error":
        return (event.get("message") or event.get("content") or "").strip()
    if event_type == "system":
        subtype = event.get("subtype", "")
        if subtype == "api_retry":
            attempt = event.get("attempt")
            max_retries = event.get("max_retries")
            error = event.get("error") or "unknown"
            return f"API 重试 {attempt}/{max_retries}: {error}"
        return ""
    return ""


def _should_persist_event(event: dict) -> bool:
    event_type = event.get("type", "")
    subtype = event.get("subtype", "")
    if event_type not in {"assistant", "user", "system", "result", "error"}:
        return False
    if event_type == "system" and subtype in {"init", "hook_started", "hook_response"}:
        return False
    return True


async def _run_agent_for_todo(todo_id: int, prompt: str,
                              resume_session_id: Optional[str] = None) -> str:
    full_response = ""
    current_session_id = resume_session_id

    await set_todo_processing(todo_id, True)
    try:
        async for event in call_agent(prompt, resume_session_id=resume_session_id):
            event_session_id = event.get("session_id")
            if event_session_id and event_session_id != current_session_id:
                current_session_id = event_session_id
                await set_todo_claude_session_id(todo_id, event_session_id)

            if not _should_persist_event(event):
                continue

            payload = json.dumps(event, ensure_ascii=False)
            event_type = event.get("type", "")
            event_subtype = event.get("subtype", "")
            role = event_type if event_type in {"assistant", "user"} else "system"
            text = _extract_event_text(event)
            await add_message(
                todo_id,
                role,
                text,
                event_type=event_type,
                event_subtype=event_subtype,
                payload=payload,
            )

            if event_type == "assistant" and text:
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

    return full_response


async def _stream_keepalive(req_id: str, stream_id: str, interval: int = 15):
    """Periodically send stream messages to prevent WeChat stream timeout."""
    count = 1
    while True:
        await asyncio.sleep(interval)
        try:
            await wecom.send_respond_msg(
                req_id, f"还在处理中，请稍候...({count})", stream_id)
            logger.info("Stream keepalive sent for req_id=%s count=%s", req_id, count)
            count += 1
        except Exception as exc:
            logger.warning("Stream keepalive failed for req_id=%s: %s", req_id, exc)
            break


async def _handle_wecom_message(data: dict):
    body = data.get("body", {})
    userid = body.get("from", {}).get("userid", "unknown")
    msgtype = body.get("msgtype", "text")
    if msgtype == "text":
        raw_content = body.get("text", {}).get("content", "")
    else:
        raw_content = f"[{msgtype}] (non-text)"

    chatid = body.get("chatid", userid)
    chattype = body.get("chattype", "single")
    req_id = data.get("headers", {}).get("req_id", "")
    stream_id = str(uuid.uuid4())

    # If message is from SPECIAL_USERID, parse first line as sender, rest as content
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

    title_text = content.split("\n")[0][:50] if content else sender
    todo = await create_todo(title=title_text, content=content, userid=sender,
                             chatid=chatid, chattype=chattype)
    todo_id = todo["id"]
    await add_message(todo_id, "user", f"发送人：{sender}\n内容：{content}")
    await wecom.send_respond_msg(req_id, "正在处理，请稍候...", stream_id)

    # Start keepalive task to prevent stream timeout during long CC processing
    keepalive_task = asyncio.create_task(
        _stream_keepalive(req_id, stream_id, interval=15))

    try:
        prompt = f"发送人：{sender}\n内容：{content}"
        full_response = await _run_agent_for_todo(todo_id, PLAN_MODE_PREFIX + prompt)
        final = full_response or "处理完成"

        # Also send keepalive during title summarization
        try:
            summary_prompt = (
                "请用不超过20个字总结以下内容的标题，只输出标题文本，不要加引号或其他格式：\n"
                f"发送人：{sender}\n内容：{content}"
            )
            summary = ""
            async for event in call_agent(PLAN_MODE_PREFIX + summary_prompt):
                if event.get("type") == "assistant":
                    text = _extract_event_text(event)
                    if text:
                        summary += text
                elif event.get("type") == "result":
                    text = (event.get("result") or "").strip()
                    if text:
                        summary = text
            summary = summary.strip()[:50]
            logger.info(f"Todo {todo_id} title summary: {summary!r}")
            if summary:
                await update_todo_title(todo_id, summary)
        except Exception as e:
            logger.warning(f"Failed to generate title for todo {todo_id}: {e}")
    except Exception as e:
        logger.error(f"Agent processing failed for todo {todo_id}: {e}")
        await add_message(todo_id, "assistant", f"处理失败: {str(e)}")
        await sync_todo_queue(todo_id)
        final = f"处理失败: {str(e)}"
    finally:
        keepalive_task.cancel()
        with suppress(asyncio.CancelledError):
            await keepalive_task

    # Send final response
    try:
        await wecom.send_respond_msg(req_id, final, stream_id, finish=True)
        logger.info("Final response sent for todo %s req_id=%s", todo_id, req_id)
    except Exception as exc:
        logger.error("Failed to send final response for todo %s req_id=%s: %s", todo_id, req_id, exc)


async def _handle_wecom_event(data: dict):
    event_type = (data.get("body", {})
                  .get("event", {})
                  .get("eventtype", ""))
    if event_type == "enter_chat":
        req_id = data.get("headers", {}).get("req_id", "")
        await wecom.send_welcome(req_id,
                                 "你好！我是 AI 助手，有问题可以直接问我，"
                                 "我会帮你处理并记录为 Todo。")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    wecom.on_message = _handle_wecom_message
    wecom.on_event = _handle_wecom_event
    ws_task = asyncio.create_task(wecom.connect())
    logger.info("WeCom Bot server starting...")
    yield
    await wecom.stop()
    ws_task.cancel()


app = FastAPI(title="WeCom Bot + Todo Dashboard", lifespan=lifespan, root_path=ROOT_PATH)
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

    existing = await get_messages(todo_id)
    claude_session_id = todo.get("claude_session_id") or None
    if claude_session_id:
        prompt = PLAN_MODE_PREFIX + req.content
    else:
        history = []
        for message in existing:
            if message["role"] in {"user", "assistant"} and message["content"]:
                history.append({"role": message["role"], "content": message["content"]})
        prompt = PLAN_MODE_PREFIX + build_transcript_prompt(history)

    full_response = await _run_agent_for_todo(
        todo_id,
        prompt,
        resume_session_id=claude_session_id,
    )
    return {"status": "ok", "response": full_response}


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


@app.get("/api/stats")
async def api_stats():
    return await get_stats()


@app.get("/api/config")
async def api_config():
    return {"owner_name": OWNER_NAME, "project_base_dir": PROJECT_BASE_DIR}


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
