"""
============================================================
应用启动中心（≈ Spring Boot @SpringBootApplication + ApplicationContext）
============================================================
create_app() 是整个应用唯一的组装点：注册中间件、挂载各路由、配置生命周期。
这一个函数回答了"这个应用是什么、由哪些东西组成"——想改装配，只看这里。

分层：
    Controller(api/routes) → Service(services) → Repository(repositories) → 领域(agent/ingestion)
    依赖装配在 api/deps.py（≈ @Configuration）

生命周期：
    lifespan 启动段  预热 RAG 链 + 编译 Agent 图（≈ ApplicationRunner / @PostConstruct）
    lifespan 关闭段  释放 OA 客户端连接（≈ @PreDestroy / DisposableBean）

启动：
    python scripts/run_api.py         # 开发（热重载）
    python scripts/run_api.py --prod  # 生产
    uvicorn src.api.app:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.middleware import register_middleware
from src.api.routes import system, generate, agent, oa
from src.infra.logger import get_logger

logger = get_logger(__name__)


_DESCRIPTION = """
## 功能说明

基于 RAG（检索增强生成）的智能公文写作助手。

1. **公文生成**：输入简短提示，自动生成符合党政机关公文格式的完整正文。
2. **致远 OA 对接**：将生成的公文推送到致远互联 OA 系统的公文表单中。

## 支持的公文体裁

请示 | 报告 | 通知 | 函 | 纪要 | 决定 | 通报 | 批复 | 公告 | 意见

## 技术栈

- **LLM**：DeepSeek Chat（可切换为任何 OpenAI 兼容接口的大模型）
- **RAG**：LangChain LCEL + Chroma 向量库
- **Embedding**：BAAI/bge-small-zh-v1.5（本地模型）
- **框架**：FastAPI + Pydantic v2
- **架构**：Controller → Service → Repository 分层 + Depends 依赖注入
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时预热依赖，关闭时释放资源。"""
    # ===== 启动段（≈ ApplicationRunner / @PostConstruct）=====
    from src.api.deps import get_rag_chain
    from src.domain.graph.build import get_agent_graph

    logger.info("应用启动：预热依赖（RAG 链 / Agent 图）...")
    try:
        get_rag_chain()
        logger.info("  ✓ RAG 链预热完成")
    except Exception as e:
        logger.warning(f"  ! RAG 链预热跳过（知识库可能未构建）：{e}")
    try:
        await get_agent_graph()
        logger.info("  ✓ Agent 图编译完成")
    except Exception as e:
        logger.warning(f"  ! Agent 图预热跳过：{e}")

    yield

    # ===== 关闭段（≈ @PreDestroy / DisposableBean）=====
    from src.api.deps import get_oa_client
    try:
        get_oa_client().close()
    except Exception:
        pass
    logger.info("应用已关闭，资源已释放")


def create_app() -> FastAPI:
    """组装并返回 FastAPI 应用（唯一装配入口）。"""
    app = FastAPI(
        title="致远 OA 公文 Agent",
        description=_DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # ---- 横切关注点（CORS / 请求追踪 / 限流）----
    register_middleware(app)

    # ---- 挂载路由（Controller 层）----
    app.include_router(system.router)
    app.include_router(generate.router)
    app.include_router(agent.router)
    app.include_router(oa.router)

    logger.info("FastAPI 应用已装配：controller → service → repository")
    return app


# 全局唯一实例（供 uvicorn "src.api.app:app" 引用）
app = create_app()
