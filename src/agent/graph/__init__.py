"""
============================================================
LangGraph 版深度模式 Agent（编排层）
============================================================
用 StateGraph + checkpointer 替代手写 while 循环，解决三个硬伤：
  - ask_user 忙等阻塞线程   → interrupt() 暂停不占线程
  - 进程重启丢失会话        → checkpointer 持久化
  - ThreadPool+Queue 桥接   → 原生 async astream

深度模式（/generate/agent/stream）的唯一实现。对外保持 7 类 SSE 事件契约
（status/tool_start/tool_end/draft/done/ask_user/error），前端零改动。

详见 docs/LangGraph升级方案.md。
"""
