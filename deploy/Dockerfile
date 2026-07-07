# ============================================================
# 致远 OA 智能公文 AI Agent — 后端镜像
# ============================================================
# 构建方式：
#   docker build -t oa-agent:latest -f deploy/Dockerfile .
# 或：
#   cd deploy && docker compose build
# ============================================================

FROM python:3.13-slim

LABEL maintainer="oa-agent"
LABEL description="致远 OA 智能公文 AI Agent - 后端 API 服务"
LABEL version="1.0.0"

WORKDIR /app

# ---- 系统依赖 ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        && rm -rf /var/lib/apt/lists/*

# ---- Python 依赖（利用 Docker 层缓存）----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com

# ---- 预下载 Embedding 模型（从 ModelScope，无需科学上网）----
# 使用 download_model.py 脚本，自动处理下载 + sentence-transformers 4.x 兼容性修补
COPY scripts/download_model.py scripts/download_model.py
RUN python scripts/download_model.py \
    --model BAAI/bge-small-zh-v1.5 \
    --output /app/models/bge-small-zh-v1.5

# ---- 复制源码 ----
COPY . .

# ---- 创建运行时数据目录 ----
RUN mkdir -p /app/data/raw_docs /app/data/vector_db /app/data/output

# ---- 容器环境标识（config/settings.py 据此切换路径策略）----
ENV RUNNING_IN_DOCKER=1

# ---- 清理临时文件（减小镜像体积）----
RUN rm -rf scripts/download_model.py && \
    pip cache purge || true

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "scripts/run_api.py", "--prod"]
