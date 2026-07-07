"""
============================================================
【运行入口】启动 FastAPI 服务 / 构建知识库
============================================================
使用方式：
    # 开发模式（代码改动自动重启）
    cd D:/python-projects/oa-agent
    python scripts/run_api.py

    # 生产模式（禁用热重载，日志更简洁）
    python scripts/run_api.py --prod

    # 重建知识库（换范文后运行）
    python scripts/run_api.py --build-kb

    # PyInstaller 打包后
    oa-agent.exe                  # 启动服务
    oa-agent.exe --build-kb       # 重建知识库

启动后访问：
    Swagger 文档：    http://localhost:8000/docs
    健康检查：        http://localhost:8000/health
    生成公文（POST）：http://localhost:8000/generate

前端由 Nginx / OpenResty 托管，开发时单独启动：
    cd frontend && npm run serve
"""

import sys
import os
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

import uvicorn
from config.settings import settings
from src.infra.logger import get_logger

logger = get_logger(__name__)


def _run_build_kb():
    """重建知识库（供 --build-kb 参数调用）。"""
    import time
    from src.domain.ingestion.doc_loader import load_gongwen_documents
    from src.domain.ingestion.text_splitter import split_gongwen_documents
    from src.domain.ingestion.embed_store import build_vector_store

    logger.info("=" * 60)
    logger.info("  知识库重建工具")
    logger.info("=" * 60)

    start = time.time()

    # Step 1: 加载
    logger.info(f"\n[1/3] 扫描 {settings.RAW_DOCS_DIR}")
    docs = load_gongwen_documents(settings.RAW_DOCS_DIR)
    if not docs:
        logger.error("未找到任何 .docx 文件！请将范文放入 data/raw_docs/")
        return
    total_chars = sum(d.metadata.get("total_chars", 0) for d in docs)
    logger.info(f"  加载完成：{len(docs)} 个文档，{total_chars} 字符")

    # Step 2: 分块
    logger.info(f"\n[2/3] 分块（chunk_size={settings.CHUNK_SIZE}, overlap={settings.CHUNK_OVERLAP}）")
    chunks = split_gongwen_documents(docs, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    avg_len = sum(c.metadata["char_count"] for c in chunks) / len(chunks)
    logger.info(f"  分块完成：{len(chunks)} 个语义块，平均 {avg_len:.0f} 字符")

    # Step 3: 向量化
    logger.info(f"\n[3/3] 向量化 -> Chroma（模型：{settings.LOCAL_EMBEDDING_MODEL}）")
    _ = build_vector_store(chunks, persist_dir=settings.VECTOR_DB_DIR)

    elapsed = time.time() - start
    logger.info(f"\n知识库构建完成！耗时 {elapsed:.1f}s，共 {len(chunks)} 条向量 -> {settings.VECTOR_DB_DIR}")


def main():
    # ---- 命令行参数 ----
    if "--build-kb" in sys.argv:
        _run_build_kb()
        return

    is_prod = "--prod" in sys.argv
    is_frozen = getattr(sys, 'frozen', False)

    if is_prod or is_frozen:
        reload = False
        log_level = "warning"
        mode_label = "PyInstaller 打包模式" if is_frozen else "生产模式"
    else:
        reload = True
        log_level = "info"
        mode_label = "开发模式"

    logger.info("=" * 60)
    logger.info(f"  致远 OA 公文 Agent - API 服务（{mode_label}）")
    logger.info("=" * 60)
    logger.info(f"  LLM 模型：{settings.LLM_MODEL_NAME}")
    logger.info(f"  向量库路径：{settings.VECTOR_DB_DIR}")
    logger.info(f"  API 地址：http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"  API 文档：http://localhost:{settings.API_PORT}/docs")
    logger.info(f"  热重载：{'开' if reload else '关'}")
    logger.info(f"  OA 已配置：{'是' if settings.SEEYON_OA_BASE_URL else '否（需填入 .env）'}")
    logger.info("=" * 60)

    if is_frozen:
        # PyInstaller 打包后：直接传 app 对象（避免 importlib 解析问题）
        from src.api.app import app
        uvicorn.run(
            app,
            host=settings.API_HOST,
            port=settings.API_PORT,
            reload=False,
            log_level=log_level,
        )
    else:
        uvicorn.run(
            "src.api.app:app",
            host=settings.API_HOST,
            port=settings.API_PORT,
            reload=reload,
            log_level=log_level,
        )


if __name__ == "__main__":
    main()
