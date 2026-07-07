"""
============================================================
公文语义分块器（Chunking Strategy）
============================================================
设计原则：
  1. **语义优先**： 公文有严格的格式层级（标题 → 主送 → 正文 → 落款），
     分块时必须保持每个 chunk 内部语义完整。
  2. **结构感知**： 利用 doc_loader 中标记的 category 元数据，
     在标题前、落款前做「强制切分」，阻止跨章节合并。
  3. **重叠保留**： 相邻块保留一定重叠，确保跨 chunk 检索时
     不会丢失边界处的上下文。
  4. **长度合理**： 默认 800 字符/块，符合主流 embedding 模型的
     最佳输入长度（如 text-embedding-3-small 推荐 ≤ 8192 tokens）。

分块策略详解：
  ┌──────────────────────────────────────────────────┐
  │  原始公文                                          │
  │  ┌─ 标题段 (header)      ──→ 强制断点 ──┐         │
  │  ├─ 主送机关 (recipient)  ──→ 强制断点 ──┤         │
  │  ├─ 正文段1 (body)                    ├─ Chunk 1 │
  │  ├─ 正文段2 (body)       ──→ 长度截断 ──┤         │
  │  ├─ 正文段3 (body)                    ├─ Chunk 2 │
  │  │   ... (body)                       │  (带重叠)│
  │  ├─ 附件 (attachment)    ──→ 强制断点 ──┤         │
  │  └─ 落款 (signature)     ──→ 强制断点 ──┘         │
  └──────────────────────────────────────────────────┘
"""

from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)

from config.settings import settings
from src.infra.logger import get_logger
logger = get_logger(__name__)


# ============================================================
# 自定义分隔符列表 —— 按公文结构优先级排列
# ============================================================

# RecursiveCharacterTextSplitter 会按顺序尝试用这些分隔符切分，
# 优先级从高到低：先尝试段落间空行 → 单换行 → 句号 → 逗号 → 空格
_GONGWEN_SEPARATORS = [
    # 第一优先级：段落间空行（公文段落间通常有空行）
    "\n\n\n",
    "\n\n",
    # 第二优先级：单换行
    "\n",
    # 第三优先级：中文标点句号（语义边界强）
    "。",
    "；",   # 分号也是较强边界
    # 第四优先级：逗号
    "，",
    # 第五优先级：空格
    " ",
    # 兜底：逐字符切分
    "",
]


# ============================================================
# 结构感知包裹器
# ============================================================

class StructureAwareSplitter:
    """
    结构感知的公文分块器。

    工作流程：
      1. 解析每个 Document 的 elements 元数据，识别 header/body/signature 边界。
      2. 在结构边界处插入「分块标记」（特殊分隔符），强制 splitter 在此断开。
      3. 调用 RecursiveCharacterTextSplitter 按长度和分隔符完成最终切分。
    """

    # 强制断点对应的 category 集合
    FORCE_BREAK_CATEGORIES = {"header", "recipient", "signature", "attachment"}

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        """
        Args:
            chunk_size:   每块最大字符数（None 则用 settings 默认值）。
            chunk_overlap: 相邻块重叠字符数。
        """
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP

        # ---- 底层字符切分器 ----
        self._base_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=_GONGWEN_SEPARATORS,
            # 使用字符级长度函数（兼容中文，一个汉字 = 1 个字符）
            length_function=len,
            is_separator_regex=False,
            # 强制在分隔符处断开（而非贪婪合并）
            keep_separator="end",
        )

    def _insert_structure_breaks(self, doc: Document) -> str:
        """
        在文档文本中插入结构标记。

        核心逻辑：
          遍历 elements 元数据，每当遇到 header/recipient/signature/attachment
          类别时，在前方插入两个连续换行（触发 splitter 的 "\n\n" 分隔符），
          从而实现「强制切分」。

        Args:
            doc: 原始 LangChain Document。

        Returns:
            插入了结构断点的文本字符串。
        """
        elements = doc.metadata.get("elements", [])
        if not elements:
            # 没有元数据 → 直接返回原始内容
            return doc.page_content

        # 将文本按原始段落分隔符切开
        paragraphs = doc.page_content.split("\n\n")
        if len(paragraphs) != len(elements):
            # 段落与元数据数量不一致（例如表格合并了多个段落），
            # 安全降级：在 category 变化处插入断点。
            logger.debug(
                f"段落数({len(paragraphs)})与元数据数({len(elements)})不一致，"
                f"使用 category 边界切分"
            )
            return self._insert_breaks_by_category(doc)

        # 为每个段落添加结构信息
        annotated = []
        for i, (para, meta) in enumerate(zip(paragraphs, elements)):
            cat = meta.get("category", "body")
            if cat in self.FORCE_BREAK_CATEGORIES and i > 0:
                # 在结构边界前插入双换行 → 强制切分
                annotated.append(f"\n\n---{cat}---\n\n{para}")
            else:
                annotated.append(para)

        return "\n\n".join(annotated)

    def _insert_breaks_by_category(self, doc: Document) -> str:
        """
        降级方案：按 category 变化位置插入断点。
        用于 paragraphs 与 elements 数量不匹配的情况。
        """
        elements = doc.metadata.get("elements", [])
        texts = doc.page_content.split("\n")

        # 简单策略：将文本按换行切分，在 category 变化处加标记
        result_parts = []
        prev_cat = None
        for i, elem in enumerate(elements):
            cat = elem.get("category", "body")
            if i < len(texts):
                line = texts[i]
            else:
                line = ""
            if cat in self.FORCE_BREAK_CATEGORIES and cat != prev_cat:
                result_parts.append(f"\n\n---{cat}---\n\n{line}")
            else:
                result_parts.append(line)
            prev_cat = cat

        return "\n".join(result_parts)

    def split_documents(self, documents: List[Document]) -> List[Document]:
        """
        主入口：对文档列表执行结构感知分块。

        流程：
          1. 为每个 Document 插入结构断点
          2. 调用 RecursiveCharacterTextSplitter 切分
          3. 清理分块中的结构标记（可选保留）
          4. 为每个 chunk 补充元数据（源文件、分块序号等）

        Args:
            documents: langchain_core Document 列表。

        Returns:
            分块后的 Document 列表。
        """
        all_chunks: List[Document] = []

        for doc in documents:
            # Step 1: 插入结构断点
            annotated_text = self._insert_structure_breaks(doc)

            # Step 2: 用底层切分器执行长度切分
            # 构造临时 Document 用于切分
            temp_doc = Document(
                page_content=annotated_text,
                metadata={"source": doc.metadata.get("source", "unknown")},
            )
            chunks = self._base_splitter.split_documents([temp_doc])

            # Step 3: 清理并补充元数据
            for i, chunk in enumerate(chunks):
                # 去掉结构标记（如 "---header---"），保持文本干净
                clean_text = self._clean_chunk(chunk.page_content)

                # 补充丰富的元数据，方便后续检索溯源
                all_chunks.append(Document(
                    page_content=clean_text,
                    metadata={
                        "source": doc.metadata.get("source", "unknown"),
                        "file_path": doc.metadata.get("file_path", ""),
                        "chunk_index": i,
                        "chunk_total": len(chunks),
                        "char_count": len(clean_text),
                    },
                ))

        logger.info(
            f"分块完成：{len(documents)} 个文档 → "
            f"{len(all_chunks)} 个语义块 "
            f"(chunk_size={self.chunk_size}, overlap={self.chunk_overlap})"
        )
        return all_chunks

    @staticmethod
    def _clean_chunk(text: str) -> str:
        """
        清理分块中的结构标记。

        保留操作：
          - 去掉 ---category--- 标记（仅用于切分，检索不需要）
          - 合并多余空白
          - 去掉首尾无意义换行
        """
        import re
        # 去掉结构标记
        text = re.sub(r"^[\s]*---\w+---[\s]*", "", text)
        text = re.sub(r"\n[\s]*---\w+---[\s]*\n", "\n\n", text)
        # 合并 3 个以上连续换行为双换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


# ============================================================
# 便捷函数
# ============================================================

def split_gongwen_documents(
    documents: List[Document],
    chunk_size: int = None,
    chunk_overlap: int = None,
) -> List[Document]:
    """便捷函数：一行完成公文分块。"""
    splitter = StructureAwareSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(documents)
