"""
============================================================
Agent 共享工具（新旧引擎公用的纯逻辑）
============================================================
从原 agent_executor.py 抽出的无状态辅助函数，供 LangGraph 深度模式引擎
(src/agent/graph/) 与 API 层 /stats 复用：

  - TokenTracker / get_token_stats / _extract_token_usage：token 用量统计
  - _extract_tool_calls：从 LLM 响应解析 tool_calls（兼容 LangChain / OpenAI 格式）
  - _tool_result_to_text：工具结果截断/摘要化为 ToolMessage 内容
  - _RE_MODIFY_KEYWORDS：局部修改请求关键词（预编译正则）
  - build_tool_end：按工具类型构造 tool_end 事件 data

这些函数不持有运行时状态，可安全跨引擎、跨请求共享。
"""

import json
import re
import threading
from typing import Dict, Any, List

from src.infra.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Token 用量追踪
# ============================================================

class TokenTracker:
    """跨请求的 LLM token 用量统计器（线程安全）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_calls = 0

    def record(self, prompt_tokens: int = 0, completion_tokens: int = 0):
        with self._lock:
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            self.total_calls += 1

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "calls": self.total_calls,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
            }


# 模块级全局跟踪器（新引擎在 agent_node 里 record，/stats 读取快照）
_token_tracker = TokenTracker()


def get_token_stats() -> dict:
    """获取全局 token 用量快照。"""
    return _token_tracker.snapshot()


def _extract_token_usage(response) -> tuple:
    """
    从 LLM 响应中提取 token 用量。

    兼容 LangChain AIMessage.response_metadata 和
    原生 OpenAI usage 对象。
    """
    try:
        meta = getattr(response, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {}) or meta.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
        return (prompt_tokens or 0, completion_tokens or 0)
    except Exception:
        return (0, 0)


# ============================================================
# 预编译正则模式（避免每次调用时重复编译）
# ============================================================

# 修改模式关键词检测（按长度降序，优先匹配长词）
_RE_MODIFY_KEYWORDS = [
    re.compile(r"把.*改成"),
    re.compile(r"将.*改为"),
    re.compile(r"修改"),
    re.compile(r"换成"),
    re.compile(r"调整"),
    re.compile(r"更新"),
    re.compile(r"替换"),
    re.compile(r"变更"),
    re.compile(r"修正"),
    re.compile(r"换一下"),
    re.compile(r"改一下"),
    re.compile(r"改"),
]


# ============================================================
# 工具调用提取
# ============================================================

def _extract_tool_calls(response) -> List[Dict[str, Any]]:
    """
    从 LLM 响应中提取 tool calls，兼容 LangChain 和原生 OpenAI 格式。

    LangChain AIMessage 格式：
        response.tool_calls = [
            {"name": "search_exemplars", "args": {"query": "..."}, "id": "call_xxx"}
        ]

    原生 OpenAI 格式（可能在 additional_kwargs 中）：
        response.additional_kwargs["tool_calls"] = [
            {"id": "call_xxx", "type": "function",
             "function": {"name": "search_exemplars", "arguments": '{"query": "..."}'}}
        ]
    """
    result = []

    # ---- 方式 1：LangChain AIMessage.tool_calls ----
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            if isinstance(tc, dict):
                name = tc.get("name", "")
                args = tc.get("args", {})
                tc_id = tc.get("id", f"call_{hash(str(tc))}")
            else:
                name = getattr(tc, "name", "")
                args = getattr(tc, "args", {})
                tc_id = getattr(tc, "id", f"call_{hash(str(tc))}")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    logger.warning(f"工具参数 JSON 解析失败：{args[:100]}")
                    args = {}
            result.append({"name": name, "args": args, "id": tc_id})

    # ---- 方式 2：additional_kwargs（OpenAI 原生格式）----
    if not result and hasattr(response, "additional_kwargs"):
        # 注意：DeepSeek 在无工具调用时返回 "tool_calls": null，
        # dict.get("key", default) 只在 key 不存在时用 default，
        # key 存在但值为 None 时会返回 None，导致 for tc in None 报错。
        raw = response.additional_kwargs.get("tool_calls") or []
        for tc in raw:
            func = tc.get("function", {})
            name = func.get("name", "")
            args_str = func.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                logger.warning(f"工具参数 JSON 解析失败：{args_str[:100]}")
                args = {}
            result.append({
                "name": name,
                "args": args,
                "id": tc.get("id", f"call_{hash(args_str)}"),
            })

    return result


def _tool_result_to_text(tool_name: str, raw_result: str) -> str:
    """
    将工具返回值截断/摘要化为 ToolMessage 的 content，
    避免 context 无限膨胀。
    """
    if tool_name == "search_exemplars":
        # 每篇已在工具中截断到 600 字，4 篇 ≈ 2400+ 字符，留足余量
        return raw_result[:4000]
    elif tool_name == "check_format":
        # 只保留 summary + critical issues
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            issues = data.get("issues", [])
            critical = [i for i in issues if i.get("status") == "issue"]
            summary = data.get("summary", "")
            # 精简反馈
            slim = {
                "critical_count": len(critical),
                "summary": summary,
                "issues": critical,  # 只传有问题的条目
            }
            return json.dumps(slim, ensure_ascii=False)
        except Exception:
            return raw_result[:500]
    elif tool_name == "refine_draft":
        # 草稿全文，但限制长度
        return raw_result[:3000]
    else:
        return raw_result[:500]


# ============================================================
# SSE 事件构造辅助
# ============================================================

def build_tool_end(tool_name: str, raw_result: str) -> Dict[str, Any]:
    """根据工具类型构造 tool_end 事件 data。"""
    if tool_name == "search_exemplars":
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            return {
                "tool": tool_name,
                "result": {
                    "total_found": data.get("total_found", 0),
                    "exemplars": data.get("exemplars", []),
                },
            }
        except Exception:
            return {"tool": tool_name, "result": {"total_found": 0, "exemplars": []}}

    elif tool_name == "check_format":
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            return {
                "tool": tool_name,
                "result": {
                    "issues": data.get("issues", []),
                    "critical_count": data.get("critical_count", 0),
                    "summary": data.get("summary", ""),
                },
            }
        except Exception:
            return {"tool": tool_name, "result": {"issues": [], "critical_count": 0, "summary": "检查解析失败"}}

    elif tool_name == "refine_draft":
        return {
            "tool": tool_name,
            "result": {"char_count": len(raw_result) if raw_result else 0},
        }

    elif tool_name == "finish":
        return {"tool": tool_name, "result": {"summary": "任务完成"}}

    else:
        return {"tool": tool_name, "result": {}}
