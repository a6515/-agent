"""
============================================================
公文生成服务（Service 层 · 深度模式 Agent）
============================================================
编排 LangGraph 深度模式：把图的自定义事件流转成 SSE 文本帧，并在 done
事件时落盘 .docx；同时提供 ask_user 的回答注入。

与重构前 server._agent_stream_langgraph 行为一致。
"""

import json
import uuid
from typing import AsyncIterator

from src.api.schemas import GenerateRequest
from src.repositories.document_repository import DocumentRepository
from src.infra.helpers import extract_title_from_content
from src.infra.logger import get_logger

logger = get_logger(__name__)


class AgentService:
    """深度模式（LangGraph Agent）生成编排。"""

    def __init__(self, docs: DocumentRepository):
        self._docs = docs

    async def stream_events(self, req: GenerateRequest) -> AsyncIterator[str]:
        """运行深度模式 Agent，逐帧产出 7 类 SSE 事件文本。"""
        from src.domain.graph.sse_adapter import run_graph_agent_stream

        session_id = uuid.uuid4().hex[:12]
        doc_type = req.doc_type.value if req.doc_type else None
        history = req.messages if getattr(req, "messages", None) else None
        current_draft = req.current_draft if getattr(req, "current_draft", None) else None

        try:
            async for ev in run_graph_agent_stream(
                req.prompt, doc_type=doc_type, history=history,
                current_draft=current_draft, session_id=session_id,
            ):
                ev_type = ev.get("event", "message")
                ev_data = ev.get("data", {})
                # 拦截 done 事件落盘 docx（与重构前一致）
                if ev_type == "done" and isinstance(ev_data, dict):
                    final_draft = ev_data.get("final_draft", "")
                    if final_draft:
                        title = ev_data.get("title") or extract_title_from_content(final_draft)
                        try:
                            docx_path = self._docs.save(final_draft, title)
                            ev_data["docx_path"] = docx_path
                            ev_data["title"] = title
                            logger.info(f"Agent(LangGraph) 已保存 .docx：{docx_path}")
                        except Exception as e:
                            logger.warning(f"Agent(LangGraph) docx 保存失败：{e}")
                yield f"event: {ev_type}\ndata: {json.dumps(ev_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"LangGraph Agent 流异常：{e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    def submit_answer(self, session_id: str, answer: str) -> bool:
        """向等待中的 Agent 注入 ask_user 回答，成功返回 True。"""
        from src.domain.graph.sse_adapter import submit_answer
        return submit_answer(session_id, answer)
