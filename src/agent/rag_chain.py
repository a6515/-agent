"""
============================================================
RAG 链（LCEL 语法）—— 检索增强生成核心
============================================================
职责：
  1. 构建 LangChain LCEL 链：检索 → 格式化 → 提示词填充 → LLM 生成。
  2. 支持同步和流式两种输出模式。
  3. 内置公文类型识别器，自动判断用户意图对应的公文文种。
  4. 封装为简洁的调用接口，方便命令行测试和 API 调用。

LCEL 数据流：
  用户输入 (str)
      │
      ▼
  ┌──────────────────────┐
  │  1. 检索相关范文      │  ← retriever.retrieve()
  │     输出: List[Doc]   │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  2. 格式化检索结果    │  ← retriever.format_for_prompt()
  │     输出: str         │
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  3. 组装完整 Prompt   │  ← ChatPromptTemplate
  │     {context} +       │    填充 SYSTEM_PROMPT 的
  │     {question}        │    {context} 和 {question}
  └──────────┬───────────┘
             │
             ▼
  ┌──────────────────────┐
  │  4. LLM 生成          │  ← ChatOpenAI (DeepSeek)
  │     输出: str         │    低温度保证稳定性
  └──────────────────────┘
"""

import re
from datetime import datetime
from typing import List, Optional, Iterator, AsyncIterator

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from config.settings import settings
from src.agent.prompts import SYSTEM_PROMPT
from src.agent.retriever import GongwenRetriever, get_retriever
from src.utils.helpers import build_date_hint, enhance_query_with_doc_type
from src.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 预编译正则模式（避免每次调用时重复编译）
# ============================================================

# AI 套话清理 — 开头模式
_CLEAN_PATTERNS_START = [
    re.compile(r"^(好的[，,。\.]?\s*)+"),
    re.compile(r"^以下是[为您]*生成的.*?[：:]\s*"),
    re.compile(r"^根据您的要求[，,]?\s*我.*?[：:]\s*"),
    re.compile(r"^为您撰写.*?如下[：:]\s*"),
    re.compile(r"^这是.*?公文[：:]\s*"),
    re.compile(r"^生成结果[如下]*[：:]\s*"),
    re.compile(r"^(当然|没问题|好的|明白了)[，,。\.]?\s*"),
    re.compile(r"^作为.*?(公文秘书|AI|语言模型).*?[：:]\s*"),
]

# AI 套话清理 — 结尾模式
_CLEAN_PATTERNS_END = [
    re.compile(r"\s*希望以上内容[对能].*?[。\.]?\s*$"),
    re.compile(r"\s*如有[任何]*?(疑问|问题|需要).*?[。\.]?\s*$"),
    re.compile(r"\s*以上[是就].*?生成.*?[。\.]?\s*$"),
    re.compile(r"\s*请注意.*?[。\.]?\s*$"),
    re.compile(r"\s*综上所述[，,].*?[。\.]?\s*$"),
]

# 多余空白行
_RE_MULTI_NEWLINES = re.compile(r"\n{3,}")

# 文种关键词集合（用于 query 增强检查）
_DOC_TYPE_NAMES = {"请示", "报告", "通知", "函", "纪要", "决定", "批复", "通报", "公告", "意见"}


# ============================================================
# 公文类型识别
# ============================================================

# 公文文种关键词映射（用于自动识别用户意图）
_DOC_TYPE_KEYWORDS = {
    "请示": ["请示", "申请", "审批", "批准", "购置", "立项", "拨款", "批复"],
    "报告": ["报告", "汇报", "总结", "述职", "情况反映"],
    "通知": ["通知", "告知", "发布", "印发", "转发", "会议", "放假", "任免"],
    "函":   ["函", "商洽", "询问", "答复", "征询", "商请"],
    "纪要": ["纪要", "会议纪要", "座谈纪要"],
    "决定": ["决定", "表彰", "处分", "撤销"],
    "批复": ["批复", "批示"],
    "通报": ["通报", "表扬", "批评"],
    "公告": ["公告", "通告"],
    "意见": ["意见", "建议"],
}


def detect_doc_type(user_query: str) -> str:
    """
    根据用户输入自动识别公文类型。

    识别逻辑：
      1. 遍历关键词映射表，匹配得分最高的文种。
      2. 如果用户明确提及了文种名称（如"写一份请示"），直接采用。
      3. 无法识别时默认返回"公文"。

    Args:
        user_query: 用户的简短提示。

    Returns:
        公文文种名称，如 "请示"、"通知"、"报告" 等。
    """
    scores = {}
    for doc_type, keywords in _DOC_TYPE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in user_query:
                # 精确包含关键词，计分
                score += 1
        if score > 0:
            scores[doc_type] = score

    if not scores:
        return "公文"

    # 得分最高的文种
    best = max(scores, key=scores.get)
    logger.debug(f"公文类型识别：'{user_query[:40]}...' → {best}")
    return best


# ============================================================
# LLM 工厂
# ============================================================

def create_llm() -> ChatOpenAI:
    """
    创建 LLM 实例（DeepSeek，兼容 OpenAI 接口）。

    参数说明：
      - temperature=0.3:  低温度确保输出稳定和格式规范。
      - max_tokens=4096:  足够生成完整的公文（通常 800-2000 字）。
      - 支持 streaming:   用于流式输出（后续 FastAPI 可用）。
    """
    return ChatOpenAI(
        model=settings.LLM_MODEL_NAME,
        base_url=settings.LLM_BASE_URL,
        api_key=settings.LLM_API_KEY,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=4096,
        streaming=True,  # 开启流式支持
        verbose=False,
    )


# ============================================================
# RAG 链构建（LCEL）
# ============================================================

class GongwenRAGChain:
    """
    公文 RAG 链。

    封装完整的 LCEL 管道，对外暴露简洁的调用接口。

    使用方式：
        chain = GongwenRAGChain()
        result = chain.invoke("写一份申请购买3台服务器的请示")
        # 或流式
        for chunk in chain.stream("写一份通知"):
            print(chunk, end="")
    """

    def __init__(self, retriever: GongwenRetriever = None):
        """
        Args:
            retriever: 检索器实例（None 则自动创建默认检索器）。
        """
        self.retriever = retriever or get_retriever()
        self.llm = create_llm()

        # ---- 构建 LCEL 管道 ----
        self._chain = self._build_chain()

        logger.info(f"RAG 链已就绪：LLM={settings.LLM_MODEL_NAME}, "
                     f"检索器=k={self.retriever.k}")

    def _build_chain(self):
        """
        使用 LCEL 语法构建 RAG 管道。

        管道步骤：
          1. 检索：   RunnableLambda 包裹检索逻辑
          2. 格式化： RunnableLambda 将检索结果格式化为文本
          3. 组装：   ChatPromptTemplate 填充 {context} 和 {question}
          4. 生成：   ChatOpenAI.invoke()
          5. 解析：   StrOutputParser() 提取纯文本
        """
        # ---- Prompt 模板 ----
        prompt = ChatPromptTemplate.from_template(SYSTEM_PROMPT)

        # ---- 检索 + 格式化（组合为一步）----
        def _retrieve_and_format(query: str) -> dict:
            """检索并格式化，返回 {context, question} 字典。"""
            # 检索
            docs = self.retriever.retrieve(query)
            # 格式化为 Markdown 友好的文本
            context = self.retriever.format_for_prompt(docs)
            return {"context": context, "question": query}

        # ---- LCEL 管道 ----
        chain = (
            RunnableLambda(_retrieve_and_format)  # Step 1+2: 检索 & 格式化
            | prompt                                # Step 3: 填充 Prompt
            | self.llm                              # Step 4: LLM 生成
            | StrOutputParser()                     # Step 5: 提取纯文本
        )

        return chain

    def _prepare_query(self, query: str, doc_type: Optional[str] = None) -> str:
        """
        预处理用户输入：清洗、日期注入、文种引导增强。

        提取公共逻辑供 invoke()/ainvoke()/stream()/astream() 复用。

        Args:
            query:    用户原始提示。
            doc_type: 已识别的文种（调用方传入则不重复检测，也让用户显式指定生效）。
        """
        if not query or not query.strip():
            raise ValueError("用户提示不能为空")

        query = query.strip()
        doc_type = doc_type or detect_doc_type(query)
        logger.info(f"收到请求 → 公文类型：{doc_type}")

        # ---- 注入当前日期 + 增强文种引导（复用公共函数）----
        query = build_date_hint() + enhance_query_with_doc_type(query, doc_type)
        return query

    def invoke(self, query: str, doc_type: Optional[str] = None) -> str:
        """
        同步调用：输入用户提示，输出公文正文。
        """
        query = self._prepare_query(query, doc_type)

        try:
            result = self._chain.invoke(query)
            result = self._clean_output(result)
            logger.info(f"生成完成：{len(result)} 字符")
            return result
        except Exception as e:
            logger.error(f"生成失败：{e}")
            raise

    async def ainvoke(self, query: str, doc_type: Optional[str] = None) -> str:
        """
        异步调用：与 invoke() 等价，但不阻塞 FastAPI 事件循环。
        """
        query = self._prepare_query(query, doc_type)

        try:
            result = await self._chain.ainvoke(query)
            result = self._clean_output(result)
            logger.info(f"生成完成：{len(result)} 字符")
            return result
        except Exception as e:
            logger.error(f"生成失败：{e}")
            raise

    def stream(self, query: str, doc_type: Optional[str] = None) -> Iterator[str]:
        """
        流式调用：逐 token 返回生成的公文正文。
        """
        query = self._prepare_query(query, doc_type)

        try:
            for chunk in self._chain.stream(query):
                yield chunk
        except Exception as e:
            logger.error(f"流式生成失败：{e}")
            raise

    async def astream(
        self, query: str, doc_type: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        异步流式调用：与 stream() 等价，但不阻塞 FastAPI 事件循环。
        """
        query = self._prepare_query(query, doc_type)

        try:
            async for chunk in self._chain.astream(query):
                yield chunk
        except Exception as e:
            logger.error(f"流式生成失败：{e}")
            raise

    @staticmethod
    def _clean_output(text: str) -> str:
        """
        输出后处理：清理 AI 可能产生的废话和不规范内容。
        """
        # ---- 去掉开头的 AI 套话 ----
        for pat in _CLEAN_PATTERNS_START:
            text = pat.sub("", text)

        # ---- 去掉结尾的 AI 套话 ----
        for pat in _CLEAN_PATTERNS_END:
            text = pat.sub("", text)

        # ---- 合并多余空白行 ----
        text = _RE_MULTI_NEWLINES.sub("\n\n", text)

        # ---- 首尾去空白 ----
        return text.strip()


# ============================================================
# 便捷函数
# ============================================================

def build_rag_chain(
    k: int = None,
    search_type: str = "similarity",
) -> GongwenRAGChain:
    """
    便捷函数：一行构建即用的 RAG 链。

    Args:
        k:           检索返回文档数。
        search_type: 检索类型。

    Returns:
        就绪的 GongwenRAGChain 实例。

    Usage:
        chain = build_rag_chain()
        result = chain.invoke("写一份购买打印机的请示")
    """
    retriever = get_retriever(k=k, search_type=search_type)
    return GongwenRAGChain(retriever=retriever)
