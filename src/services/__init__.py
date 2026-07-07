"""
Service 层 —— 业务编排（≈ Spring 的 @Service）
==============================================
Controller 只调用本层，不直接碰领域链路 / 仓储细节。每个 service 负责
一条完整的业务流程，把"识别文种 → 检索 → 生成 → 落盘"这类编排从
HTTP 端点里抽离出来。

  - generation_service.py  快速模式（RAG 单轮）生成编排
  - agent_service.py       深度模式（LangGraph Agent）生成编排
  - oa_service.py          致远 OA 推送编排 + 异常映射
  - stats_service.py       token 用量统计
"""
