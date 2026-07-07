"""
============================================================
向量化与向量数据库存储
============================================================
职责：
  1. 初始化 Embedding 模型（OpenAI 兼容接口）。
  2. 将分块后的文本批量向量化。
  3. 存入 Chroma 向量数据库（支持持久化到本地磁盘）。
  4. 提供检索器获取方法（供第二阶段 RAG 链使用）。

设计要点：
  - Embedding 接口使用 langchain-openai 的 OpenAIEmbeddings，
    通过 base_url 参数适配任何兼容 OpenAI 接口的 embedding 服务。
  - 支持批量处理，避免逐条调用 API（提升速度、降低费用）。
  - Chroma 数据持久化到本地，重启后无需重建。
"""

import time
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma

from config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# Embedding 模型工厂
# ============================================================

@lru_cache(maxsize=1)
def create_embeddings() -> Embeddings:
    """
    创建 Embedding 模型实例（进程内单例）。

    用 lru_cache 缓存：快速模式（rag_chain）与深度模式（tools）各自的
    VectorStoreManager 会共享同一份 embedding 模型，避免 BGE 模型被加载两份。
    embedding 推理是只读操作，多个检索器共享同一实例是安全的。

    支持两种模式（通过 .env 中 EMBEDDING_TYPE 切换）：

    【本地模式】EMBEDDING_TYPE=local（默认，推荐）
      使用 HuggingFace 本地模型，免费、离线、无 API 费用。
      首次运行会自动下载模型到本地缓存，请保持网络畅通。
      推荐模型：
        BAAI/bge-small-zh-v1.5    — 轻量，~100MB，启动快
        BAAI/bge-large-zh-v1.5    — 精度高，~1.3GB，效果最佳

    【远程 API 模式】EMBEDDING_TYPE=api
      使用 OpenAI 兼容接口调用远程 Embedding 服务。
      支持任何兼容的 API 提供商：
        - 阿里云百炼
        - 硅基流动
        - OpenAI 官方
    """
    if settings.EMBEDDING_TYPE == "api":
        # ---- 远程 API 模式 ----
        from langchain_openai import OpenAIEmbeddings

        logger.info(f"Embedding 模式：远程 API → {settings.EMBEDDING_MODEL_NAME}")
        return OpenAIEmbeddings(
            model=settings.EMBEDDING_MODEL_NAME,
            base_url=settings.EMBEDDING_BASE_URL,
            api_key=settings.EMBEDDING_API_KEY,
            chunk_size=20,
            show_progress_bar=True,
        )
    else:
        # ---- 本地 HuggingFace 模式（默认）----
        from langchain_huggingface import HuggingFaceEmbeddings

        model_name = settings.LOCAL_EMBEDDING_MODEL
        logger.info(f"Embedding 模式：本地模型 → {model_name}")
        logger.info("  首次使用将自动下载模型（约 100MB），请稍候...")

        embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={
                "normalize_embeddings": True,      # 归一化，方便余弦相似度计算
                "batch_size": 32,
            },
        )
        # float16 半精度 → 模型内存从 ~400MB 降到 ~200MB
        # bge-small-zh-v1.5 对精度不敏感，公文检索完全够用
        # 兼容 langchain-huggingface 新旧版本 API：
        #   旧版 (0.x): 公开属性 .client
        #   新版 (1.x): 私有属性 ._client
        if hasattr(embeddings, 'client'):
            embeddings.client.half()
        elif hasattr(embeddings, '_client'):
            embeddings._client.half()
        else:
            logger.warning("  无法获取 SentenceTransformer client，跳过 float16 半精度切换")
        logger.info("  已切换为 float16 半精度模式（内存 -50%）")
        return embeddings


# ============================================================
# 向量数据库管理器
# ============================================================

class VectorStoreManager:
    """
    向量数据库管理器。

    封装了 Chroma 的初始化、写入、查询等操作，
    对外提供干净的接口。

    使用方式：
        manager = VectorStoreManager()
        manager.build(documents)              # 构建新库
        retriever = manager.get_retriever()   # 获取检索器
    """

    def __init__(self, persist_dir: Path = None):
        """
        Args:
            persist_dir: 向量库持久化目录（None 则用 settings 默认值）。
        """
        self.persist_dir = persist_dir or settings.VECTOR_DB_DIR
        self.embeddings = create_embeddings()
        self._vector_store: Optional[Chroma] = None

        model_name = settings.LOCAL_EMBEDDING_MODEL if settings.EMBEDDING_TYPE == "local" else settings.EMBEDDING_MODEL_NAME
        logger.info(f"Embedding 模型：{model_name}")
        logger.info(f"向量库类型：Chroma（持久化到 {self.persist_dir}）")

    def build(
        self,
        documents: List[Document],
        collection_name: str = None,
    ) -> Chroma:
        """
        构建向量数据库（全量重建）。

        流程：
          1. 删除旧集合（如果存在）
          2. 创建新集合
          3. 批量向量化并写入 Chroma
          4. 持久化到磁盘

        Args:
            documents:       分块后的 Document 列表。
            collection_name: Chroma collection 名称。

        Returns:
            构建完成的 Chroma 实例。
        """
        if not documents:
            raise ValueError("documents 列表为空，无法构建向量库")

        collection_name = collection_name or settings.CHROMA_COLLECTION_NAME
        logger.info(f"开始构建向量库：{len(documents)} 个文本块")

        # ---- 确保持久化目录存在 ----
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # ---- 删除旧集合（全量重建模式） ----
        try:
            old_store = Chroma(
                collection_name=collection_name,
                embedding_function=self.embeddings,
                persist_directory=str(self.persist_dir),
            )
            # 获取旧集合中的文档数量
            old_count = old_store._collection.count()
            if old_count > 0:
                logger.info(f"检测到旧向量库（{old_count} 条），正在清除...")
                old_store.delete_collection()
        except Exception:
            # 旧库不存在或已损坏，忽略继续
            pass

        # ---- 批量写入（带重试机制，应对 API 限流） ----
        batch_size = 50  # 每批 50 条，避免单次请求过大
        total = len(documents)
        max_retries = 3

        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch = documents[batch_start:batch_end]

            for attempt in range(max_retries):
                try:
                    if self._vector_store is None:
                        # 第一批：创建 Chroma 实例
                        self._vector_store = Chroma.from_documents(
                            documents=batch,
                            embedding=self.embeddings,
                            collection_name=collection_name,
                            persist_directory=str(self.persist_dir),
                        )
                    else:
                        # 后续批次：追加文档
                        self._vector_store.add_documents(batch)

                    logger.info(
                        f"  批次 [{batch_start}-{batch_end}/{total}] "
                        f"写入成功"
                    )
                    break  # 成功 → 跳出重试循环

                except Exception as e:
                    if attempt < max_retries - 1:
                        wait = 2 ** attempt  # 指数退避：1s, 2s, 4s
                        logger.warning(
                            f"  批次 [{batch_start}-{batch_end}] "
                            f"写入失败（重试 {attempt + 1}/{max_retries}）：{e}"
                        )
                        time.sleep(wait)
                    else:
                        logger.error(
                            f"  批次 [{batch_start}-{batch_end}] "
                            f"最终失败：{e}"
                        )
                        raise

        # ---- 确保持久化 ----
        # Chroma 在写入时已自动持久化，但显式调用一次无妨
        logger.info(
            f"向量库构建完成！总计 {total} 条向量，"
            f"持久化路径：{self.persist_dir}"
        )
        return self._vector_store

    def load(self, collection_name: str = None) -> Chroma:
        """
        从磁盘加载已有的向量数据库。

        适用于：知识库已构建过，重启后直接加载使用。

        Args:
            collection_name: Chroma collection 名称。

        Returns:
            加载的 Chroma 实例。

        Raises:
            FileNotFoundError: 向量库目录不存在或为空。
        """
        collection_name = collection_name or settings.CHROMA_COLLECTION_NAME

        if not self.persist_dir.exists():
            raise FileNotFoundError(
                f"向量库目录不存在：{self.persist_dir}\n"
                f"请先运行 build_knowledge_base.py 构建知识库"
            )

        self._vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_dir),
        )

        count = self._vector_store._collection.count()
        logger.info(f"已加载向量库：{count} 条记录（路径：{self.persist_dir}）")
        return self._vector_store

    def get_retriever(
        self,
        k: int = None,
        search_type: str = "similarity",
    ) -> VectorStoreRetriever:
        """
        获取 LangChain 兼容的检索器。

        Args:
            k:           返回的文档数量。
            search_type: 检索类型：
                           "similarity"         → 余弦相似度（默认）
                           "mmr"                → 最大边际相关性（去重）
                           "similarity_score_threshold" → 相似度阈值过滤

        Returns:
            VectorStoreRetriever 实例，可直接用于 RAG 链。
        """
        if self._vector_store is None:
            raise RuntimeError(
                "向量库未初始化，请先调用 build() 或 load()"
            )

        k = k or settings.RETRIEVER_K
        return self._vector_store.as_retriever(
            search_type=search_type,
            search_kwargs={"k": k},
        )

    @property
    def is_ready(self) -> bool:
        """检查向量库是否已经初始化并可用。"""
        return self._vector_store is not None


# ============================================================
# 便捷函数
# ============================================================

def build_vector_store(
    documents: List[Document],
    persist_dir: Path = None,
) -> Chroma:
    """便捷函数：一行构建向量库。"""
    manager = VectorStoreManager(persist_dir=persist_dir)
    return manager.build(documents)


def load_vector_store(persist_dir: Path = None) -> VectorStoreManager:
    """便捷函数：加载已有向量库并返回 manager。"""
    manager = VectorStoreManager(persist_dir=persist_dir)
    manager.load()
    return manager
