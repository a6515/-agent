"""
============================================================
FastAPI 服务 — 公文 Agent API
============================================================
提供 4 个核心端点：
  GET  /health           — 健康检查
  POST /generate          — 同步生成公文
  POST /generate/stream   — 流式生成公文（SSE）
  POST /oa/forward        — 推送公文到致远 OA

启动方式：
    uvicorn src.api.server:app --host 0.0.0.0 --port 8000 --reload
    或
    python scripts/run_api.py

Swagger 文档：
    启动后访问 http://localhost:8000/docs
"""

import json
import re
import sys
import uuid
import time
import threading
from collections import defaultdict, deque

from pathlib import Path as FilePath

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse

from fastapi.middleware.cors import CORSMiddleware
from config.settings import settings
from src.agent.rag_chain import build_rag_chain, detect_doc_type
from src.utils.docx_writer import save_gongwen_to_docx
from src.api.schemas import (
    GenerateRequest,
    GenerateResponse,
    OAForwardRequest,
    OAForwardResponse,
    HealthResponse,
    AgentAnswerRequest,
)
from src.api.oa_client import (
    oa_client,
    SeeyonOANotConfiguredError,
    SeeyonOAApiError,
    SeeyonOAAuthError,
)
from src.utils.helpers import extract_title_from_content
from src.utils.logger import get_logger, set_request_id

logger = get_logger(__name__)


# ============================================================
# 简易速率限制器（滑动窗口，内存实现）
# ============================================================

class RateLimiter:
    """
    基于滑动窗口的速率限制器。

    设计要点：
      - 纯内存实现，无外部依赖，适合单机部署
      - 多 Docker 副本场景需替换为 Redis 版本
      - 用 client_ip 作为 key（生产环境建议加上 X-Forwarded-For 处理）
    """

    def __init__(self):
        self._windows: dict = defaultdict(deque)  # key → deque[timestamps]
        self._lock = threading.Lock()
        self._call_count = 0  # 轻量计数器，用于触发定期清理

    def _parse_limit(self, limit_str: str) -> tuple:
        """解析 "10/minute" → (10, 60)"""
        parts = limit_str.strip().split("/")
        if len(parts) != 2:
            return (10, 60)
        count = int(parts[0])
        unit = parts[1].lower()
        multipliers = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
        window = multipliers.get(unit, 60)
        return (count, window)

    def is_allowed(self, key: str, limit_str: str) -> bool:
        """检查 key 是否在限制内。返回 True 表示放行。"""
        max_req, window_sec = self._parse_limit(limit_str)
        now = time.time()
        cutoff = now - window_sec

        with self._lock:
            timestamps = self._windows[key]
            # 清理过期记录（deque.popleft 是 O(1)，优于 list.pop(0) 的 O(n)）
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if len(timestamps) >= max_req:
                return False
            timestamps.append(now)

            # 定期清理过期 key（每 1000 次调用触发一次）
            self._call_count += 1
            if self._call_count % 1000 == 0:
                expired_keys = [
                    k for k, ts_list in self._windows.items()
                    if not ts_list or ts_list[-1] < cutoff
                ]
                for k in expired_keys:
                    del self._windows[k]

            return True


_rate_limiter = RateLimiter()


def _get_client_ip(request: Request) -> str:
    """获取客户端 IP（考虑反向代理）。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ============================================================
# FastAPI 应用初始化
# ============================================================

app = FastAPI(
    title="致远 OA 公文 Agent",
    description="""
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
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ---- CORS 中间件（从环境变量读取允许的来源）----
_cors_origins = [
    o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()
]
# 浏览器规范：allow_origins=["*"] 与 allow_credentials=True 不能共存
# （携带 Cookie 的跨域请求会被浏览器拒绝）。配通配符时关闭凭证；
# 若前端需要带 Cookie 跨域，请在 .env 的 CORS_ORIGINS 显式列出前端域名。
_allow_credentials = "*" not in _cors_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info(f"CORS 允许来源：{_cors_origins}（allow_credentials={_allow_credentials}）")


# ---- 请求追踪中间件（注入 request_id 到日志上下文）----
@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


# ---- 速率限制中间件 ----
@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    # 只限制生成类端点
    path = request.url.path
    if path == "/generate":
        limit = settings.RATE_LIMIT_GENERATE
    elif path == "/generate/agent/stream":
        limit = settings.RATE_LIMIT_AGENT
    else:
        return await call_next(request)

    client_ip = _get_client_ip(request)
    if not _rate_limiter.is_allowed(client_ip, limit):
        logger.warning(f"速率限制触发：{client_ip} → {path}")
        raise HTTPException(
            status_code=429,
            detail=f"请求过于频繁，当前限制：{limit}。请稍后重试。",
        )

    return await call_next(request)


# ============================================================
# 全局资源（应用启动时加载一次）
# ============================================================

_rag_chain = None  # 延迟初始化，避免首次启动过慢


def _get_chain():
    """获取或初始化 RAG 链（懒加载 + 单例）。"""
    global _rag_chain
    if _rag_chain is None:
        logger.info("正在初始化 RAG 链...")
        _rag_chain = build_rag_chain(k=settings.RETRIEVER_K)
    return _rag_chain


# ============================================================
# 工具函数
# ============================================================



# ============================================================
# API 端点
# ============================================================

@app.get("/health", response_model=HealthResponse)
async def health_check(check_llm: bool = False):
    """
    服务健康检查。

    可用于：
      - Kubernetes/Docker 健康探针
      - 监控告警检查
      - 排查 LLM/向量库/OA 连接问题

    参数：
      - check_llm: 设为 true 时还会验证 LLM API Key 是否可用（消耗少量 token）。
    """
    try:
        chain = _get_chain()
        vector_db_ok = chain.retriever.is_ready
    except Exception:
        vector_db_ok = False

    # ---- 可选 LLM 探活（仅在明确请求时执行）----
    llm_ok = None
    if check_llm:
        try:
            from langchain_openai import ChatOpenAI
            probe_llm = ChatOpenAI(
                model=settings.LLM_MODEL_NAME,
                base_url=settings.LLM_BASE_URL,
                api_key=settings.LLM_API_KEY,
                temperature=0,
                max_tokens=1,
            )
            probe_llm.invoke("ping")
            llm_ok = True
        except Exception as e:
            logger.warning(f"LLM 探活失败：{e}")
            llm_ok = False

    return HealthResponse(
        status="ok",
        version="1.0.0",
        llm_model=settings.LLM_MODEL_NAME,
        vector_db_ready=vector_db_ok,
        oa_configured=oa_client.is_configured,
        llm_ok=llm_ok,
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate_document(req: GenerateRequest):
    """
    同步生成公文正文。

    流程：
      1. 接收用户简短提示（prompt）
      2. 自动识别或使用指定的公文文种
      3. 从向量库检索相关范文
      4. LLM 生成符合格式的公文正文
      5. 返回生成结果（含标题、正文、来源等元数据）

    请求示例：
    ```json
    {
        "prompt": "写一份申请购买 3 台服务器的请示",
        "doc_type": "请示",
        "retrieve_k": 4,
        "temperature": 0.3
    }
    ```
    """
    try:
        chain = _get_chain()

        # ---- 公文类型识别 ----
        doc_type = req.doc_type.value if req.doc_type else detect_doc_type(req.prompt)
        logger.info(f"API 请求：prompt='{req.prompt[:50]}...' → {doc_type}")

        # ---- 异步生成（doc_type 透传，链内不再重复检测；不阻塞事件循环）----
        content = await chain.ainvoke(req.prompt, doc_type=doc_type)

        # ---- 提取标题 ----
        title = extract_title_from_content(content)

        # ---- 保存为 .docx 文件 ----
        try:
            docx_path = str(save_gongwen_to_docx(content, title=title))
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
    except Exception as e:
        logger.error(f"生成失败：{e}")
        return GenerateResponse(
            success=False,
            title="",
            content="",
            doc_type="",
            char_count=0,
            error=str(e),
        )


@app.get("/stats")
async def get_stats():
    """
    获取服务运行统计（非敏感信息）。

    返回：LLM 调用次数、token 用量等。
    """
    from src.agent.agent_shared import get_token_stats as _agent_stats
    return {
        "status": "ok",
        "token_usage": _agent_stats(),
    }


@app.post("/generate/stream")
async def generate_stream(req: GenerateRequest):
    """
    流式生成公文正文（Server-Sent Events）。

    适用场景：
      - 前端需要实时显示打字效果
      - 长公文生成过程中让用户看到进度
      - WebSocket/SSE 推送

    事件格式（SSE）：
    ```
    event: token
    data: {"token": "关于", "done": false, "doc_type": "请示"}

    event: token
    data: {"token": "申请", "done": false}

    ...

    event: done
    data: {"token": "", "done": true}
    ```

    前端使用示例（JavaScript）：
    ```js
    const evtSource = new EventSource('/generate/stream');
    evtSource.addEventListener('token', (e) => {
        const { token, done } = JSON.parse(e.data);
        if (!done) outputEl.textContent += token;
    });
    ```
    """
    try:
        chain = _get_chain()
        doc_type = req.doc_type.value if req.doc_type else detect_doc_type(req.prompt)
        logger.info(f"API 流式请求：prompt='{req.prompt[:50]}...' → {doc_type}")

        async def event_generator():
            """SSE event generator - manual formatting to bypass sse-starlette serialization issues."""
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

                # Done event with docx_path
                full_content = "".join(full_content_parts)
                title = extract_title_from_content(full_content)
                docx_path = None
                try:
                    docx_path = str(save_gongwen_to_docx(full_content, title=title))
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

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    except Exception as e:
        logger.error(f"流式接口初始化失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _agent_stream_langgraph(req: GenerateRequest):
    """
    LangGraph 引擎：原生 async 流，无需 ThreadPool+Queue 桥接。
    产出与 legacy 完全相同的 7 类 SSE 事件；拦截 done 事件存 docx（与 legacy 一致）。
    """
    from src.agent.graph.sse_adapter import run_graph_agent_stream

    session_id = uuid.uuid4().hex[:12]
    doc_type = req.doc_type.value if req.doc_type else None
    history = req.messages if getattr(req, "messages", None) else None
    current_draft = req.current_draft if getattr(req, "current_draft", None) else None

    async def event_generator():
        try:
            async for ev in run_graph_agent_stream(
                req.prompt, doc_type=doc_type, history=history,
                current_draft=current_draft, session_id=session_id,
            ):
                ev_type = ev.get("event", "message")
                ev_data = ev.get("data", {})
                # 拦截 done 存 docx（与 legacy 路径一致）
                if ev_type == "done" and isinstance(ev_data, dict):
                    final_draft = ev_data.get("final_draft", "")
                    if final_draft:
                        title = ev_data.get("title") or extract_title_from_content(final_draft)
                        try:
                            docx_path = str(save_gongwen_to_docx(final_draft, title=title))
                            ev_data["docx_path"] = docx_path
                            ev_data["title"] = title
                            logger.info(f"Agent(LangGraph) 已保存 .docx：{docx_path}")
                        except Exception as e:
                            logger.warning(f"Agent(LangGraph) docx 保存失败：{e}")
                yield f"event: {ev_type}\ndata: {json.dumps(ev_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"LangGraph Agent 流异常：{e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/generate/agent/stream")
async def generate_agent_stream(req: GenerateRequest):
    """
    【Agent 深度模式】多轮推理 + 自查 + 自修（SSE 流式）。

    与 /generate/stream (RAG 快速模式) 的区别：
      - RAG 模式：  检索 → 一次生成 → 流式返回（~3 秒，单轮）
      - Agent 模式：检索 → 生成 → 自查 → 修复 → 再查 → 返回（~15-30 秒，多轮）

    Agent 会：
      1. 自动识别公文类型（或使用指定的 doc_type）
      2. 自动检索范文（search_exemplars）
      3. 撰写初稿
      4. 逐项自查格式（check_format，基于 GB/T 9704-2012）
      5. 发现问题后定向修复（refine_draft）
      6. 循环 4-5 直到通过或达到最大轮数
      7. 输出最终稿 + 修改说明（finish）

    SSE 事件类型：
      - status:     状态消息（"已识别公文类型：请示"）
      - tool_start: 工具开始执行（tool + args）
      - tool_end:   工具执行完成（tool + result）
      - draft:      草稿更新（实时推送到前端正文面板）
      - done:       Agent 完成（final_draft + summary + agent_turns）
      - ask_user:   Agent 需要用户澄清（question）
      - error:      错误信息

    前端使用示例：
    ```js
    const resp = await fetch('/generate/agent/stream', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({prompt: '写一份购买3台服务器的请示'})
    });
    const reader = resp.body.getReader();
    // 按 SSE 协议解析事件流...
    ```
    """
    # 深度模式统一走 LangGraph StateGraph 引擎（interrupt 中断 + SQLite 持久化）
    return await _agent_stream_langgraph(req)


@app.post("/generate/agent/answer")
async def agent_answer(req: AgentAnswerRequest):
    """
    向等待中的 Agent 注入用户回答（ask_user 恢复流程）。

    当深度模式 Agent 通过 ask_user 工具向用户提问时，
    前端收集回答后调用此接口，Agent 将自动继续执行。

    请求示例：
    ```json
    {
        "session_id": "a1b2c3d4",
        "answer": "申请部门为信息技术部"
    }
    ```
    """
    from src.agent.graph.sse_adapter import submit_answer
    success = submit_answer(req.session_id, req.answer)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {req.session_id} 不存在或已过期。"
                     f"可能是 Agent 已结束运行或超时。",
        )
    logger.info(f"Agent 会话 {req.session_id} 收到用户回答：{req.answer[:80]}...")
    return {"success": True, "message": "回答已提交，Agent 继续执行中"}


@app.post("/oa/forward", response_model=OAForwardResponse)
async def forward_to_oa(req: OAForwardRequest):
    """
    推送公文到致远 OA 系统。

    此接口接收已生成的公文内容，调用致远 OA API 将其
    创建为 OA 系统中的公文单据。

    前置条件：
      - .env 中已配置 SEEYON_OA_BASE_URL / SEEYON_OA_API_TOKEN
      - 致远 OA 服务可访问
      - OA 表单模板 ID 已配置（SEEYON_OA_FORM_ID）

    请求示例：
    ```json
    {
        "title": "关于申请购置办公服务器的请示",
        "content": "为保障公司业务系统稳定运行……",
        "doc_type": "请示",
        "secret_level": "普通",
        "urgency": "普通",
        "creator_id": "zhangsan",
        "department": "信息技术部",
        "form_data": {"经费预算": "480000", "设备数量": "3"}
    }
    ```
    """
    try:
        logger.info(f"OA 推送请求：title='{req.title}'")

        # ---- 调用 OA 客户端创建公文 ----
        result = oa_client.create_document(
            title=req.title,
            content=req.content,
            doc_type=req.doc_type.value,
            secret_level=req.secret_level or "普通",
            urgency=req.urgency or "普通",
            creator_id=req.creator_id,
            department=req.department,
            form_data=req.form_data or {},
        )

        # ---- 构造响应 ----
        return OAForwardResponse(
            success=True,
            oa_doc_id=str(result.get("id", result.get("docId", ""))),
            oa_status=result.get("status", result.get("state", "unknown")),
            message=result.get("message", "公文已成功推送至致远 OA"),
        )

    except SeeyonOANotConfiguredError as e:
        logger.warning(f"OA 未配置：{e}")
        # 返回 success=false 而非抛 500，方便前端展示友好的配置引导
        return OAForwardResponse(
            success=False,
            message=(
                "致远 OA 尚未配置。请在 .env 中设置以下变量：\n"
                f"  SEEYON_OA_BASE_URL=http://your-oa-server.com\n"
                f"  SEEYON_OA_API_TOKEN=your-token\n"
                f"  SEEYON_OA_FORM_ID=your-form-template-id\n\n"
                f"参考前端源码：D:\\vue-projects\\apps-edoc-front\n"
                f"参考后端源码：E:\\Seeyon\\A8"
            ),
        )

    except SeeyonOAAuthError as e:
        logger.error(f"OA 认证失败：{e}")
        return OAForwardResponse(
            success=False,
            message=f"致远 OA 认证失败，请检查 API Token 是否正确：{e}",
        )

    except SeeyonOAApiError as e:
        logger.error(f"OA API 错误：{e}")
        return OAForwardResponse(
            success=False,
            message=f"致远 OA 接口调用失败：{e}",
        )

    except Exception as e:
        logger.error(f"OA 推送未知错误：{e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 静态文件下载（供前端获取生成的 .docx）
# ============================================================

# 输出目录 — 统一用 settings 保证与 docx_writer 保存路径一致
_OUTPUT_DIR = settings.DATA_DIR / "output"


@app.get("/download/{filename}")
async def download_docx(filename: str):
    """
    下载生成的 .docx 公文文件。

    前端 AI 智能创作弹窗调用此接口下载生成的 docx 文件。
    URL 示例：GET /download/关于申请购置办公服务器的请示_20260615_102605.docx
    """
    file_path = _OUTPUT_DIR / filename

    # 安全检查：防止路径穿越攻击
    if not file_path.resolve().is_relative_to(_OUTPUT_DIR.resolve()):
        raise HTTPException(status_code=403, detail="禁止的路径")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在：{filename}")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ============================================================
# 前端部署说明
# ============================================================
# 生产环境前端由 Nginx / OpenResty 托管静态文件并反向代理 API，
# 不再由 FastAPI 直接提供前端服务。
# 开发时请单独启动：cd frontend && npm run serve
