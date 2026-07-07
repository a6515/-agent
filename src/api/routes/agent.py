"""
深度模式端点：/generate/agent/stream、/generate/agent/answer。Controller 层。

深度模式统一走 LangGraph StateGraph 引擎（interrupt 中断 + SQLite 持久化）。
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.deps import get_agent_service
from src.api.schemas import GenerateRequest, AgentAnswerRequest
from src.services.agent_service import AgentService
from src.infra.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["agent"])


@router.post("/generate/agent/stream")
async def generate_agent_stream(
    req: GenerateRequest,
    svc: AgentService = Depends(get_agent_service),
):
    """
    【深度模式】多轮推理 + 自查 + 自修（SSE 流式）。

    SSE 事件：status / tool_start / tool_end / draft / done / ask_user / error。
    """
    return StreamingResponse(
        svc.stream_events(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/generate/agent/answer")
async def agent_answer(
    req: AgentAnswerRequest,
    svc: AgentService = Depends(get_agent_service),
):
    """向等待中的 Agent 注入用户回答（ask_user 恢复流程）。"""
    if not svc.submit_answer(req.session_id, req.answer):
        raise HTTPException(
            status_code=404,
            detail=f"会话 {req.session_id} 不存在或已过期。"
                   f"可能是 Agent 已结束运行或超时。",
        )
    logger.info(f"Agent 会话 {req.session_id} 收到用户回答：{req.answer[:80]}...")
    return {"success": True, "message": "回答已提交，Agent 继续执行中"}
