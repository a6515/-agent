"""
============================================================
API 中间件（Controller 层横切关注点，≈ Spring Interceptor / AOP）
============================================================
- CORS：从环境变量读取允许来源
- 请求追踪：注入 / 回写 X-Request-ID
- 速率限制：滑动窗口内存实现（单进程；多副本需换 Redis 版）

register_middleware(app) 由启动中心 app.py 调用，注册顺序与重构前一致。
"""

import time
import uuid
import threading
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from src.infra.logger import get_logger, set_request_id

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
# 注册入口
# ============================================================

def register_middleware(app: FastAPI) -> None:
    """把 CORS、请求追踪、速率限制注册到应用（顺序与重构前一致）。"""

    # ---- CORS 中间件 ----
    cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    # 浏览器规范：allow_origins=["*"] 与 allow_credentials=True 不能共存
    allow_credentials = "*" not in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    logger.info(f"CORS 允许来源：{cors_origins}（allow_credentials={allow_credentials}）")

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
