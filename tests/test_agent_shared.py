"""
============================================================
测试：Agent 共享工具（agent_shared.py）
============================================================
覆盖新旧引擎公用的纯函数：tool_call 解析、结果摘要、修改关键词、
tool_end 事件构造。
"""

import json
import pytest
from unittest.mock import MagicMock

from src.agent.agent_shared import (
    _extract_tool_calls,
    _tool_result_to_text,
    _RE_MODIFY_KEYWORDS,
    build_tool_end,
)


class TestExtractToolCalls:
    """工具调用提取（兼容 LangChain 和原生 OpenAI 格式）。"""

    def test_langchain_format(self):
        """LangChain AIMessage.tool_calls 格式。"""
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"name": "search_exemplars", "args": {"query": "服务器采购"}, "id": "call_001"}
        ]
        result = _extract_tool_calls(mock_response)
        assert len(result) == 1
        assert result[0]["name"] == "search_exemplars"
        assert result[0]["args"] == {"query": "服务器采购"}
        assert result[0]["id"] == "call_001"

    def test_openai_native_format(self):
        """additional_kwargs 中原生 OpenAI 格式（JSON 字符串 args）。"""
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.additional_kwargs = {
            "tool_calls": [
                {
                    "id": "call_002",
                    "type": "function",
                    "function": {
                        "name": "check_format",
                        "arguments": '{"draft": "test", "doc_type": "请示"}',
                    },
                }
            ]
        }
        result = _extract_tool_calls(mock_response)
        assert len(result) == 1
        assert result[0]["name"] == "check_format"
        assert result[0]["args"] == {"draft": "test", "doc_type": "请示"}

    def test_multiple_tools(self):
        """多工具同时调用。"""
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"name": "search_exemplars", "args": {"query": "test"}, "id": "c1"},
            {"name": "check_format", "args": {"draft": "...", "doc_type": "通知"}, "id": "c2"},
        ]
        result = _extract_tool_calls(mock_response)
        assert len(result) == 2

    def test_empty_tools(self):
        """无工具调用。"""
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.additional_kwargs = {}
        result = _extract_tool_calls(mock_response)
        assert result == []

    def test_additional_kwargs_tool_calls_none(self):
        """DeepSeek 在无工具调用时 additional_kwargs.tool_calls 为 None（回归测试）。"""
        mock_response = MagicMock()
        mock_response.tool_calls = []
        mock_response.additional_kwargs = {"tool_calls": None}
        result = _extract_tool_calls(mock_response)
        assert result == []

    def test_invalid_json_args(self):
        """args JSON 解析失败时降级为空 dict。"""
        mock_response = MagicMock()
        mock_response.tool_calls = [
            {"name": "bad_tool", "args": "not valid json{{{", "id": "c3"}
        ]
        result = _extract_tool_calls(mock_response)
        assert len(result) == 1
        assert result[0]["args"] == {}


class TestToolResultToText:
    """工具结果截断/摘要化。"""

    def test_search_exemplars_truncation(self):
        long_result = json.dumps({"total_found": 4, "exemplars": [{"source": "x"}] * 100})
        result = _tool_result_to_text("search_exemplars", long_result)
        assert len(result) <= 4000

    def test_check_format_slim(self):
        check_result = json.dumps({
            "issues": [
                {"item": "标题", "status": "pass", "detail": ""},
                {"item": "结尾用语", "status": "issue", "detail": "应为请示结尾"},
            ],
            "critical_count": 1,
            "summary": "1 个问题",
        })
        result = _tool_result_to_text("check_format", check_result)
        data = json.loads(result)
        # 精简后应只包含有问题的条目
        assert data["critical_count"] == 1
        assert len(data["issues"]) == 1

    def test_refine_draft_truncation(self):
        long_draft = "x" * 5000
        result = _tool_result_to_text("refine_draft", long_draft)
        assert len(result) <= 3000


class TestBuildToolEnd:
    """tool_end 事件 data 构造。"""

    def test_search_exemplars(self):
        raw = json.dumps({"total_found": 3, "exemplars": [{"source": "a"}]})
        data = build_tool_end("search_exemplars", raw)
        assert data["tool"] == "search_exemplars"
        assert data["result"]["total_found"] == 3
        assert len(data["result"]["exemplars"]) == 1

    def test_check_format(self):
        raw = json.dumps({"issues": [{"item": "标题", "status": "issue"}],
                          "critical_count": 1, "summary": "1 个问题"})
        data = build_tool_end("check_format", raw)
        assert data["result"]["critical_count"] == 1
        assert data["result"]["summary"] == "1 个问题"

    def test_refine_draft(self):
        data = build_tool_end("refine_draft", "x" * 120)
        assert data["result"]["char_count"] == 120

    def test_malformed_json_degrades(self):
        """解析失败时返回安全默认值，不抛异常。"""
        data = build_tool_end("search_exemplars", "not json{{{")
        assert data["result"]["total_found"] == 0
        assert data["result"]["exemplars"] == []

    def test_unknown_tool(self):
        data = build_tool_end("finish", "{}")
        assert data["tool"] == "finish"


class TestModifyKeywords:
    """修改模式关键词匹配。"""

    @pytest.mark.parametrize("query,expected", [
        ("把时间改成8月1日", True),
        ("将地点改为301会议室", True),
        ("修改一下金额", True),
        ("换成采购部的名字", True),
        ("调整一下日期", True),
        ("更新部门信息", True),
        ("替换附件", True),
        ("变更申请金额", True),
        ("修正结尾用语", True),
        ("改一下", True),
        ("换一下标题", True),
        # 不应匹配的
        ("写一份申请购买3台服务器的请示", False),
        ("生成一份会议通知", False),
        ("帮我写一份报告", False),
    ])
    def test_modify_detection(self, query, expected):
        is_modify = any(pat.search(query) for pat in _RE_MODIFY_KEYWORDS)
        assert is_modify == expected

    def test_no_false_positive_on_rewrite(self):
        """'重写''重新写'不应被误判为局部修改。"""
        # '重写'包含'写'但不包含'改'，所以不应匹配修改关键词
        is_modify = any(pat.search("重新写一份") for pat in _RE_MODIFY_KEYWORDS)
        assert is_modify is False  # 没有'改'字，不应误判
