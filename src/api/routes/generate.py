"""
快速模式端点：/generate（同步）、/generate/stream（SSE 流式）。Controller 层。
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from src.api.deps import get_generation_service
from src.api.schemas import GenerateRequest, GenerateResponse
from src.services.generation_service import GenerationService

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerateResponse)
async def generate_document(
    req: GenerateRequest,
    svc: GenerationService = Depends(get_generation_service),
):
    """同步生成公文正文（检索 → 一次生成 → 返回完整结果）。"""
    return await svc.generate(req)


@router.post("/generate/stream")
async def generate_stream(
    req: GenerateRequest,
    svc: GenerationService = Depends(get_generation_service),
):
    """流式生成公文正文（Server-Sent Events，实时打字效果）。"""
    try:
        # 提前触发链构建：知识库缺失时在此返回 500，而非流式中途报错
        svc.ensure_ready()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return StreamingResponse(
        svc.stream_events(req),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
