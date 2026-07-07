"""
============================================================
公文生成服务（Service 层 · 快速模式）
============================================================
编排"识别文种 → 检索 + 生成（RAG 单轮）→ 提取标题 → 落盘"的业务流程。
Controller 只调用本服务，不关心链路细节。

依赖以「provider 惰性获取」方式注入 RAG 链：链的构建会读取向量库，
若知识库未构建会抛 FileNotFoundError——放到方法内触发，才能复现
重构前 /generate 返回 503、/generate/stream 返回 500 的既有行为。
"""

import json
from typing import AsyncIterator, Callable

from fastapi import HTTPException

from src.domain.rag_chain import GongwenRAGChain, detect_doc_type
from src.api.schemas import GenerateRequest, GenerateResponse
from src.repositories.document_repository import DocumentRepository
from src.infra.helpers import extract_title_from_content
from src.infra.logger import get_logger

logger = get_logger(__name__)


class GenerationService:
    """快速模式（RAG 单轮）公文生成编排。"""

    def __init__(
        self,
        chain_provider: Callable[[], GongwenRAGChain],
        docs: DocumentRepository,
    ):
        self._chain_provider = chain_provider   # 惰性获取，异常在方法内捕获
        self._docs = docs

    def ensure_ready(self) -> None:
        """触发 RAG 链构建（知识库缺失时在此抛异常，而非流式中途）。"""
        self._chain_provider()

    async def generate(self, req: GenerateRequest) -> GenerateResponse:
        """同步生成，返回完整响应体。"""
        try:
            chain = self._chain_provider()
            doc_type = req.doc_type.value if req.doc_type else detect_doc_type(req.prompt)
            logger.info(f"API 请求：prompt='{req.prompt[:50]}...' → {doc_type}")

            content = await chain.ainvoke(req.prompt, doc_type=doc_type)
            title = extract_title_from_content(content)

            try:
                docx_path = self._docs.save(content, title)
                logger.info(f"已保存 .docx：{docx_path}")
            except Exception as e:
                logger.warning(f".docx 保存失败（不影响生成结果）：{e}")
                docx_path = None

            logger.info(f"生成成功：{len(content)} 字符，标题={title}")
            return GenerateResponse(
                success=True,
                title=title,
                content=content,
                doc_type=doc_type,
                char_count=len(content),
                docx_path=docx_path,
            )

        except FileNotFoundError as e:
            logger.error(f"向量库未找到：{e}")
            raise HTTPException(
                status_code=503,
                detail="知识库未构建，请先运行 build_knowledge_base.py",
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"生成失败：{e}")
            return GenerateResponse(
                success=False, title="", content="", doc_type="", char_count=0, error=str(e),
            )

    async def stream_events(self, req: GenerateRequest) -> AsyncIterator[str]:
        """流式生成，逐帧产出 SSE 文本（event: token / done / error）。"""
        chain = self._chain_provider()
        doc_type = req.doc_type.value if req.doc_type else detect_doc_type(req.prompt)
        logger.info(f"API 流式请求：prompt='{req.prompt[:50]}...' → {doc_type}")

        doc_type_sent = False
        full_content_parts = []
        try:
            async for chunk in chain.astream(req.prompt, doc_type=doc_type):
                full_content_parts.append(chunk)
                event_data = {"token": chunk}
                if not doc_type_sent:
                    event_data["doc_type"] = doc_type
                    doc_type_sent = True
                yield f"event: token\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            full_content = "".join(full_content_parts)
            title = extract_title_from_content(full_content)
            docx_path = None
            try:
                docx_path = self._docs.save(full_content, title)
                logger.info(f"docx saved: {docx_path}")
            except Exception as e:
                logger.warning(f"docx save failed: {e}")

            done_data = {
                "doc_type": doc_type,
                "docx_path": docx_path,
                "title": title,
                "char_count": len(full_content),
            }
            yield f"event: done\ndata: {json.dumps(done_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
