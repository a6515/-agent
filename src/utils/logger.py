"""
============================================================
统一日志配置
============================================================
提供带颜色的控制台输出和可选的本地文件落盘，
方便调试知识库构建过程和线上排查问题。

支持 request_id 上下文变量（contextvars），
可在日志中自动附带请求 ID 用于链路追踪。
"""

import logging
import sys
from contextvars import ContextVar
from pathlib import Path

# ---- 请求级上下文（用于链路追踪）----
_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(rid: str) -> None:
    """设置当前请求的追踪 ID。"""
    _request_id.set(rid)


def get_request_id() -> str:
    """获取当前请求的追踪 ID。"""
    return _request_id.get()


class _RequestIDFilter(logging.Filter):
    """将 request_id 注入到每条日志记录中。"""

    def filter(self, record):
        record.request_id = _request_id.get()
        return True


# 日志格式：时间 | 级别 | [请求ID] | 模块:行号 → 消息
_LOG_FMT = (
    "%(asctime)s | %(levelname)-7s | [%(request_id)s] | "
    "%(name)s:%(lineno)d → %(message)s"
)
_LOG_DATE_FMT = "%m-%d %H:%M:%S"

# 全局初始化标志，确保 handler 只添加一次
_initialized = False


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    获取一个配置好的 logger 实例。

    Args:
        name:  通常传 __name__，用于标识日志来源模块。
        level: 日志级别，默认 INFO。

    Returns:
        logging.Logger 实例。
    """
    global _initialized

    logger = logging.getLogger(name)

    # ---- 避免重复添加 handler ----
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # ---- 控制台 handler ----
    # 在 Windows 上强制 UTF-8 编码，避免 GBK 编码错误
    console = logging.StreamHandler(
        open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
        if hasattr(sys.stdout, 'fileno') else sys.stdout
    )
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_LOG_FMT, datefmt=_LOG_DATE_FMT))
    console.addFilter(_RequestIDFilter())
    logger.addHandler(console)

    # 禁止向上传播，防止日志重复打印
    logger.propagate = False

    return logger


# 快捷获取项目根 logger
root_logger = get_logger("oa-agent")
