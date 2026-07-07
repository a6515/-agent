"""
============================================================
检索器封装
============================================================
职责：
  1. 从 Chroma 向量库加载已有知识库。
  2. 根据用户查询检索最相关的公文范文片段。
  3. 支持相似度检索（similarity）和最大边际相关性检索（MMR）。
  4. 对检索结果做后处理：去重、按相关度排序、格式化输出。

设计考量：
  - MMR（Maximum Marginal Relevance）模式适合需要多样化结果的场景，
    比如用户指令可能涉及多种公文类型，MMR 可以返回不同类型的范文。
  - 相似度阈值过滤可以排除完全不相关的结果，避免 LLM 被噪声干扰。
"""

from typing import List, Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever

from config.settings import settings
from src.ingestion.embed_store import VectorStoreManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 检索器工厂
# ============================================================

class GongwenRetriever:
    """
    公文知识库检索器。

    封装了向量库加载、检索参数配置和结果后处理，
    为 RAG 链提供即插即用的检索能力。

    使用方式：
        retriever = GongwenRetriever()
        docs = retriever.retrieve("写一份购买3台服务器的请示")
    """

    def __init__(
        self,
        k: int = None,
        search_type: str = "similarity",
        score_threshold: float = None,
    ):
        """
        Args:
            k:               返回文档数（None 则用 settings 默认值）。
            search_type:     检索算法类型。
                               "similarity" → 余弦相似度（默认，适合精准匹配）
                               "mmr"        → 最大边际相关性（结果更多样化）
                               "similarity_score_threshold" → 带相似度阈值过滤
            score_threshold: 相似度阈值（仅 search_type="similarity_score_threshold" 时生效）。
        """
        self.k = k or settings.RETRIEVER_K
        self.search_type = search_type
        self.score_threshold = score_threshold

        # ---- 加载向量库 ----
        logger.info("正在加载向量知识库...")
        self._manager = VectorStoreManager()
        try:
            self._manager.load()
            self._retriever = self._build_retriever()
        except FileNotFoundError:
            logger.error(
                "向量库未找到！请先运行 scripts/build_knowledge_base.py 构建知识库"
            )
            raise

    def _build_retriever(self) -> VectorStoreRetriever:
        """
        构建 LangChain 检索器实例。

        根据 search_type 配置不同的检索策略：
          - similarity: 纯余弦相似度排序
          - mmr: 平衡相关性和多样性（fetch_k 取 k*2 的候选再精选）
          - similarity_score_threshold: 低于阈值的直接丢弃
        """
        search_kwargs = {"k": self.k}

        if self.search_type == "mmr":
            # MMR 需要更大的候选池
            search_kwargs["fetch_k"] = self.k * 3
            search_kwargs["lambda_mult"] = 0.7  # 0=最大多样性, 1=最大相关性

        elif self.search_type == "similarity_score_threshold":
            search_kwargs["score_threshold"] = self.score_threshold or 0.5

        return self._manager._vector_store.as_retriever(
            search_type=self.search_type,
            search_kwargs=search_kwargs,
        )

    def retrieve(self, query: str) -> List[Document]:
        """
        根据用户查询检索相关公文范文。

        Args:
            query: 用户的简短提示，例如 "写一份申请购买3台服务器的请示"。

        Returns:
            相关公文 Document 列表，按相关度降序排列。
        """
        if not query or not query.strip():
            logger.warning("查询为空，返回空列表")
            return []

        docs = self._retriever.invoke(query.strip())

        logger.info(
            f"检索完成：query='{query[:50]}...' → {len(docs)} 条结果"
        )
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "unknown")
            chars = doc.metadata.get("char_count", len(doc.page_content))
            logger.debug(
                f"  [{i+1}] {source} | {chars} 字符 | "
                f"首句: {doc.page_content[:60]}..."
            )

        return docs

    def format_for_prompt(self, docs: List[Document]) -> str:
        """
        将检索到的文档格式化为 Prompt 中可直接使用的文本。

        格式化策略：
          - 每条结果标注来源文件名
          - 用分隔线区分不同范文
          - 截取关键内容（每篇最多 1000 字），避免 Prompt 过长

        Args:
            docs: 检索到的 Document 列表。

        Returns:
            格式化后的文本，可直接插入 System Prompt 的 {context} 占位符。
        """
        if not docs:
            return "（未检索到相关范文，请根据公文写作规范自主撰写。）"

        parts = []
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source", "未知来源")
            content = doc.page_content

            # 截断过长内容（保留完整语义，同时在 token 预算内）
            if len(content) > 1000:
                content = content[:1000] + "\n……（后文省略）"

            parts.append(
                f"【范文 {i + 1}】来源：{source}\n"
                f"{'─' * 50}\n"
                f"{content}\n"
                f"{'─' * 50}"
            )

        return "\n\n".join(parts)

    @property
    def is_ready(self) -> bool:
        """检查检索器是否就绪。"""
        return self._manager.is_ready


# ============================================================
# 便捷函数
# ============================================================

def get_retriever(
    k: int = None,
    search_type: str = "similarity",
) -> GongwenRetriever:
    """
    便捷函数：获取一个即用检索器实例。

    Args:
        k:           返回文档数。
        search_type: 检索类型。

    Returns:
        就绪的 GongwenRetriever 实例。
    """
    return GongwenRetriever(k=k, search_type=search_type)
