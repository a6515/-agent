"""
============================================================
GongwenGraphState — LangGraph 深度模式 Agent 状态
============================================================
对应旧实现的 AgentState（dataclass），改写为 LangGraph 的 TypedDict。
messages 用 add_messages reducer 自动累加，不再手动 append。
"""

from typing import Annotated, Optional, List, Dict, TypedDict

from langgraph.graph.message import add_messages


class GongwenGraphState(TypedDict, total=False):
    """深度模式 Agent 的图状态（total=False：字段均可选，便于分节点增量更新）。"""

    # ---- 对话消息：add_messages reducer 自动累加 ----
    messages: Annotated[list, add_messages]

    # ---- 输入 ----
    user_query: str                      # 用户原始请求
    history: List[Dict[str, str]]        # 前端传来的对话历史
    current_draft: Optional[str]         # 修改模式：已有草稿
    session_id: str                      # 会话 ID（ask_user 恢复用）

    # ---- 运行状态 ----
    doc_type: str                        # 识别/指定的文种
    draft: Optional[str]                 # 当前草稿
    searched: bool                       # 是否已检索范文
    fix_attempts: Dict[str, int]         # 各条目修复次数
    turn_count: int                      # LLM 推理轮次
    finished: bool                       # 是否已结束
    summary: str                         # finish 的修改说明
    pending_question: Optional[str]      # 待用户澄清的问题（非空 → 路由到 ask_user 节点触发 interrupt）
    ask_count: int                       # 已发起的补充提问次数（用于「最多 3 轮」限制）

    # ---- token 统计 ----
    prompt_tokens: int
    completion_tokens: int
