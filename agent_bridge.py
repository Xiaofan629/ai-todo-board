import asyncio
import json
import logging
import os
import shutil
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from config import CLAUDE_BIN, CLAUDE_MODEL

logger = logging.getLogger("agent_bridge")
_RESOLVED_CLAUDE_BIN: Optional[str] = None


def _candidate_claude_paths(bin_name: str) -> List[str]:
    if "/" in bin_name:
        return [bin_name]

    candidates: List[str] = []
    resolved = shutil.which(bin_name)
    if resolved:
        candidates.append(resolved)

    home = Path.home()
    known_paths = [
        home / ".local" / "bin" / bin_name,
        home / ".bun" / "bin" / bin_name,
        Path("/opt/homebrew/bin") / bin_name,
        Path("/usr/local/bin") / bin_name,
    ]
    for path in known_paths:
        path_str = str(path)
        if path_str not in candidates:
            candidates.append(path_str)

    # nvm installs place binaries under versioned node directories.
    nvm_versions = sorted(
        (home / ".nvm" / "versions" / "node").glob("*/bin"),
        reverse=True,
    )
    for bin_dir in nvm_versions:
        path_str = str(bin_dir / bin_name)
        if path_str not in candidates:
            candidates.append(path_str)

    return candidates


async def _resolve_claude_bin() -> Optional[str]:
    global _RESOLVED_CLAUDE_BIN

    if _RESOLVED_CLAUDE_BIN and Path(_RESOLVED_CLAUDE_BIN).exists():
        return _RESOLVED_CLAUDE_BIN

    for candidate in _candidate_claude_paths(CLAUDE_BIN):
        if Path(candidate).exists():
            _RESOLVED_CLAUDE_BIN = candidate
            logger.info("Resolved Claude CLI to %s", candidate)
            return candidate

    # If PATH is incomplete in the current process, ask the user's login shell.
    shell = os.environ.get("SHELL") or "/bin/zsh"
    try:
        proc = await asyncio.create_subprocess_exec(
            shell,
            "-lc",
            f"command -v {shlex_quote(CLAUDE_BIN)}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        resolved = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and resolved and Path(resolved).exists():
            _RESOLVED_CLAUDE_BIN = resolved
            logger.info("Resolved Claude CLI via login shell: %s", resolved)
            return resolved
        if stderr:
            logger.warning("Login shell could not resolve Claude CLI: %s",
                           stderr.decode("utf-8", errors="replace").strip())
    except Exception as exc:
        logger.warning("Failed to resolve Claude CLI via login shell: %s", exc)

    return None


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def build_transcript_prompt(messages: List[dict]) -> str:
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


def _build_command(claude_bin: str, prompt: str,
                   resume_session_id: Optional[str] = None) -> List[str]:
    cmd = [
        claude_bin,
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

    resolved_claude_bin = await _resolve_claude_bin()
    if not resolved_claude_bin:
        logger.error("Claude CLI not found. configured=%s path=%s", CLAUDE_BIN, os.environ.get("PATH", ""))
        yield {
            "type": "error",
            "subtype": "cli_missing",
            "message": (
                f"Claude Code CLI 不可用: 未找到 {CLAUDE_BIN}。"
                "请在 .env 中设置 CLAUDE_BIN 为 claude 的绝对路径。"
            ),
        }
        return

    cmd = _build_command(resolved_claude_bin, prompt, resume_session_id=resume_session_id)
    logger.info("Starting Claude Code CLI: %s", " ".join(cmd[:-1]))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(Path(__file__).parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("Claude CLI not found when starting: configured=%s resolved=%s",
                     CLAUDE_BIN, resolved_claude_bin)
        yield {
            "type": "error",
            "subtype": "cli_missing",
            "message": (
                f"Claude Code CLI 不可用: 未找到 {resolved_claude_bin}。"
                "请确认该文件存在，或在 .env 中设置 CLAUDE_BIN。"
            ),
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
