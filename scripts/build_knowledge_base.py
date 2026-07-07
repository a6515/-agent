"""
============================================================
【第一阶段 运行入口】构建公文知识库
============================================================
使用方式：
    cd D:/python-projects/oa-agent
    python scripts/build_knowledge_base.py

前置条件：
    1. 将 .docx 公文范文放入 data/raw_docs/ 目录
    2. 配置好 .env 文件中的 Embedding API 信息
    3. pip install -r requirements.txt

执行流程：
    Step 1 — 扫描并加载所有 .docx 文件
    Step 2 — 结构感知的语义分块
    Step 3 — 向量化并存入 Chroma 数据库
    Step 4 — 输出统计信息
"""

import sys
import time
from pathlib import Path

# ---- 将项目根目录加入 sys.path ----
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

from config.settings import settings
from src.ingestion.doc_loader import load_gongwen_documents
from src.ingestion.text_splitter import split_gongwen_documents
from src.ingestion.embed_store import build_vector_store
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main():
    """知识库构建主流程。"""
    logger.info("=" * 60)
    logger.info("  致远 OA 公文知识库构建工具")
    logger.info("=" * 60)

    start_time = time.time()

    # ========================================
    # Step 1: 加载文档
    # ========================================
    logger.info("\n[Step 1/3] 加载 Word 公文文档...")
    logger.info(f"  扫描目录：{settings.RAW_DOCS_DIR}")

    documents = load_gongwen_documents(settings.RAW_DOCS_DIR)

    if not documents:
        logger.error(
            "未找到任何文档！请将 .docx 公文放入 data/raw_docs/ 目录后重试。\n"
            "示例公文类型：请示、报告、通知、函、纪要、批复等"
        )
        return

    total_chars = sum(d.metadata.get("total_chars", 0) for d in documents)
    logger.info(f"  加载完成：{len(documents)} 个文档，共 {total_chars} 字符")

    # ========================================
    # Step 2: 语义分块
    # ========================================
    logger.info("\n[Step 2/3] 执行结构感知分块...")
    logger.info(f"  分块参数：chunk_size={settings.CHUNK_SIZE}, "
                 f"overlap={settings.CHUNK_OVERLAP}")

    chunks = split_gongwen_documents(
        documents,
        chunk_size=settings.CHUNK_SIZE,
        chunk_overlap=settings.CHUNK_OVERLAP,
    )

    if not chunks:
        logger.error("分块结果为空！请检查文档内容。")
        return

    avg_chunk_len = sum(c.metadata["char_count"] for c in chunks) / len(chunks)
    logger.info(f"  分块完成：{len(chunks)} 个语义块，"
                 f"平均 {avg_chunk_len:.0f} 字符/块")

    # ========================================
    # Step 3: 向量化 & 存储
    # ========================================
    logger.info("\n[Step 3/3] 向量化并存入 Chroma...")
    logger.info(f"  Embedding 模型：{settings.EMBEDDING_MODEL_NAME}")
    logger.info(f"  向量库路径：{settings.VECTOR_DB_DIR}")

    vector_store = build_vector_store(chunks, persist_dir=settings.VECTOR_DB_DIR)

    # ========================================
    # 输出构建统计
    # ========================================
    elapsed = time.time() - start_time
    logger.info("\n" + "=" * 60)
    logger.info("  知识库构建完成！")
    logger.info(f"  总耗时：{elapsed:.1f} 秒")
    logger.info(f"  源文档：{len(documents)} 个 .docx 文件")
    logger.info(f"  语义块：{len(chunks)} 个")
    logger.info(f"  向量库：{settings.VECTOR_DB_DIR}")
    logger.info("=" * 60)
    logger.info("\n下一步：运行 pytest 或启动 API（python scripts/run_api.py）验证检索效果")


if __name__ == "__main__":
    main()
