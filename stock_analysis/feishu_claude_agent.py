"""
飞书 Claude Agent — Tool-calling 引擎
通过 OpenAI SDK 调 DeepSeek，支持代码执行 + 本地数据读取。
"""
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any

from openai import OpenAI

from config import DEEPSEEK_API_KEY, PROJECT_DIR

logger = logging.getLogger("claude_agent")

# ── API 配置 ──────────────────────────────────────────────
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL = "deepseek-chat"
CODE_TIMEOUT = 60  # Python 代码执行超时（秒）
MAX_HISTORY = 30   # 每会话保留最大消息数
MAX_TOOL_OPS = 25  # 单次处理最大工具调用轮次

ALLOWED_DIRS = [
    PROJECT_DIR.resolve(),
    Path("D:/1989n/stock_data").resolve(),
    Path("D:/1989n/.claude").resolve(),
]

CONVERSATIONS_DIR = PROJECT_DIR / "conversations"
CONVERSATIONS_DIR.mkdir(exist_ok=True)

# ── API Key 获取（settings.json 回退）────────────────────
def _resolve_api_key() -> str:
    """获取 DeepSeek API Key。优先用 settings.json 中 Claude 在用的 key。"""
    candidates = [
        PROJECT_DIR.parent / ".claude" / "settings.json",
        PROJECT_DIR.parent / ".claude" / "settings.local.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                cfg = json.loads(p.read_text(encoding="utf-8"))
                env = cfg.get("env", {})
                for k in ("ANTHROPIC_AUTH_TOKEN", "DEEPSEEK_API_KEY"):
                    val = env.get(k, "")
                    if val:
                        return val
        except Exception:
            continue
    # fallback: .env 中的 key
    if DEEPSEEK_API_KEY and "your" not in DEEPSEEK_API_KEY.lower():
        return DEEPSEEK_API_KEY
    return ""


_API_KEY = _resolve_api_key()
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


# ── 对话记忆 ──────────────────────────────────────────────
def _conversation_path(chat_id: str) -> Path:
    safe = chat_id.replace("/", "_").replace("\\", "_")
    return CONVERSATIONS_DIR / f"{safe}.json"


def _load_history(chat_id: str) -> list[dict]:
    p = _conversation_path(chat_id)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data = data[-MAX_HISTORY:]
            # 移除历史截断导致的孤立 tool 消息
            data = _strip_orphaned_tools(data)
            return data
        except Exception:
            logger.warning("Corrupt conversation file: %s", p)
    return []


def _strip_orphaned_tools(messages: list[dict]) -> list[dict]:
    """移除所有孤立 tool 消息（前面没有对应的 assistant.tool_calls）。

    对话截断到 MAX_HISTORY 条时，可能切在 tool 消息中间，导致
    tool 消息找不到匹配的 assistant.tool_calls → API 400 错误。
    """
    result: list[dict] = []
    pending_tool_ids: set[str] = set()

    for msg in messages:
        role = msg.get("role")
        if role == "assistant":
            # 携带本次 tool_call 的 id 集合
            pending_tool_ids = {
                tc.get("id", "") for tc in msg.get("tool_calls", [])
                if isinstance(tc, dict)
            }
            result.append(msg)
        elif role == "tool":
            tc_id = msg.get("tool_call_id", "")
            if tc_id in pending_tool_ids:
                result.append(msg)
            else:
                logger.warning("Dropping orphaned tool msg: tool_call_id=%s", tc_id)
        else:
            # user / system 等
            pending_tool_ids = set()
            result.append(msg)

    return result


def _save_history(chat_id: str, messages: list[dict]) -> None:
    p = _conversation_path(chat_id)
    try:
        p.write_text(
            json.dumps(messages[-MAX_HISTORY:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        logger.exception("Failed to save conversation")


# ── 系统提示 ──────────────────────────────────────────────
SYSTEM_PROMPT = textwrap.dedent("""\
    你是一位A股投资助手，通过飞书与用户对话。

    ## 输出格式 — 第一行必须是分类标签
    每次回复的第一行必须是以下分类之一（不含其他文字）：
    📊 行情分析
    📈 持仓报告
    ⚠️ 风险提醒
    💬 问答

    然后空一行，再输出正式内容。

    ## 核心原则
    1. **数据准确性优先** — 查询价格/持仓/财务时必须用工具的 `run_python` 读本地数据，不能依赖训练数据。
    2. **结果导向** — 给出明确结论和具体数字，不加模糊表述。
    3. **止损纪律** — 检查持仓时必须对比最新价与成本，明确盈亏金额和比例。
    4. **交易合规** — 你只提供分析，不下单、不给投资建议。分析末尾加「仅供参考，不构成投资建议」。

    ## 工具使用原则
    - 分析类问题 → `run_python` 读 Parquet/CSV/数据库
    - 已有脚本能做的事 → `run_script` 调用
    - 需要看原始数据文件 → `read_file`
    - 不要为简单问题就执行代码——只有需要实时/本地数据时才用工具
""")


# ── 工具定义 ──────────────────────────────────────────────
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "执行 Python 代码做数据分析和计算。可导入 pandas、numpy 等标准库。"
                           "结果用 print() 输出",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 代码。import 语句放在开头，用 print() 输出结果",
                    }
                },
                "required": ["code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取本地文件内容。支持 txt/json/csv/parquet/md。"
                           "超过 2000 行的文件只返回末尾行数",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径，相对于 stock_analysis/ 或 stock_data/ 目录",
                    },
                    "max_lines": {
                        "type": "number",
                        "description": "最大读取行数（默认 200）",
                        "default": 200,
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "运行 stock_analysis/ 下的分析脚本（如 stock_quote.py, portfolio_guard.py）。"
                           "不支持交互式脚本",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "脚本文件名（如 stock_quote.py）",
                    },
                    "args": {
                        "type": "string",
                        "description": "命令行参数（可选）",
                        "default": "",
                    },
                },
                "required": ["script"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容，了解可用文件和子目录",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要列出的目录路径（相对于 stock_analysis/）",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        },
    },
]


# ── 工具执行 ──────────────────────────────────────────────
def _validate_path(requested: str) -> Path | None:
    """验证并返回绝对路径，防止目录遍历攻击"""
    try:
        p = Path(requested).resolve()
        for allowed in ALLOWED_DIRS:
            try:
                p.relative_to(allowed)
                return p
            except ValueError:
                continue
        # 也允许直接访问 stock_analysis/
        try:
            p.relative_to(PROJECT_DIR)
            return p
        except ValueError:
            pass
        logger.warning("Path traversal blocked: %s", requested)
        return None
    except Exception:
        return None


def _tool_run_python(code: str) -> str:
    """在子进程中执行 Python 代码"""
    logger.info("Executing Python code (%d chars)", len(code))
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=CODE_TIMEOUT,
            cwd=str(PROJECT_DIR),
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        if proc.returncode != 0:
            parts.append(f"[exit code: {proc.returncode}]")
        return "\n".join(parts) if parts else "(无输出)"
    except subprocess.TimeoutExpired:
        return f"[超时：代码执行超过 {CODE_TIMEOUT}s]"
    except Exception as e:
        return f"[执行错误] {e}"


def _tool_read_file(path: str, max_lines: int = 200) -> str:
    """读取文件内容"""
    p = _validate_path(path)
    if not p:
        p = _validate_path(str(PROJECT_DIR / path))
    if not p or not p.exists():
        return f"[文件不存在: {path}]"
    if p.is_dir():
        return f"[{path} 是目录，请用 list_directory]"
    try:
        text = p.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines.append(f"\n... (共 {len(text.splitlines())} 行，仅显示前 {max_lines})")
        return "\n".join(lines)
    except Exception as e:
        try:
            size = p.stat().st_size
            return f"[{p.name}: {size:,} bytes (二进制文件，无法直接读取)]"
        except Exception:
            return f"[读取失败] {e}"


def _tool_run_script(script: str, args: str = "") -> str:
    """运行 stock_analysis/ 下的已有脚本"""
    script_path = PROJECT_DIR / script
    if not script_path.exists():
        return f"[脚本不存在: {script}]"
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd.extend(args.split())
    logger.info("Running script: %s %s", script, args)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=CODE_TIMEOUT,
            cwd=str(PROJECT_DIR),
        )
        out = proc.stdout.strip()
        err = proc.stderr.strip()
        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        if proc.returncode != 0:
            parts.append(f"[exit code: {proc.returncode}]")
        return "\n".join(parts) if parts else "(无输出)"
    except subprocess.TimeoutExpired:
        return f"[超时：脚本执行超过 {CODE_TIMEOUT}s]"
    except Exception as e:
        return f"[执行错误] {e}"


def _tool_list_directory(path: str) -> str:
    """列出目录内容"""
    p = _validate_path(path)
    if not p:
        p = _validate_path(str(PROJECT_DIR / path))
    if not p or not p.exists():
        return f"[目录不存在: {path}]"
    if not p.is_dir():
        return f"[{path} 不是目录]"
    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
        lines = []
        for item in items:
            suffix = "/" if item.is_dir() else ""
            size = item.stat().st_size if item.is_file() else 0
            if size:
                lines.append(f"  {item.name}{suffix}  ({size:,} bytes)")
            else:
                lines.append(f"  {item.name}{suffix}")
        header = f"目录: {path}  ({len(items)} 项)"
        return header + "\n" + "\n".join(lines)
    except Exception as e:
        return f"[列出失败] {e}"


TOOL_DISPATCH = {
    "run_python": _tool_run_python,
    "read_file": _tool_read_file,
    "run_script": _tool_run_script,
    "list_directory": _tool_list_directory,
}


# ── 消息处理 ──────────────────────────────────────────────
def process_message(text: str, chat_id: str = "default") -> str:
    """处理用户消息，返回回复文本"""
    client = _get_client()
    if not client.api_key:
        return "出错：API Key 未配置，请在 .env 中设置 DEEPSEEK_API_KEY"

    history = _load_history(chat_id)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": text})

    # 多轮 tool calling
    for turn in range(MAX_TOOL_OPS):
        # 发送前防御校验：确保无孤立 tool 消息
        messages = _strip_orphaned_tools(messages)
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=4096,
                timeout=60,
            )
        except Exception as e:
            logger.exception("API call failed (turn %d)", turn)
            return f"API 调用失败: {e}"

        choice = resp.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            # 最终回复
            final = msg.content or "(无回复)"
            _save_history(chat_id, messages[1:] + [{"role": "assistant", "content": final}])
            return final

        # 处理工具调用
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            try:
                fn_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            handler = TOOL_DISPATCH.get(fn_name)
            if handler:
                logger.info("Tool call: %s %s", fn_name, fn_args)
                result = handler(**fn_args)
            else:
                result = f"[未知工具: {fn_name}]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        if turn == MAX_TOOL_OPS - 1:
            # 最后一轮强制模型输出文本
            messages.append({
                "role": "user",
                "content": "请基于以上结果给出最终回答。不要再用工具。",
            })

    # 超出最大轮次
    final = "抱歉，我需要更多步骤才能完成这个分析，但已到达处理上限。请简化你的问题。"
    _save_history(chat_id, messages[1:] + [{"role": "assistant", "content": final}])
    return final


# ── 快速测试 ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    test = sys.argv[1] if len(sys.argv) > 1 else "查一下桂冠电力最新行情"
    print(f"问题: {test}\n")
    result = process_message(test, chat_id="test")
    print(f"回答:\n{result}")
