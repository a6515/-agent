"""
============================================================
LangGraph 深度模式 Agent — 图节点与路由
============================================================
每个节点是 async 函数，用 get_stream_writer() 发出与旧实现相同的 7 类
SSE 事件（status/tool_start/tool_end/draft/done/ask_user/error），保证
前端零改动。工具执行、token 统计、结果摘要等纯逻辑复用现有模块。

节点图：
    prepare → agent → [tools | accept_or_remind | finalize]
    tools   → [agent | finalize]
    accept_or_remind → agent
    finalize → END
"""

import asyncio
import json
from typing import Optional

from langchain_core.messages import (
    HumanMessage, AIMessage, ToolMessage, SystemMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from config.settings import settings
from src.agent.agent_prompt import AGENT_SYSTEM_PROMPT
from src.agent.tools import execute_tool, AGENT_TOOLS
from src.agent.rag_chain import detect_doc_type
from src.agent.agent_shared import (
    _extract_tool_calls,
    _tool_result_to_text,
    _extract_token_usage,
    _token_tracker,
    _RE_MODIFY_KEYWORDS,
    build_tool_end,
)
from src.utils.helpers import build_date_context
from src.utils.logger import get_logger
from src.agent.graph.state import GongwenGraphState

logger = get_logger(__name__)

MAX_TURNS = 10
MAX_FIX_ATTEMPTS = 2
MAX_ASK_ROUNDS = 3   # ask_user 补充提问的最多轮次（逐轮询问的上限）


# ============================================================
# LLM 单例（不 streaming：每轮需完整响应以判断 tool_call）
# ============================================================

_llm: Optional[ChatOpenAI] = None


def _get_llm() -> ChatOpenAI:
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model=settings.LLM_MODEL_NAME,
            base_url=settings.LLM_BASE_URL,
            api_key=settings.LLM_API_KEY,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=4096,
        )
    return _llm


def _emit_tool_status(writer, tool_name: str, raw_result: str):
    """工具完成后的状态消息（用 writer 发 SSE status 事件）。"""
    if tool_name == "search_exemplars":
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            n = data.get("total_found", 0)
            writer({"event": "status", "data": {
                "message": f"已检索到 {n} 篇范文，正在撰写初稿...", "icon": "📚"}})
        except Exception:
            pass
    elif tool_name == "check_format":
        try:
            data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            issues = [i for i in data.get("issues", []) if i.get("status") == "issue"]
            if issues:
                writer({"event": "status", "data": {
                    "message": f"格式审查发现 {len(issues)} 个问题，正在修复...", "icon": "🔧"}})
            else:
                writer({"event": "status", "data": {
                    "message": "格式审查通过，准备输出最终稿", "icon": "✅"}})
        except Exception:
            pass
    elif tool_name == "refine_draft":
        writer({"event": "status", "data": {
            "message": f"草稿已修复，共 {len(raw_result) if raw_result else 0} 字，正在再次审查...",
            "icon": "📝"}})


def _looks_like_clarification(text: str) -> bool:
    """
    判断 LLM 的纯文本输出是「提问 / 澄清 / 自我叙述」而非公文正文。

    用于 accept_or_remind_node：避免把 Agent 的提问或思考文字（如
    “检索到的范文主要是模板…我来向您确认…请问文种是？”）误当成草稿。
    命中公文结尾用语则判为正文；否则含问号或提问/自述特征即判为澄清。
    """
    t = (text or "").strip()
    if not t:
        return True
    # 公文结尾/正文特征——出现基本可判为正文，直接放行
    doc_markers = ["特此", "妥否", "请批示", "请审批", "此复", "请予", "函告", "以上报告", "报告如上"]
    if any(m in t for m in doc_markers):
        return False
    # 提问 / 澄清 / 自我叙述特征
    if "？" in t or "?" in t:
        return True
    q_markers = [
        "请问", "向您确认", "请提供", "请补充", "请确认", "麻烦您", "请告知",
        "需要您提供", "需要您补充", "检索到的范文", "没关系，我", "我来帮您", "让我先",
    ]
    return any(m in t for m in q_markers)


# ============================================================
# 节点
# ============================================================

async def prepare_node(state: GongwenGraphState) -> dict:
    """识别文种，构建初始对话消息（system + 历史 + 用户输入/草稿）。"""
    writer = get_stream_writer()
    user_query = state["user_query"]
    doc_type = state.get("doc_type") or detect_doc_type(user_query)

    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT + build_date_context())]

    # 注入对话历史
    for msg in state.get("history") or []:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    # 修改模式 vs 新建
    current_draft = state.get("current_draft")
    if current_draft and current_draft.strip():
        draft_msg = (
            "以下是之前生成的公文草稿：\n\n---\n"
            f"{current_draft.strip()}\n---\n\n"
            f"用户要求：{user_query}\n\n"
            "如果这是一个局部修改请求（如改时间、改地点、改名称、改数字等），"
            "请直接调用 refine_draft 修改指定内容。不要调用 search_exemplars 检索范文，"
            "不要重新撰写全文。只改用户指定的内容，其他部分原封不动。"
        )
        if any(pat.search(user_query) for pat in _RE_MODIFY_KEYWORDS):
            draft_msg += ("\n\n这看起来是一个局部修改请求。请严格遵循「修改流程」："
                          "禁止 search_exemplars → 直接 refine_draft → check_format → finish。")
        messages.append(HumanMessage(content=draft_msg))
    else:
        messages.append(HumanMessage(content=user_query))

    writer({"event": "status", "data": {
        "message": f"已识别公文类型：{doc_type}", "icon": "📋",
        "session_id": state.get("session_id", ""),
    }})
    writer({"event": "status", "data": {"message": "正在检索历史范文...", "icon": "🔍"}})

    return {
        "messages": messages,
        "doc_type": doc_type,
        "searched": False,
        "fix_attempts": {},
        "turn_count": 0,
        "draft": None,
        "finished": False,
        "ask_count": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
    }


async def agent_node(state: GongwenGraphState) -> dict:
    """调 LLM 推理一轮（带重试与 token 统计）。"""
    writer = get_stream_writer()
    turn = state.get("turn_count", 0) + 1

    if turn == 2:
        writer({"event": "status", "data": {
            "message": f"第 {turn} 轮：正在检索范文并撰写初稿...", "icon": "🔄"}})
    elif turn > 2:
        writer({"event": "status", "data": {
            "message": f"第 {turn} 轮：正在审查格式并修复问题...", "icon": "🔄"}})

    llm = _get_llm()
    max_retries = settings.LLM_MAX_RETRIES
    retry_delay = settings.LLM_RETRY_DELAY
    response = None
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            response = await llm.ainvoke(
                state["messages"], tools=AGENT_TOOLS, tool_choice="auto",
            )
            break
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * (2 ** attempt))
            else:
                logger.error(f"LLM 调用最终失败（第 {turn} 轮，已重试 {max_retries} 次）：{e}")

    if response is None:
        writer({"event": "error", "data": {
            "message": f"LLM 调用失败（已重试 {settings.LLM_MAX_RETRIES} 次）：{last_error}"}})
        # 标记 finished → 路由到 finalize（有草稿则输出，无则报错）
        return {"turn_count": turn, "finished": True}

    upd = {"messages": [response], "turn_count": turn}
    if settings.TOKEN_TRACKING_ENABLED:
        pt, ct = _extract_token_usage(response)
        if pt or ct:
            _token_tracker.record(pt, ct)
            upd["prompt_tokens"] = state.get("prompt_tokens", 0) + pt
            upd["completion_tokens"] = state.get("completion_tokens", 0) + ct
    return upd


async def tools_node(state: GongwenGraphState) -> dict:
    """执行 AIMessage 里的所有 tool_calls，更新状态并发出 SSE 事件。"""
    writer = get_stream_writer()
    llm = _get_llm()
    tool_calls = _extract_tool_calls(state["messages"][-1])

    new_messages = []
    updates: dict = {}
    fix_attempts = dict(state.get("fix_attempts", {}))

    for tc in tool_calls:
        name, args, tc_id = tc["name"], tc["args"], tc["id"]
        writer({"event": "tool_start", "data": {"tool": name, "args": args}})

        try:
            # execute_tool 内部含同步 LLM/检索调用 → 丢线程池避免阻塞事件循环
            raw_result = await asyncio.to_thread(execute_tool, name, args, llm)
        except Exception as e:
            logger.error(f"工具 {name} 执行失败：{e}")
            writer({"event": "tool_end", "data": {"tool": name, "result": {"error": str(e)[:200]}}})
            new_messages.append(ToolMessage(
                content=f"工具 {name} 执行失败：{str(e)[:300]}", tool_call_id=tc_id))
            continue

        # ---- 状态更新 ----
        if name == "search_exemplars":
            updates["searched"] = True
        elif name == "refine_draft":
            updates["draft"] = raw_result
            writer({"event": "draft", "data": {"content": raw_result, "doc_type": state["doc_type"]}})
        elif name == "check_format":
            try:
                data = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
                for issue in data.get("issues", []):
                    if issue.get("status") == "issue":
                        item = issue.get("item", "")
                        fix_attempts[item] = fix_attempts.get(item, 0) + 1
            except Exception:
                pass

        writer({"event": "tool_end", "data": build_tool_end(name, raw_result)})
        _emit_tool_status(writer, name, raw_result)

        # ---- 特殊标记：决定 ToolMessage 内容与状态更新 ----
        if raw_result.startswith("__FINISH__"):
            fd = json.loads(raw_result[len("__FINISH__"):])
            updates["draft"] = fd["final_draft"]
            updates["finished"] = True
            updates["summary"] = fd["summary"]
            tool_content = "已输出最终稿。"
        elif raw_result.startswith("__ASK_USER__"):
            question = raw_result[len("__ASK_USER__"):]
            asked = state.get("ask_count", 0) + 1
            updates["ask_count"] = asked
            if asked <= MAX_ASK_ROUNDS:
                # 逐轮询问：记录待澄清问题，由 route 路由到 ask_user 节点触发 interrupt
                updates["pending_question"] = question
                tool_content = f"已向用户提问（第 {asked}/{MAX_ASK_ROUNDS} 次），等待回答：{question}"
            else:
                # 达到补充提问上限：不再中断询问，强制基于现有信息推断并撰写
                tool_content = (
                    f"补充提问已达上限（{MAX_ASK_ROUNDS} 次），不能再调用 ask_user。"
                    "请立即基于现有信息合理推断剩余的次要要素，直接开始撰写公文，不要再提问。"
                )
        else:
            tool_content = _tool_result_to_text(name, raw_result)

        # ToolMessage 必须回应每个 tool_call
        new_messages.append(ToolMessage(content=tool_content, tool_call_id=tc_id))

    updates["messages"] = new_messages
    updates["fix_attempts"] = fix_attempts

    # 修复次数超限 → 提示标注人工审核后结束
    stuck = [item for item, cnt in fix_attempts.items() if cnt >= MAX_FIX_ATTEMPTS]
    if stuck and not updates.get("finished"):
        new_messages.append(HumanMessage(
            content=f"以下问题已修复 {MAX_FIX_ATTEMPTS} 次仍未通过，请标注「需人工审核」"
                    f"并直接调用 finish 输出：{', '.join(stuck)}"))

    return updates


async def accept_or_remind_node(state: GongwenGraphState) -> dict:
    """LLM 返回纯文本（无工具调用）时：接受为初稿 或 注入流程提醒。"""
    writer = get_stream_writer()
    last = state["messages"][-1]
    content = getattr(last, "content", "") or ""

    draft = state.get("draft")
    searched = state.get("searched", False)

    if draft is None and len(content) > 50:
        # 防串：LLM 把「提问 / 澄清 / 自述」当正文输出 → 不接受为草稿，纠偏
        if _looks_like_clarification(content):
            asked = state.get("ask_count", 0)
            if asked >= MAX_ASK_ROUNDS:
                remind = ("补充提问已达上限，请立即基于现有信息合理推断，直接撰写完整公文正文"
                          "（含标题、主送机关、正文、落款），不要再提问，也不要输出任何说明或思考文字。")
            else:
                remind = ("不要用普通文本向用户提问或自述。若还需补充信息，必须调用 ask_user 工具"
                          "（每次只问一个问题）；若信息已足够，请直接撰写完整公文正文"
                          "（含标题、主送机关、正文、落款），正文之外不要输出任何提问、说明或思考文字。")
            writer({"event": "status", "data": {"message": "正在梳理待补充的信息...", "icon": "💬"}})
            return {"messages": [HumanMessage(content=remind)]}
        if not searched:
            writer({"event": "status", "data": {
                "message": "需要先检索范文再撰写，正在强制要求...", "icon": "⚠️"}})
            return {"messages": [HumanMessage(content=
                "你还没有调用 search_exemplars 检索范文！请立即调用 search_exemplars 工具，"
                "必须传入 query 参数。检索完成后再撰写公文。不要直接输出文本。")]}
        # 接受初稿
        writer({"event": "status", "data": {"message": f"初稿已生成，共 {len(content)} 字", "icon": "✍️"}})
        writer({"event": "draft", "data": {"content": content, "doc_type": state["doc_type"]}})
        return {"draft": content}

    # 已有草稿却没调工具 → 提醒继续流程
    return {"messages": [HumanMessage(content=
        f"请按照工作流程继续：调用 check_format 审查当前草稿"
        f"（draft={(draft or '')[:100]}... doc_type={state['doc_type']}），或调用 finish 输出。")]}


async def finalize_node(state: GongwenGraphState) -> dict:
    """收尾：发出 done（含 token 统计）或 error。docx 落盘由 server 层拦截 done 事件完成。"""
    writer = get_stream_writer()
    draft = state.get("draft")

    if draft:
        summary = state.get("summary") or f"完成（共 {state.get('turn_count', 0)} 轮）"
        writer({"event": "draft", "data": {"content": draft, "doc_type": state["doc_type"]}})
        done_data = {
            "success": True,
            "final_draft": draft,
            "doc_type": state["doc_type"],
            "summary": summary,
            "agent_turns": state.get("turn_count", 0),
        }
        if settings.TOKEN_TRACKING_ENABLED:
            pt = state.get("prompt_tokens", 0)
            ct = state.get("completion_tokens", 0)
            done_data["token_usage"] = {
                "prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
            }
        writer({"event": "done", "data": done_data})
    else:
        writer({"event": "error", "data": {"message": "Agent 未能生成草稿"}})

    return {"finished": True}


async def ask_user_node(state: GongwenGraphState) -> dict:
    """
    向用户提问并暂停图（interrupt）。

    第一次执行到 interrupt() → 图落盘 checkpoint 并挂起（不占用任何线程）；
    用户回答后由 Command(resume=answer) 恢复，interrupt() 返回答案，
    注入为 HumanMessage 继续。interrupt 前无副作用，重放安全。
    """
    question = state.get("pending_question") or "请补充必要信息。"
    answer = interrupt(question)   # ← 暂停点；恢复后返回用户回答
    return {
        "messages": [HumanMessage(content=answer)],
        "pending_question": None,
    }


# ============================================================
# 路由（条件边）
# ============================================================

def route_after_agent(state: GongwenGraphState) -> str:
    """agent 之后：结束 / 执行工具 / 处理纯文本。"""
    if state.get("finished") or state.get("turn_count", 0) >= MAX_TURNS:
        return "finalize"
    if _extract_tool_calls(state["messages"][-1]):
        return "tools"
    return "accept_or_remind"


def route_after_tools(state: GongwenGraphState) -> str:
    """tools 之后：finish/达上限→收尾；有待澄清问题→ask_user；否则回 agent。"""
    if state.get("finished") or state.get("turn_count", 0) >= MAX_TURNS:
        return "finalize"
    if state.get("pending_question"):
        return "ask_user"
    return "agent"
