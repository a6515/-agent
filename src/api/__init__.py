"""
第三阶段 — API 接口封装与致远 OA 对接
=======================================
提供 FastAPI 服务：
  - /generate       生成公文正文（同步）
  - /generate/stream  生成公文正文（流式 SSE）
  - /oa/forward     推送公文到致远 OA 表单
  - /health         服务健康检查
"""

from src.api.server import app

__all__ = ["app"]
