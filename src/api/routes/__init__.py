"""
Controller 层 —— HTTP 路由（≈ Spring @RestController）
=====================================================
每个路由文件只负责 HTTP 编解码 + 调用对应 service，不含业务逻辑。

  - system.py    /health /stats /download
  - generate.py  /generate /generate/stream
  - agent.py     /generate/agent/stream /generate/agent/answer
  - oa.py        /oa/forward
"""
