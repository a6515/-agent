"""
第一阶段 — RAG 知识库构建模块
===============================
提供 Word 公文加载、语义分块、向量化存储的完整流水线。

公共接口：
    from src.domain.ingestion import (
        load_gongwen_documents,     # 加载 .docx
        split_gongwen_documents,    # 语义分块
        build_vector_store,         # 向量化入库
    )
"""

from src.domain.ingestion.doc_loader import load_gongwen_documents
from src.domain.ingestion.text_splitter import split_gongwen_documents
from src.domain.ingestion.embed_store import build_vector_store

__all__ = [
    "load_gongwen_documents",
    "split_gongwen_documents",
    "build_vector_store",
]
