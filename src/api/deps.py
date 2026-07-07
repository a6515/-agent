"""
============================================================
依赖装配（DI 容器 · ≈ Spring @Configuration + ApplicationContext）
============================================================
整个应用的「对象怎么 new、谁依赖谁」集中在这一个文件里，用 lru_cache
提供单例。Controller 通过 Depends(get_xxx_service) 拿到装配好的服务，
不再散落全局变量——想看依赖关系，读这一个文件即可。

  get_generation_service ─┬─ get_rag_chain（provider，惰性）
                          └─ get_document_repository
  get_agent_service ──────── get_document_repository
  get_oa_service ─────────── get_oa_client
  get_stats_service
"""

from functools import lru_cache

from config.settings import settings
from src.domain.rag_chain import GongwenRAGChain, build_rag_chain
from src.repositories.document_repository import DocumentRepository
from src.repositories.oa_client import SeeyonOAClient, oa_client
from src.services.generation_service import GenerationService
from src.services.agent_service import AgentService
from src.services.oa_service import OAService
from src.services.stats_service import StatsService


# ============================================================
# 基础组件（Repository / 领域链路）
# ============================================================

@lru_cache
def get_document_repository() -> DocumentRepository:
    return DocumentRepository(settings.DATA_DIR / "output")


@lru_cache
def get_rag_chain() -> GongwenRAGChain:
    """RAG 链单例（懒构建；知识库缺失时首次调用抛 FileNotFoundError）。"""
    return build_rag_chain(k=settings.RETRIEVER_K)


@lru_cache
def get_oa_client() -> SeeyonOAClient:
    return oa_client


# ============================================================
# Service（业务编排）
# ============================================================

@lru_cache
def get_generation_service() -> GenerationService:
    # 传 provider 函数而非链实例：让"知识库缺失"的异常在 service 方法内触发，
    # 从而复现重构前的 503 / 500 行为。
    return GenerationService(
        chain_provider=get_rag_chain,
        docs=get_document_repository(),
    )


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(docs=get_document_repository())


@lru_cache
def get_oa_service() -> OAService:
    return OAService(client=get_oa_client())


@lru_cache
def get_stats_service() -> StatsService:
    return StatsService()
