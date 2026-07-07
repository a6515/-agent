"""
============================================================
运行统计服务（Service 层）
============================================================
封装 LLM token 用量的读取。底层跟踪器（agent_shared._token_tracker）由
Agent 节点写入，这里只做只读快照。
"""

from src.domain.agent_shared import get_token_stats
from src.infra.logger import get_logger

logger = get_logger(__name__)


class StatsService:
    """服务运行统计（token 用量等非敏感信息）。"""

    def snapshot(self) -> dict:
        return {
            "status": "ok",
            "token_usage": get_token_stats(),
        }
