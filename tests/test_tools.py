"""
============================================================
测试：Agent 工具集（tools.py）
============================================================
重点回归 check_format 的两个历史 bug：
  1. CHECK_FORMAT_PROMPT 含 JSON 花括号，用 str.format() 会抛 KeyError。
  2. LLM 调用异常时 except 分支引用未定义的 text 变量导致 NameError。
"""

import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage

from src.domain.tools import CHECK_FORMAT_PROMPT, check_format


class TestCheckFormatPromptInjection:
    """CHECK_FORMAT_PROMPT 变量注入（回归 KeyError bug）。"""

    def test_replace_injection_no_crash(self):
        """含 JSON 示例花括号的 prompt 用 replace 注入不应抛异常。"""
        prompt = CHECK_FORMAT_PROMPT.replace("{draft}", "我的草稿正文").replace(
            "{doc_type}", "请示"
        )
        assert "我的草稿正文" in prompt
        assert "请示" in prompt
        # JSON 示例的花括号应原样保留（供 LLM 参考输出格式）
        assert '"issues"' in prompt
        assert "{draft}" not in prompt
        assert "{doc_type}" not in prompt

    def test_str_format_would_have_crashed(self):
        """记录性测试：证明旧的 .format() 写法确实会崩溃。"""
        with pytest.raises((KeyError, ValueError, IndexError)):
            CHECK_FORMAT_PROMPT.format(draft="x", doc_type="请示")


class TestCheckFormat:
    """check_format 工具主逻辑。"""

    def test_parses_clean_json(self):
        """LLM 返回裸 JSON 时正确解析。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(
            content='{"issues": [], "critical_count": 0, "summary": "全部通过"}'
        )
        result = check_format("草稿", "请示", llm)
        assert result["critical_count"] == 0
        assert result["summary"] == "全部通过"

    def test_parses_json_in_markdown_fence(self):
        """LLM 用 ```json 代码块包裹时也能解析。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(
            content='```json\n{"issues": [{"item": "结尾用语", "status": "issue", "detail": "应为妥否请批示"}], "critical_count": 1, "summary": "1 个问题"}\n```'
        )
        result = check_format("草稿", "请示", llm)
        assert result["critical_count"] == 1
        assert result["issues"][0]["item"] == "结尾用语"

    def test_llm_error_graceful_degradation(self):
        """LLM 调用抛异常时优雅降级（回归 NameError bug）。"""
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("网络超时")
        result = check_format("草稿", "请示", llm)
        # 应返回降级结果而非抛 NameError
        assert result["critical_count"] == 1
        assert "人工审核" in result["summary"]

    def test_malformed_json_graceful(self):
        """LLM 返回非法 JSON 时优雅降级。"""
        llm = MagicMock()
        llm.invoke.return_value = AIMessage(content="这不是 JSON，只是一段普通文字")
        result = check_format("草稿", "请示", llm)
        assert result["critical_count"] == 1
        assert result["issues"][0]["status"] == "issue"
