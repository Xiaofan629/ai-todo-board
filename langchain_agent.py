import json
import logging
import re
import subprocess
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain.agents import create_agent

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, PROJECT_BASE_DIR, MCP_CONFIG_PATH

logger = logging.getLogger("langchain_agent")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWLISTED_COMMANDS = {
    "cat", "head", "tail", "ls", "find", "grep", "rg", "wc", "file",
    "tree", "which", "pwd", "echo", "type", "stat", "diff",
}

_GIT_READ_ONLY_SUBCOMMANDS = {
    "log", "show", "diff", "status", "branch", "tag", "remote",
    "ls-files", "ls-tree", "rev-parse", "blame", "shortlog", "describe",
    "reflog",
}

_BLOCKED_PATTERNS = [
    ">>", ">",
    "sed -i", "rm", "rmdir", "mv", "cp", "chmod", "chown",
    "pip install", "npm install", "curl -X POST", "wget",
    "kill", "pkill", "mkfifo", "nc", "dd",
]

_MAX_OUTPUT_CHARS = 10000
_TOOL_TIMEOUT_SECONDS = 30


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def bash_read(command: str) -> str:
    """Execute a read-only shell command and return its output.

    Only allowlisted commands and git read-only subcommands are permitted.
    Any attempt to modify the filesystem will be rejected.
    """
    cmd_stripped = command.strip()

    for pattern in _BLOCKED_PATTERNS:
        # Operators and phrases: substring match; single words: word boundary match
        if ' ' in pattern or not pattern.isalnum():
            if pattern in cmd_stripped:
                return (
                    f"[blocked] 命令包含被禁止的模式 {pattern!r}，"
                    f"该命令会修改文件或系统，不允许执行。"
                    f"请换一种只读方式来获取信息，不要重试相同的命令。"
                )
        else:
            if re.search(r'\b' + re.escape(pattern) + r'\b', cmd_stripped):
                return (
                    f"[blocked] 命令包含被禁止的模式 {pattern!r}，"
                    f"该命令会修改文件或系统，不允许执行。"
                    f"请换一种只读方式来获取信息，不要重试相同的命令。"
                )

    parts = cmd_stripped.split()
    if not parts:
        return "[error] Empty command"

    base = parts[0]
    if base == "git" and len(parts) >= 2:
        subcmd = parts[1]
        if subcmd not in _GIT_READ_ONLY_SUBCOMMANDS:
            return (
                f"[blocked] git {subcmd} 不是只读子命令，不允许执行。"
                f"可用的 git 只读命令: {', '.join(sorted(_GIT_READ_ONLY_SUBCOMMANDS))}"
            )
    elif base not in _ALLOWLISTED_COMMANDS:
        return (
            f"[blocked] 命令 {base!r} 不在允许列表中，不允许执行。"
            f"可用的命令: {', '.join(sorted(_ALLOWLISTED_COMMANDS))}"
        )

    try:
        result = subprocess.run(
            cmd_stripped,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TOOL_TIMEOUT_SECONDS,
            cwd=str(PROJECT_BASE_DIR),
        )
        output = result.stdout
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr) if output else result.stderr
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"[timeout] Command timed out after {_TOOL_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return f"[error] {exc}"


@tool
def project_summary(project_name: str = "") -> str:
    """Return a directory tree summary of a project under the project base directory.

    Args:
        project_name: Optional subdirectory name under the project base directory.
    """
    target = Path(PROJECT_BASE_DIR)
    if project_name:
        target = target / project_name

    if not target.exists():
        return f"[error] Directory not found: {target}"

    try:
        result = subprocess.run(
            ["tree", "-L", "3", "--filelimit", "50", str(target)],
            capture_output=True, text=True, timeout=_TOOL_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            output = result.stdout
            if len(output) > _MAX_OUTPUT_CHARS:
                output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated]"
            return output
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        return "[timeout] tree command timed out"

    try:
        result = subprocess.run(
            ["find", str(target), "-maxdepth", "3", "-type", "f"],
            capture_output=True, text=True, timeout=_TOOL_TIMEOUT_SECONDS,
        )
        output = result.stdout
        if len(output) > _MAX_OUTPUT_CHARS:
            output = output[:_MAX_OUTPUT_CHARS] + "\n... [truncated]"
        return output or "(empty directory)"
    except Exception as exc:
        return f"[error] {exc}"


@tool
def reply_to_user(message: str) -> str:
    """Directly reply a message to the user. Use this to confirm actions like
    '已记录该 Todo' or to provide a quick answer that doesn't need investigation.

    Args:
        message: The reply message to send to the user.
    """
    return f"REPLY:{message}"


@tool
def investigate(issue_description: str) -> str:
    """Trigger a structured investigation for an issue. Use this when the user's
    request is NOT a simple todo but requires troubleshooting, debugging, or
    root-cause analysis.

    This tool provides an investigation framework. After calling it, you should
    follow the steps using your other tools (bash_read, MCP tools for DB queries,
    log inspection, and Grafana metrics).

    Args:
        issue_description: Brief description of the issue to investigate.
    """
    return (
        f"开始排查: {issue_description}\n\n"
        "排查步骤:\n"
        "1. **查数据库**: 使用 db-mcp 工具查询相关表，确认数据状态\n"
        "2. **查日志**: 使用 bash_read 查看相关服务日志 (如 kubectl logs, journalctl)\n"
        "3. **查 Grafana 打点**: 使用对应的 MCP 工具查看性能指标和告警\n"
        "4. **汇总结论**: 综合以上信息给出根因分析和建议\n\n"
        "请按以上步骤依次排查，每步给出关键发现。"
    )


BASE_TOOLS = [bash_read, project_summary, reply_to_user, investigate]


# ---------------------------------------------------------------------------
# MCP tool loading (from external config)
# ---------------------------------------------------------------------------

_mcp_tools_cache: list | None = None


async def init_mcp_tools() -> list:
    """Load MCP tools once from mcp_config.json and cache them."""
    global _mcp_tools_cache
    if _mcp_tools_cache is not None:
        return _mcp_tools_cache

    config_path = Path(MCP_CONFIG_PATH)
    if not config_path.exists():
        logger.info("No MCP config file found at %s", config_path)
        _mcp_tools_cache = []
        return []

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            mcp_config = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read MCP config: %s", exc)
        _mcp_tools_cache = []
        return []

    if not mcp_config:
        _mcp_tools_cache = []
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        connections = {}
        for name, conf in mcp_config.items():
            transport = conf.get("transport", "sse")
            entry: dict = {"transport": transport}
            if transport == "sse":
                entry["url"] = conf["url"]
            elif transport == "stdio":
                entry["command"] = conf["command"]
                if "args" in conf:
                    entry["args"] = conf["args"]
                if "env" in conf:
                    entry["env"] = conf["env"]
            else:
                logger.warning("Unknown MCP transport '%s' for %s, skipping", transport, name)
                continue
            connections[name] = entry

        if not connections:
            _mcp_tools_cache = []
            return []

        client = MultiServerMCPClient(connections)
        tools = await client.get_tools()
        logger.info("Loaded %d MCP tools from %d servers in %s",
                     len(tools), len(connections), config_path)
        _mcp_tools_cache = tools
        return tools
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed; skipping MCP tools")
        _mcp_tools_cache = []
        return []
    except Exception as exc:
        logger.warning("Failed to load MCP tools: %s", exc)
        _mcp_tools_cache = []
        return []


# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------

def _get_llm() -> ChatAnthropic:
    """Create a ChatAnthropic instance configured from environment variables."""
    return ChatAnthropic(
        model=LLM_MODEL,
        anthropic_api_key=LLM_API_KEY,
        anthropic_api_url=LLM_BASE_URL,
        temperature=0.7,
        max_tokens=4096,
    )


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------

# Default system prompt for the todo assistant
TODO_ASSISTANT_PROMPT = (
    "你是一个智能助手。用户发来的消息会自动记录为 Todo，你不需要重复确认。\n\n"
    "## 核心规则（必须遵守）\n"
    "无论你做了什么分析、查了什么数据，**最终都必须调用 `reply_to_user` 工具**回复用户。\n"
    "- 这是唯一能把消息发送给用户的方式，直接输出文字用户看不到\n"
    "- 哪怕只是简单确认、打招呼，也要用 `reply_to_user` 回复\n"
    "- 唯一例外：用户消息以「记录：」开头时，说明是纯记录，回复「已记录」即可\n"
    "- 绝对不能只输出文字就结束，不调用 `reply_to_user` = 用户什么也收不到，系统会要求你重新调用\n\n"
    "## 回复原则\n"
    "- 简单消息（打招呼、简单问题）：直接 `reply_to_user` 简短回复\n"
    "- 需要排查问题、查数据、查日志：先用分析工具，最后 `reply_to_user` 返回结论\n"
    "- 需要分析代码：用 `bash_read` 和 `project_summary` 工具分析，最后 `reply_to_user` 返回结论\n"
    "- 回复要简洁明了，不要重复用户的问题，直接给答案或结论\n\n"
    "## 可用工具\n"
    "- `bash_read`: 执行只读 shell 命令（查看文件、搜索代码、查看日志等）\n"
    "- `project_summary`: 获取项目目录结构\n"
    "- `investigate`: 启动结构化排查流程（查数据库 → 查日志 → 查指标 → 汇总）\n"
    "- `reply_to_user`: 回复用户（**每次对话必须调用一次**）\n"
    "- MCP 工具: 查询数据库、查看监控指标等\n\n"
    f"## 项目目录\n"
    f"所有项目代码在 {PROJECT_BASE_DIR} 目录下。\n"
)


# Cached agent graph
_agent = None
_agent_tools: list | None = None


async def _get_agent():
    """Create or return cached agent using langchain's create_agent."""
    global _agent, _agent_tools

    mcp_tools = await init_mcp_tools()
    all_tools = list(BASE_TOOLS) + mcp_tools

    # Rebuild only if tools changed
    if _agent is not None and _agent_tools == [t.name for t in all_tools]:
        return _agent

    llm = _get_llm()
    effective_prompt = TODO_ASSISTANT_PROMPT

    _agent = create_agent(
        model=llm,
        tools=all_tools,
        system_prompt=effective_prompt,
    )
    _agent_tools = [t.name for t in all_tools]
    logger.info("Agent created with %d tools", len(all_tools))
    return _agent


async def call_agent(
    prompt: str,
    system_prompt: str = "",
    history: Optional[List[dict]] = None,
) -> AsyncGenerator[dict, None]:
    """Stream agent responses using langgraph's built-in react agent."""
    if not prompt.strip():
        yield {"type": "error", "subtype": "invalid_prompt", "message": "Agent 调用失败: prompt 为空"}
        return

    if not LLM_API_KEY:
        yield {"type": "error", "subtype": "config_error", "message": "Agent 调用失败: LLM_API_KEY 未配置"}
        return

    # Build input messages
    input_messages: list = []

    if history:
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                input_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                input_messages.append(AIMessage(content=content))

    input_messages.append(HumanMessage(content=prompt))

    agent = await _get_agent()

    full_text = ""
    reply_message = ""  # Track reply_to_user content
    config = {" configurable": {}, "recursion_limit": 200}

    try:
        async for event in agent.astream_events(
            {"messages": input_messages},
            config=config,
            version="v2",
        ):
            kind = event.get("event", "")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk and hasattr(chunk, "content") and isinstance(chunk.content, str):
                    text = chunk.content
                    if text:
                        full_text += text
                        yield {
                            "type": "assistant",
                            "message": {
                                "role": "assistant",
                                "content": [{"type": "text", "text": text}],
                            },
                        }

            elif kind == "on_chat_model_end":
                output = data.get("output")
                if output and hasattr(output, "tool_calls") and output.tool_calls:
                    for tc in output.tool_calls:
                        # Capture reply_to_user message
                        if tc.get("name") == "reply_to_user":
                            reply_message = tc.get("args", {}).get("message", "")
                        yield {
                            "type": "assistant",
                            "message": {
                                "role": "assistant",
                                "content": [{
                                    "type": "tool_use",
                                    "id": tc.get("id", ""),
                                    "name": tc.get("name", "unknown"),
                                    "input": tc.get("args", {}),
                                }],
                            },
                        }

            elif kind == "on_tool_end":
                output = data.get("output")
                if output:
                    result_str = output.content if hasattr(output, "content") else str(output)
                    tool_name = event.get("name", "unknown")

                    yield {
                        "type": "result",
                        "subtype": "tool_result",
                        "result": result_str,
                        "tool_name": tool_name,
                    }

        # Final result event — prefer reply_to_user content over raw text
        yield {
            "type": "result",
            "subtype": "success",
            "result": reply_message or full_text,
            "reply_message": reply_message,
        }

    except Exception as exc:
        logger.error("Agent streaming error: %s", exc)
        yield {"type": "error", "subtype": "agent_error", "message": str(exc)}


async def call_agent_simple(prompt: str) -> str:
    """Simple one-shot LLM call without tools. Used for title summarization."""
    if not LLM_API_KEY:
        return ""

    llm = _get_llm()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        if isinstance(response.content, str):
            return response.content
        texts = []
        for block in response.content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
            elif isinstance(block, str):
                texts.append(block)
        return "\n".join(texts)
    except Exception as exc:
        logger.error("Simple agent call failed: %s", exc)
        return ""
