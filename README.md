# 致远 OA 智能公文 Agent

基于 **RAG（检索增强生成）+ Agent** 的党政机关公文智能写作助手。输入一句简短提示，自动检索历史范文、生成符合《党政机关公文格式》(GB/T 9704-2012) 的完整公文，并可一键推送到致远互联 OA 系统。

## 核心特性

- **双生成模式**
  - **快速模式**（`/generate/stream`）：检索 → 一次生成 → SSE 流式返回，约 3 秒出稿。
  - **深度模式**（`/generate/agent/stream`）：检索 → 撰写 → 逐项格式自查 → 定向修复 → 循环收敛，多轮推理，质量更高；支持 `ask_user` 中途向用户澄清。
- **本地 RAG**：LangChain LCEL + Chroma 向量库 + BAAI/bge-small-zh-v1.5 本地 Embedding（免费、离线）。
- **结构感知分块**：识别公文的标题/主送/正文/落款结构，在语义边界处切分。
- **格式化导出**：生成符合 GB/T 9704-2012 的 `.docx`（字体、字号、页边距、行距、落款右对齐）。
- **致远 OA 对接**：`/oa/forward` 推送公文到 OA 公文表单（`src/api/oa_client.py` 为骨架，需按实际 OA 版本补全接口）。
- **工程化**：pydantic-settings 配置校验、请求追踪（X-Request-ID）、滑动窗口限流、token 用量统计、LLM 调用重试。

## 技术栈

| 层 | 技术 |
|----|------|
| LLM | DeepSeek Chat（任意 OpenAI 兼容接口皆可） |
| RAG | LangChain LCEL + Chroma |
| Embedding | BAAI/bge-small-zh-v1.5（本地，可切远程 API） |
| 后端 | FastAPI + Uvicorn + Pydantic v2 |
| 前端 | Vue + Pinia + Ant Design Vue |
| 部署 | Docker + Nginx |

## 目录结构

```
config/          全局配置（settings.py）与 Prompt 模板
src/
  agent/         RAG 链、Agent 执行器、工具集、检索器、Prompt
  api/           FastAPI 服务、OA 客户端、Pydantic schemas
  ingestion/     文档加载、结构感知分块、向量化入库
  utils/         docx 生成、日志、公共辅助
scripts/         启动入口、知识库构建、模型下载、样例生成
frontend/        Vue 前端
deploy/          Dockerfile、docker-compose、nginx 配置
tests/           pytest 单元测试
data/            范文(raw_docs)、向量库(vector_db)、输出(output) —— 不入库
```

## 快速开始（本地开发）

**前置**：Python 3.13、Node.js 18+

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 配置环境变量：复制示例并填入真实 API Key
cp deploy/.env.example .env.dev
#   编辑 .env.dev，设置 LLM_API_KEY=sk-你的DeepSeek密钥

# 3. 放入范文并构建知识库（首次会自动下载 Embedding 模型）
#    把 .docx 范文放进 data/raw_docs/ 后：
python scripts/run_api.py --build-kb

# 4. 启动后端（开发模式，热重载）
python scripts/run_api.py
#    Swagger 文档: http://localhost:8000/docs

# 5. 启动前端
cd frontend
npm install
npm run serve        # http://localhost:8081
```

> ⚠️ `.env` / `.env.dev` 含 API Key，已被 `.gitignore` 忽略，**切勿提交到仓库**。

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/health` | 健康检查（`?check_llm=true` 额外探活 LLM） |
| POST | `/generate` | 同步生成公文 |
| POST | `/generate/stream` | 快速模式（SSE 流式） |
| POST | `/generate/agent/stream` | 深度模式 Agent（SSE 流式） |
| POST | `/generate/agent/answer` | 向等待中的 Agent 注入用户回答 |
| POST | `/oa/forward` | 推送公文到致远 OA |
| GET  | `/download/{filename}` | 下载生成的 .docx |
| GET  | `/stats` | token 用量统计 |

## Docker 部署

```bash
cd deploy
cp .env.example .env          # 填入生产配置
docker compose build
docker compose up -d          # 前端经 Nginx 暴露在 8081
docker compose logs -f
```

镜像构建时会预下载 Embedding 模型（从 ModelScope，无需科学上网）。数据通过 named volume 持久化。

## 测试

```bash
pytest                        # 全部单元测试（已 mock LLM，不消耗额度）
```

## 依赖版本锁定（建议）

`requirements.txt` 使用兼容区间（`>=x,<y`）便于升级。生产部署建议锁定确切版本以保证可复现：

```bash
pip freeze > requirements.lock.txt
# 部署时：pip install -r requirements.lock.txt
```

## 配置说明

所有配置项见 [`config/settings.py`](config/settings.py) 与 [`deploy/.env.example`](deploy/.env.example)，关键项：

- `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL_NAME`：LLM 接入。
- `EMBEDDING_TYPE`：`local`（本地 BGE，默认）或 `api`（远程）。
- `CHUNK_SIZE` / `CHUNK_OVERLAP` / `RETRIEVER_K`：RAG 分块与检索参数。
- `CORS_ORIGINS`：允许的跨域来源，逗号分隔。**需携带 Cookie 跨域时必须显式列出前端域名，不能用 `*`。**
- `RATE_LIMIT_*`：限流规则。
- `SEEYON_OA_*`：致远 OA 对接（可后续填入）。
