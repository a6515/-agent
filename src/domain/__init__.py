"""
第二阶段 — Agent 核心逻辑模块
===============================
提供 RAG 检索增强生成的完整链：
  - System Prompt 模板（资深公文秘书角色）
  - 向量库检索器
  - LCEL RAG 链（检索 + 格式化 + 生成）

公共接口：
    from src.domain import (
        build_rag_chain,    # 构建 RAG 链
        get_retriever,      # 获取检索器
        GONGWEN_PROMPT,     # System Prompt 模板
    )
"""

from src.domain.rag_chain import build_rag_chain, get_retriever
from src.domain.prompts import SYSTEM_PROMPT

__all__ = [
    "build_rag_chain",
    "get_retriever",
    "SYSTEM_PROMPT",
]
