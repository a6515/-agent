"""
============================================================
StateGraph 装配 + 持久化 checkpointer
============================================================
节点图：
    START → prepare → agent → ┬─ tools ──────────────┐
                              ├─ accept_or_remind ────┤→ (回) agent
                              └─ finalize → END       │
    tools → ┬─ agent                                  │
            ├─ ask_user (interrupt) → agent           │
            └─ finalize → END ────────────────────────┘

checkpointer：AsyncSqliteSaver（落盘 data/agent_checkpoints.sqlite），
图状态跨进程重启可恢复；ask_user 暂停期间即使重启后端，也能凭 thread_id
从 checkpoint 续跑。
"""

import asyncio

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config.settings import settings
from src.agent.graph.state import GongwenGraphState
from src.agent.graph.nodes import (
    prepare_node,
    agent_node,
    tools_node,
    accept_or_remind_node,
    ask_user_node,
    finalize_node,
    route_after_agent,
    route_after_tools,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

# checkpoint 持久化路径
_CKPT_PATH = settings.DATA_DIR / "agent_checkpoints.sqlite"

_compiled = None
_conn = None
_lock = asyncio.Lock()


def _assemble(checkpointer) -> "CompiledStateGraph":
    """装配并编译图（checkpointer 由调用方注入）。"""
    g = StateGraph(GongwenGraphState)

    g.add_node("prepare", prepare_node)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("accept_or_remind", accept_or_remind_node)
    g.add_node("ask_user", ask_user_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "prepare")
    g.add_edge("prepare", "agent")
    g.add_conditional_edges("agent", route_after_agent, {
        "tools": "tools",
        "accept_or_remind": "accept_or_remind",
        "finalize": "finalize",
    })
    g.add_conditional_edges("tools", route_after_tools, {
        "agent": "agent",
        "ask_user": "ask_user",
        "finalize": "finalize",
    })
    g.add_edge("accept_or_remind", "agent")
    g.add_edge("ask_user", "agent")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


async def get_agent_graph():
    """获取编译后的图（进程内单例，异步初始化 SQLite checkpointer）。"""
    global _compiled, _conn
    if _compiled is not None:
        return _compiled
    async with _lock:
        if _compiled is None:
            import aiosqlite
            _CKPT_PATH.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"正在编译 LangGraph 深度模式 Agent 图（checkpoint: {_CKPT_PATH.name}）...")
            _conn = await aiosqlite.connect(str(_CKPT_PATH))
            saver = AsyncSqliteSaver(_conn)
            await saver.setup()   # 建表（幂等）
            _compiled = _assemble(saver)
    return _compiled
