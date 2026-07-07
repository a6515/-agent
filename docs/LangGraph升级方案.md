# 项目升级方案：手写 Agent Loop → LangGraph

> 版本：v1
> 作者：升级评估
> 适用项目：致远 OA 智能公文 AI Agent
>
> **✅ 已完成（阶段 0-4 全部落地）**：LangGraph 已成为深度模式唯一引擎，
> 旧的手写循环 `agent_executor.py` 与 `AGENT_ENGINE` feature flag 已移除，
> 共享纯逻辑抽到 `src/agent/agent_shared.py`。以下为迁移过程的历史记录。

---

## 0. 一句话目标

把**深度模式**的手写 `while` 循环（[agent_executor.py](../src/agent/agent_executor.py)）替换为 **LangGraph 的 StateGraph + checkpointer**，在**不改动前端、不改动 SSE 事件契约**的前提下，解决三个硬伤：

1. **ask_user 忙等阻塞线程**（`threading.Event` + `sleep(0.1)` 轮询）
2. **进程重启丢失进行中会话**（状态只在内存 `_SESSION_STORE`）
3. **同步循环 → 异步 SSE 的桥接复杂**（`ThreadPoolExecutor` + `Queue` + 跨线程 cancelled 信号）

保留复用：**5 个工具、检索器、docx 渲染、全部 Prompt、RAG 快速模式**（快速模式不动）。

---

## 1. 硬约束（贯穿全程）

| 约束 | 说明 | 为什么 |
|------|------|--------|
| **SSE 事件契约不变** | 仍然产出 `status / tool_start / tool_end / draft / done / ask_user / error` 七类事件，字段不变 | 前端 [AiGenerator.vue](../frontend/src/views/AiGenerator.vue) 的 `handleAgentEvent` 是按这些事件写死的，契约不变 = 前端零改动 |
| **API 端点不变** | `/generate/agent/stream`、`/generate/agent/answer` 路径与请求体不变 | 前端 [api.js](../frontend/src/services/api.js) 不用改 |
| **新旧并存 + feature flag** | 用环境变量 `AGENT_ENGINE=legacy\|langgraph` 切换 | 任何阶段都能一键回滚到旧实现 |
| **快速模式不动** | LCEL RAG 链（`/generate`、`/generate/stream`）保持原样 | 它本来就没问题，缩小改动面 |

---

## 2. 目标架构

### 2.1 StateGraph 节点图

把现在"靠 Prompt 指令 + loop 里 if/else 隐式驱动"的流程，改成**显式的节点 + 条件边**：

```
                    ┌─────────────┐
   user input ─────▶│  detect     │  识别文种（detect_doc_type）
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
              ┌────▶│  agent      │  调 LLM，决定：调工具 / 出初稿 / 结束
              │     └──────┬──────┘
              │            │ (条件边：看 LLM 返回)
              │      ┌─────┴──────┬───────────┬──────────┐
              │      ▼            ▼           ▼          ▼
              │  ┌────────┐  ┌─────────┐ ┌────────┐ ┌────────┐
              │  │ search │  │ check   │ │ refine │ │ ask_user│ (interrupt)
              │  │exemplars│ │ format  │ │ draft  │ └───┬────┘
              │  └───┬────┘  └────┬────┘ └───┬────┘     │ 用户回答后 resume
              │      └────────────┴──────────┴──────────┘
              │                   │ (回到 agent)
              └───────────────────┘
                           │ finish
                           ▼
                    ┌─────────────┐
                    │  finalize   │  存 docx + done 事件
                    └─────────────┘
```

### 2.2 State 模型

现有的 `AgentState` dataclass（15+ 字段）映射为 LangGraph 的 `TypedDict` State：

```python
class GongwenGraphState(TypedDict):
    messages: Annotated[list, add_messages]   # LangGraph 内置消息累加
    doc_type: str
    draft: str | None
    fix_attempts: dict[str, int]
    searched: bool
    turn_count: int
    # token 统计等
```

关键收益：`messages` 用 `add_messages` reducer 自动累加，不再手动 `state.messages.append()`。

### 2.3 三个硬伤的解法

| 硬伤 | 现在 | LangGraph 方案 |
|------|------|---------------|
| ask_user 忙等 | `threading.Event` + `while sleep(0.1)` 占线程 | `interrupt(question)` — 图暂停并落盘 checkpoint，**不占任何线程**；`/answer` 端点用 `graph.invoke(Command(resume=answer), config)` 恢复 |
| 重启丢会话 | 内存 dict `_SESSION_STORE` | checkpointer 持久化（阶段 1 用 `MemorySaver`，阶段 3 换 `SqliteSaver`），`thread_id=session_id` |
| 异步桥接 | `ThreadPoolExecutor + Queue` | 原生 `async for ev in graph.astream(..., stream_mode="custom")`，直接喂给 SSE |

---

## 3. 分阶段实施计划

> 每个阶段**独立可交付、可回滚**。建议顺序推进，但阶段 1 完成后就已经能替代旧实现。

### 阶段 0 — 脚手架（0.5 天）

- 加依赖：`langgraph>=0.2`、`langgraph-checkpoint-sqlite`（阶段 3 用）
- 新建目录 `src/agent/graph/`，与旧 `agent_executor.py` **并存**
- 加配置项 `AGENT_ENGINE`（默认 `legacy`）到 [settings.py](../config/settings.py)
- **验收**：`AGENT_ENGINE=legacy` 时行为与现在完全一致（等于什么都没变）

### 阶段 1 — 核心图（不含中断）（2~3 天）

- `src/agent/graph/state.py`：定义 `GongwenGraphState`
- `src/agent/graph/nodes.py`：`detect / agent / tools / finalize` 节点（工具函数直接复用 [tools.py](../src/agent/tools.py)）
- `src/agent/graph/build.py`：`StateGraph` 装配 + 条件边
- `src/agent/graph/sse_adapter.py`：把 `graph.astream` 的输出映射成现有 7 类 SSE 事件
- [server.py](../src/api/server.py) 的 `/generate/agent/stream`：按 `AGENT_ENGINE` 分流到新图；新图路径**不再需要** ThreadPool+Queue
- **暂时**：ask_user 先降级为"直接推断/跳过"（阶段 2 再补 interrupt）
- **验收**：`AGENT_ENGINE=langgraph` 下，新建公文全流程跑通，前端 UI 表现（进度条、活动卡片、草稿面板）与旧版**肉眼无差**

### 阶段 2 — human-in-the-loop（ask_user）（1~2 天）

- ask_user 节点改用 `interrupt(question)`
- `/generate/agent/answer` 改用 `graph.astream(Command(resume=answer), config={"configurable": {"thread_id": session_id}})` 恢复
- 删除新路径里的 `waiting_for_user` 忙等逻辑
- **验收**：Agent 提问→前端回答→继续，全程无线程被 sleep 占用；暂停期间服务器 CPU 不空转

### 阶段 3 — 持久化 checkpointer（1 天）

- `MemorySaver` → `SqliteSaver`（落盘到 `data/agent_checkpoints.sqlite`）
- **验收**：Agent 在 ask_user 暂停时**重启后端进程**，前端提交回答仍能续跑（这是旧实现完全做不到的）

### 阶段 4 — 清理与收尾（1 天）

- 稳定运行后，移除旧 `_execute_loop` / ThreadPool 桥接 / `_SESSION_STORE`（或保留 legacy 作为 fallback 一段时间）
- 补充新图的集成测试
- 更新 [部署说明.md](../deploy/部署说明.md)：新增 checkpoint 卷挂载
- **验收**：全部测试通过；前端确认零改动

---

## 4. 配套架构升级（独立于 LangGraph，可并行或后置）

这些不依赖 LangGraph，可单独排期：

| 项 | 工作量 | 价值 |
|----|-------|------|
| **修 Prompt 热更新** | 0.5 天 | 现在 `@lru_cache`+模块级导致改 YAML 不生效，改成按 mtime 重读，或修正文档 |
| **接入 LangSmith tracing** | 0.5 天 | 依赖树已含 langsmith，配环境变量即可 trace 整条链/图 |
| **补集成测试** | 2 天 | agent 图、RAG 链、API 端点端到端；check_format 那类 bug 不再潜伏 |
| **知识库扩充** | 持续 | 现在只有 5 条向量，RAG 效果受限，多灌范文收益最大 |
| **RAG 深化** | 2~3 天 | 混合检索(BM25+向量) + rerank + 多查询改写 |
| **多 worker → Redis** | 2 天 | 限流器/session/checkpoint 抽到 Redis，才能安全多进程横向扩展 |

---

## 5. 工作量与时间线

| 阶段 | 内容 | 估计 |
|------|------|------|
| 0 | 脚手架 | 0.5 天 |
| 1 | 核心图 | 2~3 天 |
| 2 | ask_user interrupt | 1~2 天 |
| 3 | 持久化 checkpointer | 1 天 |
| 4 | 清理收尾 | 1 天 |
| **LangGraph 迁移小计** | | **约 6~8 天** |
| 配套升级（可选） | 见第 4 节 | 另计 |

> 阶段 1 结束（约 3~4 天）即可用新引擎替代旧的，后续阶段是增强。

---

## 6. 风险与回滚

| 风险 | 应对 |
|------|------|
| 新图行为与旧版有细微差异 | `AGENT_ENGINE` feature flag，随时切回 legacy |
| SSE 事件字段漏映射导致前端异常 | 阶段 1 用真实前端逐事件比对；`sse_adapter` 单测覆盖 7 类事件 |
| LangGraph 版本 API 变动 | requirements 锁定 langgraph 小版本 |
| checkpoint 落盘增加磁盘占用 | SqliteSaver 定期清理过期 thread（复用现有 TTL 思路） |

**回滚**：任意阶段出问题，设 `AGENT_ENGINE=legacy` 重启即恢复到当前稳定实现，零数据损失。

---

## 7. 验收 Checklist（全部完成即迁移成功）

- [ ] 快速模式（`/generate/stream`）不受影响
- [ ] 深度模式新建公文：进度条/活动卡片/草稿面板表现与旧版一致
- [ ] check_format 自查-修复闭环正常（第一轮已修，回归确认）
- [ ] ask_user 提问-回答-续跑正常，且暂停期间无线程忙等
- [ ] ask_user 暂停期间重启后端，回答仍能续跑（新能力）
- [ ] 前端代码**零改动**
- [ ] 新增集成测试通过
- [ ] `AGENT_ENGINE=legacy` 仍可一键回滚

---

## 8. 建议的启动方式

先做 **阶段 0 + 阶段 1**（约 3~4 天）产出一个可切换的新引擎，跑通新建公文主流程。用真实前端对比确认"肉眼无差"后，再决定是否继续阶段 2~4。这样**最小风险验证**方向，不会一次性投入 6~8 天才看到结果。
