"""
============================================================
SSE 适配器 —— graph.astream → 7 类 SSE 事件（含 ask_user 中断恢复）
============================================================
把 LangGraph 的自定义流转成 API 层需要的 {"event", "data"} 事件流。相比
旧实现的 ThreadPoolExecutor + Queue 桥接，这里是原生 async。

ask_user 中断恢复：遇到 interrupt 时 emit ask_user 事件，并在**同一个 SSE
连接**上用 asyncio.Future 异步等待答案（不占线程、不忙等）；答案由
/generate/agent/answer 端点通过 submit_answer 投递，拿到后 Command(resume)
续跑。前端行为与 legacy 完全一致（同一流先收 ask_user 再继续收 done）。
"""

import asyncio
from typing import AsyncIterator, Dict, Any, List, Optional

from langgraph.types import Command

from src.agent.graph.build import get_agent_graph
from src.utils.logger import get_logger

logger = get_logger(__name__)

# session_id → asyncio.Future：把 ask_user 答案投递给等待中的 SSE 流
_ANSWER_FUTURES: Dict[str, asyncio.Future] = {}


def submit_answer(session_id: str, answer: str) -> bool:
    """
    投递用户对 ask_user 的回答（由 answer 端点调用）。

    纯 asyncio（同一事件循环内跨请求通信），不占线程、不忙等 ——
    这正是相对 legacy 的 threading.Event 轮询的改进点。
    """
    fut = _ANSWER_FUTURES.get(session_id)
    if fut is not None and not fut.done():
        fut.set_result(answer)
        return True
    return False


async def _wait_for_answer(session_id: str, timeout: float = 1800.0) -> Optional[str]:
    """异步等待用户回答（不占线程）。超时返回 None。"""
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    _ANSWER_FUTURES[session_id] = fut
    try:
        return await asyncio.wait_for(fut, timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        _ANSWER_FUTURES.pop(session_id, None)


def _extract_interrupts(snapshot) -> List[str]:
    """从图状态快照提取 pending interrupt 的问题文本（兼容不同 langgraph 版本）。"""
    values: List[str] = []
    intrs = getattr(snapshot, "interrupts", None)
    if intrs:
        for i in intrs:
            values.append(getattr(i, "value", str(i)))
    else:
        for task in getattr(snapshot, "tasks", None) or []:
            for i in getattr(task, "interrupts", None) or []:
                values.append(getattr(i, "value", str(i)))
    return values


async def run_graph_agent_stream(
    user_query: str,
    doc_type: Optional[str] = None,
    history: Optional[List[Dict[str, str]]] = None,
    current_draft: Optional[str] = None,
    session_id: Optional[str] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """
    运行 LangGraph 深度模式 Agent，逐个 yield SSE 事件 dict。

    Yields:
        {"event": "status|tool_start|tool_end|draft|done|ask_user|error",
         "data": {...}}  —— data 已是 dict（非 JSON 字符串）
    """
    graph = await get_agent_graph()
    sid = session_id or "default"
    config = {"configurable": {"thread_id": sid}, "recursion_limit": 60}

    graph_input: Any = {
        "user_query": user_query,
        "doc_type": doc_type or "",
        "history": history or [],
        "current_draft": current_draft or "",
        "session_id": sid,
    }

    try:
        while True:
            async for chunk in graph.astream(graph_input, config, stream_mode="custom"):
                if isinstance(chunk, dict) and "event" in chunk:
                    yield chunk

            # astream 结束：检查是否因 interrupt（ask_user）暂停
            snapshot = await graph.aget_state(config)
            questions = _extract_interrupts(snapshot)
            if not questions:
                break  # 图正常完成（done 已由 finalize 节点发出）

            # 暂停：emit ask_user，异步等待答案
            yield {"event": "ask_user", "data": {"question": questions[0], "session_id": sid}}
            answer = await _wait_for_answer(sid)
            if answer is None:
                yield {"event": "error", "data": {"message": "等待用户回答超时，已结束本次生成。"}}
                break

            yield {"event": "status", "data": {"message": "已收到用户回复，继续处理...", "icon": "💬"}}
            graph_input = Command(resume=answer)   # 从中断点恢复

    except Exception as e:
        logger.error(f"LangGraph Agent 流异常：{e}")
        yield {"event": "error", "data": {"message": f"Agent 运行出错：{str(e)}"}}
