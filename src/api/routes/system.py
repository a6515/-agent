"""
系统端点：健康检查、运行统计、文件下载（Controller 层）。
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from config.settings import settings
from src.api.deps import (
    get_rag_chain,
    get_oa_client,
    get_document_repository,
    get_stats_service,
)
from src.api.schemas import HealthResponse
from src.repositories.document_repository import DocumentRepository
from src.services.stats_service import StatsService
from src.infra.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health_check(check_llm: bool = False):
    """
    服务健康检查。

    参数：
      - check_llm: 设为 true 时额外验证 LLM API Key 是否可用（消耗少量 token）。
    """
    # 直接调用 provider（非 Depends），以便用 try/except 吞掉"知识库未构建"错误，
    # 保证健康检查在向量库缺失时仍返回 200（vector_db_ready=False）。
    try:
        chain = get_rag_chain()
        vector_db_ok = chain.retriever.is_ready
    except Exception:
        vector_db_ok = False

    llm_ok = None
    if check_llm:
        try:
            from langchain_openai import ChatOpenAI
            probe_llm = ChatOpenAI(
                model=settings.LLM_MODEL_NAME,
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
                temperature=0,
                max_tokens=1,
            )
            probe_llm.invoke("ping")
            llm_ok = True
        except Exception as e:
            logger.warning(f"LLM 探活失败：{e}")
            llm_ok = False

    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_model=settings.LLM_MODEL_NAME,
        vector_db_ready=vector_db_ok,
        oa_configured=get_oa_client().is_configured,
        llm_ok=llm_ok,
    )


@router.get("/stats")
async def get_stats(svc: StatsService = Depends(get_stats_service)):
    """获取服务运行统计（LLM 调用次数、token 用量等）。"""
    return svc.snapshot()


@router.get("/download/{filename}")
async def download_docx(
    filename: str,
    docs: DocumentRepository = Depends(get_document_repository),
):
    """下载生成的 .docx 公文文件。"""
    try:
        file_path = docs.safe_path(filename)
    except PermissionError:
        raise HTTPException(status_code=403, detail="禁止的路径")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件不存在：{filename}")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
