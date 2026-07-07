# 致远 OA 智能公文 AI Agent — 项目总览

> 版本：2.0.0（分层架构重构）
> 更新日期：2026-07-07

---

## 一、项目简介

本系统是一套**智能公文写作辅助平台**，集成于致远互联（Seeyon）OA 系统生态中。用户输入简短的写作要点，AI 即可生成符合《党政机关公文格式》（GB/T 9704-2012）的正式公文，并支持一键推送到 OA 系统进流程审批。

核心功能：
- 💬 **智能写作**：基于 RAG（检索增强生成），参考历史范文，生成符合国标格式的公文正文
- 🔍 **多轮自查**：Agent 深度模式下，AI 会自动检索范文 → 撰写初稿 → 逐项审查格式 → 修复问题 → 输出终稿
- 📄 **格式渲染**：生成的纯文本按 GB/T 9704-2012 标准渲染为 `.docx` 文件（标题小标宋、正文仿宋、28 磅行距）
- 🔗 **OA 对接**：生成结果可推送到致远 OA 表单，直接发起审批流程

> **v2.0 架构说明**：AI 后端已重构为 **Controller → Service → Repository 分层架构 + 依赖注入（Depends）**，
> 拥有统一的启动中心 `src/api/app.py`。对熟悉 Spring MVC 的同学，可直接按下方「架构分层」表对照理解。

---

## 二、各模块路径速查

| 模块 | 本地路径 | 技术栈 | 说明 |
|---|---|---|---|
| **AI 后端** | `D:\python-projects\oa-agent` | Python 3.13 + FastAPI + LangChain + Chroma | RAG + Agent 公文写作引擎，提供 REST API |
| **AI 前端** | `D:\python-projects\oa-agent\frontend` | Vue 3 + Ant Design Vue + Pinia | 独立 SPA，可独立部署或嵌入 OA 页面 |
| **OA 前端** | `D:\vue-projects\apps-edoc-front` | Vue 2.x / JavaScript | 致远 OA 公文模块前端，含 AI 智能创作弹窗 |
| **OA 后端** | `D:\Java-project\v10.0瑞安源码` | Java 1.8 + Spring MVC + Hibernate | 致远 OA V10.0 插件开发源码 |
| **OA 产品** | `E:\Seeyon\A8` | Tomcat 9 + MySQL + Seeyon A8+ | 致远 OA 安装目录（生产部署环境参考） |

---

## 三、模块详细说明

### 3.1 AI 后端

**路径：** `D:\python-projects\oa-agent`

#### 架构分层（≈ Spring MVC / Spring Boot）

后端采用经典分层架构，每一层职责单一、依赖向下。对照 Spring 概念如下：

| 分层 | 职责 | 目录 / 文件 | Spring 对应 |
|---|---|---|---|
| **启动中心** | 应用组装 + 生命周期 | `src/api/app.py` 的 `create_app()` | `@SpringBootApplication` + `ApplicationContext` |
| **DI 装配** | 依赖注入（谁依赖谁） | `src/api/deps.py` | `@Configuration` / `@Autowired` |
| **Controller** | HTTP 编解码，只调 service | `src/api/routes/` | `@RestController` |
| **横切关注点** | CORS / 请求追踪 / 限流 | `src/api/middleware.py` | `Interceptor` / AOP |
| **Service** | 业务编排 | `src/services/` | `@Service` |
| **Repository** | 外部资源访问 | `src/repositories/` | `@Repository` / Mapper |
| **Domain（领域）** | RAG 管道 + Agent 状态机 | `src/domain/`（含 `ingestion/`） | 领域模型 / 核心逻辑 |
| **DTO** | 请求/响应数据封装 | `src/api/schemas.py` | Entity / DTO / VO |
| **配置** | 集中配置 | `config/settings.py` | `application.yml` + `@ConfigurationProperties` |
| **基础设施** | 日志 / docx 渲染 / 公共辅助 | `src/infra/` | 公共组件 |

> **与 Spring 的关键差异**：Python 没有「组件自动扫描」。新增一个 service 必须在 `deps.py` 里**显式登记**——
> 代价是多写几行，好处是整个依赖图摊在一个文件里，没有「这个 bean 从哪冒出来」的玄学。

#### 目录结构

```
oa-agent/
├── config/
│   ├── settings.py              # 全局配置（pydantic-settings，≈ application.yml）
│   └── prompts/                 # LLM 提示词（YAML，运行时热更新）
│       ├── rag_system.yaml
│       └── agent_system.yaml
├── src/
│   ├── api/                     # ★ Controller 层（HTTP）
│   │   ├── app.py               # ★★ 启动中心 create_app() + lifespan（≈ @SpringBootApplication）
│   │   ├── deps.py              # 依赖装配 Depends providers（≈ @Configuration）
│   │   ├── middleware.py        # CORS / 请求追踪 / 限流（≈ Interceptor）
│   │   ├── routes/              # HTTP 路由（≈ @RestController）
│   │   │   ├── system.py        #   /health  /stats  /download
│   │   │   ├── generate.py      #   /generate  /generate/stream
│   │   │   ├── agent.py         #   /generate/agent/stream  /answer
│   │   │   └── oa.py            #   /oa/forward
│   │   └── schemas.py           # 请求/响应 DTO（Pydantic v2）
│   ├── services/                # ★ Service 层（业务编排，≈ @Service）
│   │   ├── generation_service.py  # 快速模式：识别文种→检索→生成→落盘
│   │   ├── agent_service.py       # 深度模式：LangGraph 事件流 + docx 落盘
│   │   ├── oa_service.py          # OA 推送 + 异常映射
│   │   └── stats_service.py       # token 用量统计
│   ├── repositories/            # ★ Repository 层（外部资源，≈ @Repository/DAO）
│   │   ├── document_repository.py # .docx 落盘 / 下载路径解析（含防穿越）
│   │   └── oa_client.py           # 致远 OA HTTP 客户端（骨架）
│   ├── domain/                 # 领域层：RAG + Agent 核心（原 src/agent/）
│   │   ├── rag_chain.py         #   RAG 管道（LangChain LCEL）+ 文种识别
│   │   ├── retriever.py         #   向量检索器（Chroma 封装）
│   │   ├── graph/              #   LangGraph 深度模式引擎（StateGraph + SQLite 持久化）
│   │   ├── tools.py            #   5 个工具 + function calling schema
│   │   ├── agent_shared.py     #   token 统计 / tool_call 解析等纯逻辑
│   │   ├── agent_prompt.py     #   Agent 系统提示词加载
│   │   ├── prompts.py          #   RAG 系统提示词加载
│   │   └── ingestion/          #   知识库构建（离线管道，原 src/ingestion/）
│   │       ├── doc_loader.py    #     .docx 解析 + 结构分类
│   │       ├── text_splitter.py #     结构感知分块
│   │       └── embed_store.py   #     Embedding + Chroma 管理
│   └── infra/                  # 基础设施（原 src/utils/，≈ 公共组件）
│       ├── docx_writer.py       #   GB/T 9704-2012 标准 docx 渲染
│       ├── helpers.py           #   日期上下文、标题提取等
│       └── logger.py            #   统一日志（request_id 链路追踪）
├── scripts/                     # 入口脚本
│   ├── run_api.py              #   main()：启动 FastAPI（uvicorn src.api.app:app）
│   ├── build_knowledge_base.py #   构建 Chroma 向量库
│   ├── download_model.py       #   预下载本地 Embedding 模型
│   └── generate_samples.py     #   生成样例范文
├── tests/                       # pytest 单元测试（64 用例）
├── deploy/                      # 部署配置
│   ├── Dockerfile              #   后端 Python 镜像
│   ├── Dockerfile.nginx        #   前端 Nginx 镜像（多阶段）
│   ├── docker-compose.yml      #   双容器编排
│   ├── nginx.conf              #   Nginx 前端托管 + API 反代
│   ├── build.ps1               #   Windows 本地构建脚本
│   ├── .env.example            #   环境变量模板
│   └── 部署说明.md
├── frontend/                    # Vue 3 前端（独立 SPA）
└── requirements.txt             # Python 依赖
```

#### 启动中心与请求流转

**启动中心**（相当于 Spring Boot 的启动类）：

```
scripts/run_api.py            ── uvicorn.run("src.api.app:app")        # ≈ public static void main
      └─ src/api/app.py :: create_app()                                # ≈ @SpringBootApplication
            ├─ register_middleware(app)      # CORS / request-id / 限流
            ├─ include_router × 4            # 挂载 Controller
            └─ lifespan
                 ├─ 启动段：预热 RAG 链 + 编译 Agent 图   # ≈ ApplicationRunner / @PostConstruct
                 └─ 关闭段：释放 OA 客户端连接            # ≈ @PreDestroy
```

**一次请求的流转**：

```
HTTP 请求
  → middleware（CORS / X-Request-ID / 限流）
  → api/routes/*.py        Controller：解析请求、返回响应（不含业务逻辑）
  → services/*.py          Service：编排「识别文种 → 检索 → 生成 → 落盘」
  → domain/                Domain：RAG 链（LCEL）/ LangGraph 状态机 / 知识库构建
  → repositories/*.py      Repository：docx 落盘 / OA 推送 / 向量检索
依赖装配：deps.py 用 @lru_cache 提供单例，Controller 通过 Depends(get_xxx_service) 获取
```

#### 核心 API

| 端点 | 方法 | 路由文件 | 说明 |
|---|---|---|---|
| `/health` | GET | routes/system.py | 健康检查（可选 LLM 探活） |
| `/stats` | GET | routes/system.py | Token 用量统计 |
| `/download/{filename}` | GET | routes/system.py | 下载生成的 .docx 文件 |
| `/generate` | POST | routes/generate.py | 快速模式 — 同步生成公文 |
| `/generate/stream` | POST | routes/generate.py | 快速模式 — SSE 流式生成 |
| `/generate/agent/stream` | POST | routes/agent.py | 深度模式 — Agent 多轮推理（SSE） |
| `/generate/agent/answer` | POST | routes/agent.py | 注入用户回答（Ask-User 恢复） |
| `/oa/forward` | POST | routes/oa.py | 推送公文到致远 OA |
| `/docs` · `/redoc` | GET | （FastAPI 内置） | Swagger / ReDoc API 文档 |

#### 技术要点

- **架构**：Controller → Service → Repository 分层，`Depends` 依赖注入，`create_app()` 统一装配，`lifespan` 管理生命周期
- **LLM**：DeepSeek Chat（通过 OpenAI 兼容接口调用，可切换任何兼容模型）
- **Embedding**：BAAI/bge-small-zh-v1.5（本地模型，~100MB，离线运行）
- **向量库**：Chroma（SQLite 持久化，存储于 `data/vector_db/`）
- **检索**：余弦相似度，支持 MMR 和阈值过滤
- **Agent 5 工具**：`search_exemplars` → `check_format` → `refine_draft` → `ask_user` → `finish`
- **深度模式引擎**：LangGraph StateGraph + AsyncSqliteSaver（`interrupt` 中断 + checkpoint 持久化）
- **工程化**：pydantic-settings 配置校验、X-Request-ID 链路追踪、滑动窗口限流、token 用量统计、LLM 调用重试

#### 支持的公文文种

请示 | 报告 | 通知 | 函 | 纪要 | 决定 | 通报 | 批复 | 公告 | 意见

---

### 3.2 AI 前端

**路径：** `D:\python-projects\oa-agent\frontend`

#### 目录结构

```
frontend/
├── public/
│   └── index.html           # HTML 入口
├── src/
│   ├── main.js              # Vue 应用入口
│   ├── App.vue              # 根组件
│   ├── constants/
│   │   └── index.js         # 常量（图标、标签、模板、Agent 阶段定义）
│   ├── services/
│   │   ├── api.js           # HTTP API 封装（fetch）
│   │   └── sse-client.js    # SSE 流解析器（ReadableStream）
│   ├── stores/
│   │   └── ai.js            # Pinia 全局状态（单一 store）
│   ├── views/
│   │   └── AiGenerator.vue  # 主页面（核心编排组件）
│   └── components/
│       ├── layout/          # TopHeader / FooterBar
│       ├── chat/            # ChatPanel / ChatMessageList / ChatInput / ModeTabs / QuickTemplates
│       ├── draft/           # DraftPanel / DraftPlaceholder
│       └── agent/           # AgentProgressBar / AgentActivityCard / AgentAskModal
├── .env.development         # VUE_APP_API_BASE=http://localhost:8000
├── .env.production          # VUE_APP_API_BASE=（空，同源部署）
└── vue.config.js            # Vue CLI 配置（端口 8081）
```

#### 主要功能

1. **快速模式**：用户输入写作要点 → 选模板 → 发送 → 实时看到打字效果（SSE 流）
2. **深度模式**：Agent 6 阶段进度条（分析 → 检索 → 撰写 → 审查 → 修复 → 完成）
3. **实时活动**：Agent 工具调用、格式审查结果实时展示在活动卡片中
4. **Ask-User 交互**：Agent 信息不足时弹出问题，用户回答后继续
5. **操作按钮**：复制正文、下载 .docx、推送到 OA

#### 部署模式

- **开发模式**：`npm run serve`（端口 8081），API 代理到 `localhost:8000`
- **生产模式**：`npm run build` → 静态文件由 Nginx / OpenResty 托管

---

### 3.3 OA 前端（致远公文模块）

**路径：** `D:\vue-projects\apps-edoc-front`

致远 OA 公文模块的前端界面。包含：
- 公文列表、拟稿、签批等常规 OA 功能
- **AI 智能创作弹窗**：用户在 OA 中点击按钮 → 弹出 iframe 加载 AI 前端页面
- 生成完成后通过 `window.postMessage` 将内容回传给 OA 父窗口

与 AI 前端的关系：AI 前端（`frontend/`）是一个独立 SPA，嵌入在 OA 前端的 iframe 弹窗中。

---

### 3.4 Java OA 后端（致远 OA 插件）

**路径：** `D:\Java-project\v10.0瑞安源码`

#### 模块一览

| 模块 | 职责 |
|---|---|
| `apps-api` | 公共 API 接口定义 |
| `apps-customize` | **核心定制模块** — 所有自定义 Java 源码 |
| `apps-doc` | 公文相关控制器 |
| `ctp-core` | CTP 核心框架配置 |
| `ctp-organization` | 组织角色菜单配置 |

#### 核心功能：FileZ（联想文档中台）集成

| 功能 | 实现位置 | 说明 |
|---|---|---|
| 在线编辑 | `EuFileZManagerImpl.java` | 通过 FileZ SDK 打开文档进行在线编辑 |
| 套红（Red Heading） | `EuFileZRedManagerImpl.java`（645 行） | POI 书签预填 + FileZ API 合并，3 种套红路径 |
| PDF 转换 | `EuFileZManagerImpl.java` | 调用 FileZ API 将公文转 PDF |
| 水印 | `WatermarkEvent.java` | 流程流转前自动添加水印 |
| CAP4 表单控件 | `RedFileZCtrl.java` 等 3 个 | 致远 CAP4 低代码平台的自定义控件 |

#### 关键类

| 类 | 行数 | 说明 |
|---|---|---|
| `EuFileZManagerImpl` | 715 | 主管理器：文件下载、套红、PDF、水印 |
| `EuFileZRedManagerImpl` | 645 | POI 书签套红（2026.06 新增） |
| `FileZUtil` | 304 | HTTP 工具：HMAC-SHA256 签名、MD5 认证令牌 |
| `RedFileZCtrl` | 459 | 套红 CAP4 表单控件 |
| `EuFileZController` | - | Spring MVC 控制器：下载、上传、SDK 页面 |

---

### 3.5 OA 产品本体

**路径：** `E:\Seeyon\A8`

致远 OA A8+ 安装目录。目录结构：

```
E:\Seeyon\A8\
├── ApacheJetspeed\           # Tomcat 9 应用服务器
│   └── webapps\
│       └── seeyon\           # OA 主应用（WAR 解包）
│           └── WEB-INF\
│               ├── cfgHome\  # 插件配置（与 apps-customize 结构对应）
│               └── lib\      # Java 库（含 POI 相关 jar）
├── base\                     # 基础数据（配置、文档存储、索引、许可证）
├── inst\                     # 安装器环境
├── jdk\                      # 自带 JDK
├── Logs\                     # 运行日志
└── OfficeTrans\              # Office 文档转换服务
```

---

## 四、系统架构图（逻辑）

```
┌─────────────────────────────────────────────────────────────┐
│                      致远 OA 系统                           │
│  ┌──────────────┐     ┌──────────────┐                     │
│  │ OA 前端       │────▶│ Java OA 后端  │                     │
│  │ (Vue 2.x)    │     │ (Spring MVC) │                     │
│  │ 公文模块      │     │ 插件 + FileZ │                     │
│  └──────┬───────┘     └──────────────┘                     │
│         │ iframe                                               │
│         ▼                                                      │
│  ┌──────────────┐                                              │
│  │ AI 前端       │──── HTTP/SSE ────▶ ┌──────────────────┐     │
│  │ (Vue 3 SPA)  │                    │ AI 后端            │     │
│  │ 智能创作弹窗  │◀─── docx下载 ──── │ Controller       │     │
│  └──────────────┘                    │   → Service      │     │
│                                      │   → Repository   │     │
│                                      │   → RAG/Agent    │     │
│                                      └───────┬────────────┘     │
│                                              │                   │
│                                      ┌───────▼────────────┐     │
│                                      │ DeepSeek API       │     │
│                                      │ (LLM 推理)         │     │
│                                      └────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 五、关键配置项

| 环境变量 | 说明 | 默认值 |
|---|---|---|
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | LLM API 密钥 | `sk-placeholder`（需替换） |
| `LLM_MODEL_NAME` | LLM 模型名 | `deepseek-chat` |
| `EMBEDDING_TYPE` | Embedding 模式 | `local`（本地免费） |
| `LOCAL_EMBEDDING_MODEL` | 本地 Embedding 模型 | `BAAI/bge-small-zh-v1.5` |
| `VECTOR_DB_TYPE` | 向量数据库 | `chroma` |
| `CHUNK_SIZE` | 分块大小（字符） | `800` |
| `RETRIEVER_K` | 检索返回数 | `4` |
| `RATE_LIMIT_GENERATE` | 快速模式限流 | `10/minute` |
| `RATE_LIMIT_AGENT` | 深度模式限流 | `5/minute` |
| `SEEYON_OA_BASE_URL` | 致远 OA 地址 | 空（待配置） |
| `SEEYON_OA_API_TOKEN` | 致远 OA API Token | 空（待配置） |
| `API_PORT` | 服务端口 | `8000` |

完整配置项参见 `config/settings.py`。

---

## 六、开发环境要求

| 工具 | 版本要求 |
|---|---|
| Python | 3.11+（推荐 3.13） |
| Node.js | 18+ |
| Java | JDK 1.8（仅 OA 插件开发） |
| IntelliJ IDEA | 2024+（仅 OA 插件开发） |
| Docker | 20.10+（部署用） |

---

*文档终。*
