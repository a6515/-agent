"""
============================================================
pytest 共享 fixtures 和配置
============================================================
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

import pytest
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def _no_llm_calls(monkeypatch):
    """
    安全网：防止测试中意外调用真实的 LLM API。

    全局 mock ChatOpenAI.invoke，任何未在具体测试中覆盖的
    LLM 调用将返回空 AIMessage，避免消耗 API 额度。
    """
    try:
        from langchain_core.messages import AIMessage
        from langchain_openai import ChatOpenAI

        def _mock_invoke(self, *args, **kwargs):
            return AIMessage(content="[MOCK LLM RESPONSE]")

        monkeypatch.setattr(ChatOpenAI, "invoke", _mock_invoke)
    except ImportError:
        # langchain_openai 未安装时跳过
        pass
