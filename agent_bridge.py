import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from config import CLAUDE_BIN, CLAUDE_MODEL

logger = logging.getLogger("agent_bridge")


def build_transcript_prompt(messages: list[dict]) -> str:
    if not messages:
        return ""

    lines = [
        "下面是当前任务的历史对话，请基于这些上下文继续处理最后一个用户请求。",
        "",
    ]
    for message in messages:
        role = message.get("role", "user").upper()
        content = (message.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{role}:")
        lines.append(content)
        lines.append("")

    lines.append("请继续处理最后一个用户请求。")
    return "\n".join(lines).strip()


def _build_command(prompt: str, resume_session_id: Optional[str] = None) -> list[str]:
    cmd = [
        CLAUDE_BIN,
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        "--permission-mode",
        "bypassPermissions",
    ]
    if CLAUDE_MODEL:
        cmd.extend(["--model", CLAUDE_MODEL])
    if resume_session_id:
        cmd.extend(["--resume", resume_session_id])
    cmd.append(prompt)
    return cmd


async def call_agent(prompt: str, resume_session_id: Optional[str] = None) -> AsyncGenerator[dict, None]:
    """Call Claude Code CLI in bypass-permissions mode and yield NDJSON events."""
    if not prompt.strip():
        yield {
            "type": "error",
            "subtype": "invalid_prompt",
            "message": "Claude Code 调用失败: prompt 为空",
        }
        return

    cmd = _build_command(prompt, resume_session_id=resume_session_id)
    logger.info("Starting Claude Code CLI: %s", " ".join(cmd[:-1]))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(Path(__file__).parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("Claude CLI not found: %s", CLAUDE_BIN)
        yield {
            "type": "error",
            "subtype": "cli_missing",
            "message": f"Claude Code CLI 不可用: 未找到 {CLAUDE_BIN}",
        }
        return
    except Exception as exc:
        logger.error("Failed to start Claude CLI: %s", exc)
        yield {
            "type": "error",
            "subtype": "cli_start_failed",
            "message": f"Claude Code 启动失败: {exc}",
        }
        return

    stderr_task = asyncio.create_task(proc.stderr.read())

    try:
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break

            raw_line = line.decode("utf-8", errors="replace").strip()
            if not raw_line:
                continue

            try:
                yield json.loads(raw_line)
            except json.JSONDecodeError:
                logger.warning("Skipping non-JSON Claude output: %s", raw_line)

        return_code = await proc.wait()
        stderr_output = (await stderr_task).decode("utf-8", errors="replace").strip()

        if return_code != 0:
            logger.error("Claude CLI exited with code %s: %s", return_code, stderr_output)
            yield {
                "type": "error",
                "subtype": "cli_exit_error",
                "message": stderr_output or f"Claude Code 退出异常，退出码 {return_code}",
            }
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
