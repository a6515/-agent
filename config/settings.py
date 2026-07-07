r"""
============================================================
全局配置模块（pydantic-settings 版本）
============================================================
所有可配置项统一通过环境变量读取，并提供合理的默认值。
自动校验关键字段，防止因配置错误导致运行时崩溃。

路径说明:
  - 开发模式: 所有路径相对于项目根目录，加载 .env.dev
  - Docker 容器: 所有路径相对于 /app，环境变量由 docker-compose 注入
  - PyInstaller 打包后:
      - 只读资源(前端 dist) -> 在 exe 内部 (sys._MEIPASS)
      - 可写数据(vector_db/output/raw_docs) -> exe 同级的 data/ 目录
      - .env 配置文件 -> exe 同级目录
"""

import os
import sys
from pathlib import Path
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---- 判断运行环境 ----
_FROZEN = getattr(sys, 'frozen', False)
_IN_DOCKER = os.path.exists("/.dockerenv") or os.getenv("RUNNING_IN_DOCKER", "") == "1"

if _FROZEN:
    _APP_DIR = Path(sys.executable).parent
    _ENV_FILE = ".env"
elif _IN_DOCKER:
    _APP_DIR = Path("/app")
    _ENV_FILE = ".env"
else:
    _APP_DIR = Path(__file__).resolve().parent.parent
    _ENV_FILE = ".env.dev"


def _resolve_path(raw: str) -> Path:
    """将相对路径解析为基于 _APP_DIR 的绝对路径。"""
    p = Path(raw)
    return p if p.is_absolute() else _APP_DIR / p


class Settings(BaseSettings):
    """
    集中管理的全局配置类。
    使用 pydantic-settings 提供自动校验、类型转换和 Secret 掩码。
    """

    model_config = SettingsConfigDict(
        env_file=str(_APP_DIR / _ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
        case_sensitive=False,
    )

    # ========================
    # 项目路径（跨 dev / PyInstaller 通用）
    # ========================
    PROJECT_ROOT: Path = _APP_DIR
    DATA_DIR: Path = _APP_DIR / "data"
    RAW_DOCS_DIR: Path = Field(
        default_factory=lambda: _resolve_path(
            os.getenv("RAW_DOCS_DIR", "data/raw_docs")
        )
    )
    VECTOR_DB_DIR: Path = Field(
        default_factory=lambda: _resolve_path(
            os.getenv("VECTOR_DB_DIR", "data/vector_db")
        )
    )

    # ========================
    # LLM 配置（OpenAI 兼容接口）
    # ========================
    LLM_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        description="LLM API 地址",
    )
    LLM_API_KEY: str = Field(
        default="sk-placeholder",
        min_length=1,
        description="LLM API 密钥（生产环境必须替换）",
    )
    LLM_MODEL_NAME: str = Field(default="deepseek-chat", description="LLM 模型名")
    LLM_TEMPERATURE: float = Field(
        default=0.3, ge=0.0, le=2.0,
        description="生成温度，低温度让公文更稳定",
    )

    # ========================
    # Embedding 模型配置
    # ========================
    EMBEDDING_TYPE: str = Field(
        default="local",
        description="local（本地免费）/ api（远程）",
    )

    # --- 远程 API 模式 ---
    EMBEDDING_BASE_URL: str = Field(
        default="https://api.deepseek.com/v1",
        description="远程 Embedding API 地址",
    )
    EMBEDDING_API_KEY: str = Field(
        default="sk-placeholder",
        description="远程 Embedding API 密钥",
    )
    EMBEDDING_MODEL_NAME: str = Field(
        default="text-embedding-3-small",
        description="远程 Embedding 模型名",
    )

    # --- 本地模型模式 ---
    LOCAL_EMBEDDING_MODEL: str = Field(
        default="BAAI/bge-small-zh-v1.5",
        description="本地 HuggingFace 模型名",
    )

    # ========================
    # 向量数据库配置
    # ========================
    VECTOR_DB_TYPE: str = Field(
        default="chroma",
        description="chroma / faiss",
    )
    CHROMA_COLLECTION_NAME: str = Field(
        default="oa_official_docs",
        description="Chroma 集合名",
    )

    # ========================
    # 文档分块参数
    # ========================
    CHUNK_SIZE: int = Field(
        default=800, ge=100, le=5000,
        description="每块最大字符数",
    )
    CHUNK_OVERLAP: int = Field(
        default=150, ge=0, le=1000,
        description="相邻块重叠字符数",
    )

    # ========================
    # 检索参数
    # ========================
    RETRIEVER_K: int = Field(
        default=4, ge=1, le=20,
        description="每次检索返回的范文数量",
    )

    # ========================
    # 致远 OA API 配置
    # ========================
    SEEYON_OA_BASE_URL: str = Field(default="", description="致远 OA 服务地址")
    SEEYON_OA_API_TOKEN: str = Field(default="", description="致远 OA API Token")
    SEEYON_OA_FORM_ID: str = Field(default="", description="OA 表单模板 ID")

    # ========================
    # FastAPI 服务配置
    # ========================
    API_HOST: str = Field(default="0.0.0.0", description="监听地址")
    API_PORT: int = Field(default=8000, ge=1, le=65535, description="监听端口")

    # ========================
    # CORS 配置
    # ========================
    CORS_ORIGINS: str = Field(
        default="*",
        description="允许的跨域来源，逗号分隔",
    )

    # ========================
    # 速率限制
    # ========================
    RATE_LIMIT_ENABLED: bool = Field(
        default=True,
        description="是否启用速率限制",
    )
    RATE_LIMIT_GENERATE: str = Field(
        default="10/minute",
        description="快速模式限流规则",
    )
    RATE_LIMIT_AGENT: str = Field(
        default="5/minute",
        description="深度模式限流规则",
    )

    # ========================
    # Token 用量追踪
    # ========================
    TOKEN_TRACKING_ENABLED: bool = Field(
        default=True,
        description="是否统计 LLM token 用量",
    )

    # ========================
    # LLM 重试
    # ========================
    LLM_MAX_RETRIES: int = Field(
        default=2, ge=0, le=5,
        description="LLM 调用失败最大重试次数",
    )
    LLM_RETRY_DELAY: float = Field(
        default=1.0, ge=0.1, le=10.0,
        description="LLM 重试间隔（秒）",
    )

    # ========================
    # 校验
    # ========================

    @field_validator("RAW_DOCS_DIR", "VECTOR_DB_DIR", mode="before")
    @classmethod
    def _resolve_data_paths(cls, v):
        """将相对路径解析为基于 _APP_DIR 的绝对路径（处理 .env 注入的字符串值）。"""
        if isinstance(v, str):
            return _resolve_path(v)
        return v

    @field_validator("API_PORT", mode="before")
    @classmethod
    def _coerce_int(cls, v):
        """兼容环境变量中的字符串类型。"""
        if isinstance(v, str):
            return int(v)
        return v

    @field_validator("LLM_TEMPERATURE", "CHUNK_SIZE", "CHUNK_OVERLAP",
                     "RETRIEVER_K", "LLM_MAX_RETRIES", "LLM_RETRY_DELAY",
                     mode="before")
    @classmethod
    def _coerce_float_int(cls, v):
        if isinstance(v, str):
            try:
                return float(v) if "." in v else int(v)
            except ValueError:
                return v
        return v

    @field_validator("RATE_LIMIT_ENABLED", "TOKEN_TRACKING_ENABLED", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("1", "true", "yes", "on")
        return v

    @model_validator(mode="after")
    def _validate_api_key(self):
        """开发环境下 API Key 为 placeholder 时发出警告。"""
        if self.LLM_API_KEY in ("sk-placeholder", ""):
            import warnings
            warnings.warn(
                "LLM_API_KEY 未配置或为 placeholder！"
                "请在 .env 文件中设置真实的 API Key，否则 LLM 调用将失败。",
                RuntimeWarning,
                stacklevel=2,
            )
        return self


@lru_cache(maxsize=1)
def _load_settings() -> Settings:
    """单例加载配置（lru_cache 保证只初始化一次）。"""
    return Settings()


# ---- 全局单例 ----
settings = _load_settings()
