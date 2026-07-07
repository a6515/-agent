"""
============================================================
Word 公文文档加载器
============================================================
职责：
  1. 扫描指定目录下所有 .docx 文件。
  2. 使用 python-docx 解析段落、表格、页眉页脚。
  3. 对公文常见的结构（红头、标题、正文、附件、落款）
     进行智能段落分类，为后续分块提供结构元数据。
  4. 输出标准化的 LangChain Document 列表。

公文 .docx 的结构特征（以党政机关公文格式为例）：
  - 红头/版头： 文件头部的发文机关标志（通常位于页眉或前几段）
  - 发文字号：  "X发〔2025〕X号" 格式
  - 标题：    一般用 2 号小标宋体，居中
  - 主送机关： 顶格，冒号结尾
  - 正文：    3 号仿宋体，首行缩进 2 字符
  - 附件说明： "附件：1. ..." 格式
  - 落款：    发文机关 + 成文日期 + 印章位置
  - 版记：    抄送机关、印发日期
"""

import re
from pathlib import Path
from typing import List, Dict, Optional

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from langchain_core.documents import Document

from src.infra.logger import get_logger

logger = get_logger(__name__)


# ============================================================
# 公文结构标记 —— 用正则识别常见公文段落类型
# ============================================================

# 发文字号模式：例如 "国发〔2025〕1号"、"X办发〔2024〕15号"
# 支持中文/英文/数字前缀
PATTERN_DOC_NUMBER = re.compile(
    r".*[〔\[（(]\s*(\d{4})\s*[〕\]）)]\s*\d+\s*号.*"
)

# 标题特征：纯中文短句，通常不含标点，长度 20-60 字
PATTERN_TITLE = re.compile(
    r"^(关于|转发|印发|在|认真).{4,60}$"
)

# 附件标记
PATTERN_ATTACHMENT = re.compile(
    r"^附件[：:]|^\d+[\.\、]"
)

# 主送机关：顶格书写，以冒号结尾，通常包含部门、单位等
PATTERN_RECIPIENT = re.compile(
    r".*(省|市|县|区|部|委|局|厅|公司|集团|单位|机关|办).*[：:]$"
)

# 落款特征：日期在末尾，如 "2025年1月1日"
PATTERN_DATE = re.compile(
    r"\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
)


# ============================================================
# 辅助函数
# ============================================================

def _extract_paragraph_text(para: Paragraph) -> str:
    """
    提取段落纯文本，处理 python-docx 段落对象。
    会过滤掉纯空白段落和仅含标点的无意义段落。
    """
    text = para.text.strip()
    if not text:
        return ""
    # 过滤仅由空白字符、破折号、下划线组成的装饰线
    if re.match(r"^[\s\-\—\_\=]{3,}$", text):
        return ""
    return text


def _extract_table_text(table: Table) -> str:
    """
    提取 Word 表格中的文本。
    将表格转换为结构化的文本表示，保留行列关系。
    常见于「呈报表」「审批单」等 OA 表单型公文。
    """
    rows = []
    for row in table.rows:
        cells = []
        for cell in row.cells:
            cell_text = cell.text.strip().replace("\n", " ")
            cells.append(cell_text)
        rows.append(" | ".join(cells))
    return "\n".join(rows)


def _classify_paragraph(text: str, index: int, total: int) -> str:
    """
    根据文本内容和位置对段落进行分类标记。
    用于后续分块时保留语义边界。

    返回值：
      "header"     — 标题/版头
      "recipient"  — 主送机关
      "body"       — 正文
      "attachment" — 附件
      "signature"  — 落款/日期
      "other"      — 其他
    """
    # 前 5 段中出现的可能是红头/版头
    if index < 5 and len(text) < 80:
        # 短文本在文档开头：可能是发文字号或密级
        if PATTERN_DOC_NUMBER.match(text):
            return "header"
        return "other"

    # 标题：前 1/3 位置、长度适中、符合标题模式
    if index < total / 3 and PATTERN_TITLE.match(text) and len(text) < 80:
        return "header"

    # 主送机关
    if PATTERN_RECIPIENT.match(text) and len(text) < 40:
        return "recipient"

    # 附件
    if PATTERN_ATTACHMENT.match(text) and index > total * 0.6:
        return "attachment"

    # 落款（日期 + 发文机关）：文档末尾
    if index > total * 0.7:
        if PATTERN_DATE.search(text):
            return "signature"

    # 其余归为正文
    return "body"


# ============================================================
# 核心加载器
# ============================================================

class GongwenDocLoader:
    """
    公文 Word 文档加载器。

    使用方式：
        loader = GongwenDocLoader(docs_dir)
        documents = loader.load()
    """

    def __init__(self, docs_dir: Path):
        """
        Args:
            docs_dir: 存放 .docx 公文的目录路径。
        """
        self.docs_dir = Path(docs_dir)
        if not self.docs_dir.exists():
            raise FileNotFoundError(f"公文目录不存在：{self.docs_dir}")

    def _find_docx_files(self) -> List[Path]:
        """递归扫描目录下所有 .docx 文件，跳过 Word 临时文件（~$开头）。"""
        all_files = list(self.docs_dir.rglob("*.docx"))
        valid_files = [
            f for f in all_files
            if not f.name.startswith("~$")  # 跳过 Word 临时锁文件
        ]
        logger.info(f"扫描到 {len(all_files)} 个 .docx 文件，"
                     f"有效 {len(valid_files)} 个（已跳过临时文件）")
        return valid_files

    def _parse_single_doc(self, file_path: Path) -> Optional[Document]:
        """
        解析单个 .docx 文件为 LangChain Document。

        处理逻辑：
          1. 逐段提取文本并分类标记
          2. 将表格内容单独提取并标注
          3. 组合段落元数据（文件名、分类标签、位置索引）

        Returns:
            Document 对象，或 None（文件损坏时）。
        """
        try:
            docx = DocxDocument(str(file_path))
        except Exception as e:
            logger.error(f"无法打开文件 {file_path.name}：{e}")
            return None

        paragraphs_text: List[str] = []
        metadata_list: List[Dict] = []

        # ---- 收集所有有意义的内容块 ----
        # python-docx 的 paragraphs 包含正文段落，但不直接包含表格文本，
        # 我们需要遍历 document.body 的 XML 子元素来保持顺序。
        body = docx.element.body
        para_index = 0
        total_elements = len(list(body))

        for child in body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                # ---- 普通段落 ----
                para = Paragraph(child, docx)
                text = _extract_paragraph_text(para)
                if text:
                    category = _classify_paragraph(
                        text, para_index, total_elements
                    )
                    paragraphs_text.append(text)
                    metadata_list.append({
                        "source": file_path.name,
                        "category": category,
                        "element_index": para_index,
                        "type": "paragraph",
                        "char_count": len(text),
                    })
                para_index += 1

            elif tag == "tbl":
                # ---- 表格 ----
                table = Table(child, docx)
                table_text = _extract_table_text(table)
                if table_text.strip():
                    paragraphs_text.append(table_text)
                    metadata_list.append({
                        "source": file_path.name,
                        "category": "table",
                        "element_index": para_index,
                        "type": "table",
                        "char_count": len(table_text),
                    })
                para_index += 1

        if not paragraphs_text:
            logger.warning(f"文件 {file_path.name} 没有可提取的文本内容")
            return None

        # ---- 组合成 LangChain Document ----
        full_text = "\n\n".join(paragraphs_text)
        return Document(
            page_content=full_text,
            metadata={
                "source": file_path.name,
                "file_path": str(file_path),
                "total_chars": len(full_text),
                "paragraph_count": len(paragraphs_text),
                "elements": metadata_list,
            },
        )

    def load(self) -> List[Document]:
        """
        主入口：加载目录下所有公文文档。

        Returns:
            LangChain Document 列表。
        """
        files = self._find_docx_files()
        if not files:
            logger.warning("未找到任何 .docx 文件，请将公文放入 data/raw_docs/ 目录")
            return []

        documents: List[Document] = []
        for f in files:
            logger.info(f"正在解析：{f.name}")
            doc = self._parse_single_doc(f)
            if doc:
                documents.append(doc)
                logger.info(f"  [OK] {f.name} -> {doc.metadata['total_chars']} chars, "
                            f"{doc.metadata['paragraph_count']} paragraphs")

        logger.info(f"加载完成：共 {len(files)} 个文件 → {len(documents)} 个文档")
        return documents


# ============================================================
# 便捷函数
# ============================================================

def load_gongwen_documents(docs_dir: Path) -> List[Document]:
    """便捷函数：一行加载公文目录。"""
    loader = GongwenDocLoader(docs_dir)
    return loader.load()
