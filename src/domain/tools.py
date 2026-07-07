"""
============================================================
公文 Agent 工具集
============================================================
每个工具都是一个普通 Python 函数，Agent 通过 function calling 调用。

设计原则：
  - 每个函数职责单一、输入输出明确
  - 工具之间无状态依赖，可以任意顺序调用
  - 返回格式对 LLM 友好（结构化 JSON 或纯文本）
"""

import json
import re
from typing import List, Optional, Dict, Any

from langchain_core.messages import HumanMessage

from src.domain.retriever import GongwenRetriever
from src.infra.logger import get_logger

logger = get_logger(__name__)

# ---- 全局检索器（懒加载单例） ----
_retriever: Optional[GongwenRetriever] = None


def _get_retriever(k: int = 4) -> GongwenRetriever:
    global _retriever
    if _retriever is None:
        _retriever = GongwenRetriever(k=k)
    return _retriever


# ============================================================
# 工具 1：search_exemplars — 检索历史范文
# ============================================================

def search_exemplars(query: str, k: int = 4) -> Dict[str, Any]:
    """
    从历史公文范文库中检索最相关的参考文本。

    调用时机：
      - 收到用户写作请求后，在开始撰写前调用
      - 需要特定风格的范文参考时调用

    Args:
        query: 检索关键词，如"服务器采购请示""安全生产通知"
        k: 返回范文数量，默认 4
    """
    retriever = _get_retriever(k=k)
    docs = retriever.retrieve(query) or []

    exemplars = []
    for doc in docs:
        source = doc.metadata.get("source", "unknown")
        content = doc.page_content[:600]  # 截断，避免 context 爆炸
        exemplars.append({"source": source, "content": content})

    logger.info(f"search_exemplars('{query[:50]}...') → {len(exemplars)} 条")
    return {"total_found": len(exemplars), "exemplars": exemplars}


# ============================================================
# 工具 2：check_format — 格式合规检查
# ============================================================

CHECK_FORMAT_PROMPT = """你是一名公文格式审核专家。
严格对照《党政机关公文格式》(GB/T 9704-2012)，逐项检查以下公文草稿。

## 检查清单

1. **标题格式**：是否居中？是否不以标点结尾？是否包含文种关键词？
2. **主送机关**：是否顶格？是否使用规范化简称？是否以冒号结尾？
3. **正文缩进**：每段首行是否缩进 2 字符？
4. **层次序数**：是否正确？（一、→（一）→ 1. →（1））
5. **结尾用语**：是否匹配文种？
   - 请示 → "妥否，请批示" / "以上请示，请审批"
   - 报告 → "特此报告"
   - 通知 → "特此通知"
   - 函 → "特此函告" / "请予研究函复"
   - 批复 → "此复"
   - 纪要 → 无固定结尾用语
6. **落款**：是否包含发文机关 + 成文日期？日期是否用汉字数字？
7. **语言规范**：是否出现禁止词汇？
   - ❌ "好的" "综上所述" "希望以上内容" "值得注意的是" "作为AI"

## 输出格式

请严格返回以下 JSON 格式（不要输出其他任何内容）：

```json
{
  "issues": [
    {"item": "标题格式", "status": "pass", "detail": ""},
    {"item": "主送机关", "status": "pass", "detail": ""},
    {"item": "正文缩进", "status": "pass", "detail": ""},
    {"item": "层次序数", "status": "pass", "detail": ""},
    {"item": "结尾用语", "status": "pass", "detail": ""},
    {"item": "落款格式", "status": "pass", "detail": ""},
    {"item": "语言规范", "status": "pass", "detail": ""}
  ],
  "critical_count": 0,
  "summary": "全部检查通过"
}
```

其中 status 取值：
- "pass"：通过（该项没有问题）
- "issue"：有问题（必须修复）
- "na"：不适用（该公文类型不需要此项检查）

## 草稿

{draft}

## 公文类型

{doc_type}"""


def check_format(draft: str, doc_type: str, llm) -> Dict[str, Any]:
    """
    审查公文草稿是否符合 GB/T 9704-2012 格式规范。

    调用时机：
      - 每次生成或修改草稿后都应调用
      - 如果返回 issues，应立即调用 refine_draft 修复

    Args:
        draft: 需要审查的公文草稿全文
        doc_type: 文种（请示/报告/通知/函/纪要/决定/批复/通报/公告/意见）
        llm: LLM 实例（用于 LLM-as-judge）
    """
    # 注意：CHECK_FORMAT_PROMPT 内含 JSON 示例（大量花括号），不能用 str.format()，
    # 否则会把 JSON 的 { } 当成替换字段而抛 KeyError。改用精确 replace 注入变量。
    prompt = CHECK_FORMAT_PROMPT.replace("{draft}", draft).replace("{doc_type}", doc_type)

    text = ""  # 预初始化：避免 llm.invoke 抛异常时 except 分支引用未定义变量导致 NameError
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        text = response.content if hasattr(response, "content") else str(response)

        # 提取 JSON（可能被 markdown 代码块包裹）
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if json_match:
            text = json_match.group(1)

        data = json.loads(text)
        critical = [i for i in data.get("issues", []) if i.get("status") == "issue"]
        logger.info(f"check_format() → {len(critical)} 个问题")
        return data

    except Exception as e:
        logger.error(f"check_format 解析失败：{e}，原始返回：{text[:200]}")
        # 降级：返回一个「全部待人工审核」的结果
        return {
            "issues": [
                {"item": "自动审查", "status": "issue",
                 "detail": f"格式审查工具执行异常（{str(e)[:80]}），建议人工审核全文格式"}
            ],
            "critical_count": 1,
            "summary": "自动审查失败，需人工审核"
        }


# ============================================================
# 工具 3：refine_draft — 定向精修
# ============================================================

REFINE_PROMPT = """你是一名资深公文秘书。请根据审阅意见修改以下公文草稿。

## 修改原则
1. **只修改审阅意见指出的问题**，保持其他所有内容原封不动
2. 不改变公文的整体结构、主旨和逻辑
3. 修改后应确保全文通顺、连贯、无矛盾
4. 如果审阅意见提到结尾用语问题，必须严格使用对应文种的规范结尾

## 审阅意见
{feedback}

## 当前草稿
{draft}

## 修改后的草稿

直接输出完整的修改后草稿，不要加任何解释或前缀。不要用 markdown 代码块包裹。"""


def refine_draft(draft: str, feedback: str, llm) -> str:
    """
    根据审阅意见定向修改公文草稿的特定问题。

    与「全文重生成」的区别：只改有问题的地方，保留其他部分不变。

    调用时机：
      - check_format 发现问题后，用其返回的 detail 作为 feedback 参数
      - 用户提出具体的修改要求时

    Args:
        draft: 当前草稿全文
        feedback: 具体修改描述，如"结尾用语应改为'妥否，请批示'"
        llm: LLM 实例
    """
    prompt = REFINE_PROMPT.format(feedback=feedback, draft=draft)

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        result = response.content if hasattr(response, "content") else str(response)
        result = result.strip()

        # 清理可能的 markdown 代码块包裹
        code_match = re.search(r"```(?:[\w]*)?\s*([\s\S]*?)\s*```", result)
        if code_match and len(code_match.group(1)) > 50:
            result = code_match.group(1).strip()

        logger.info(f"refine_draft() → {len(result)} 字符")
        return result
    except Exception as e:
        logger.error(f"refine_draft 失败：{e}")
        # 降级：返回原草稿
        return draft


# ============================================================
# 工具 4：ask_user — 向用户提问
# ============================================================

def ask_user(question: str) -> str:
    """
    当用户需求不够明确时，向用户提问澄清。

    调用时机：
      - 用户没有指定公文文种且无法推断
      - 缺少必要信息（部门、预算金额、日期、抄送单位等）
      - 用户需求存在歧义

    Args:
        question: 需要向用户确认的问题
    """
    logger.info(f"ask_user('{question}')")
    return f"__ASK_USER__{question}"


# ============================================================
# 工具 5：finish — 完成任务
# ============================================================

def finish(final_draft: str, summary: str) -> str:
    """
    标记任务完成，输出最终稿。

    调用时机：
      - check_format 全部通过后
      - 草稿质量满意，不需要再修改

    Args:
        final_draft: 最终公文全文
        summary: 修改说明（列出做了什么修改）
    """
    logger.info(f"finish() → {len(final_draft)} 字符")
    data = {
        "final_draft": final_draft,
        "summary": summary,
    }
    return f"__FINISH__{json.dumps(data, ensure_ascii=False)}"


# ============================================================
# 工具注册表（OpenAI/DeepSeek function calling 格式）
# ============================================================

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_exemplars",
            "description": (
                "从历史公文范文库中检索相关范文。"
                "在开始撰写公文前，必须先调用此工具获取格式参考和写作范例。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "检索关键词，如'订购服务器请示''安全生产会议通知'",
                    },
                    "k": {
                        "type": "integer",
                        "default": 4,
                        "description": "返回范文数量，建议 3-5 篇",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_format",
            "description": (
                "逐项审查公文草稿是否符合 GB/T 9704-2012 格式规范。"
                "每次生成或修改草稿后，都必须调用此工具进行审查。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "draft": {
                        "type": "string",
                        "description": "需要审查的公文草稿全文",
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "公文类型：请示/报告/通知/函/纪要/决定/批复/通报/公告/意见",
                    },
                },
                "required": ["draft", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refine_draft",
            "description": (
                "根据审阅意见定向修改公文草稿的特定问题。"
                "当 check_format 发现问题时，必须调用此工具修复，而不是全文重写。"
                "feedback 参数应直接引用 check_format 返回的问题 detail。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "draft": {
                        "type": "string",
                        "description": "当前草稿全文",
                    },
                    "feedback": {
                        "type": "string",
                        "description": (
                            "需要修改的具体问题描述，直接引用 check_format 返回的 detail 字段。"
                            "例如：'结尾用语应从特此报告改为妥否，请批示'"
                        ),
                    },
                },
                "required": ["draft", "feedback"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "当用户需求不明确且无法合理推断时，向用户提问以获取必要信息。"
                "例如：缺少文种、部门信息、预算金额、抄送单位等。"
                "重要：每次调用只问【一个】最关键的缺失要素，问题要具体、单一，"
                "不要把多个问题合并到一次提问里；能推断的尽量推断，最多问 3 次。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "需要向用户确认的问题",
                    },
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": (
                "当公文草稿已完成且格式审查通过时，调用此工具结束任务。"
                "summary 中应列出本次生成做了哪些修改（如'修正了结尾用语，将报告式改为请示规范结尾'）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "final_draft": {
                        "type": "string",
                        "description": "最终公文全文",
                    },
                    "summary": {
                        "type": "string",
                        "description": "修改说明和注意事项",
                    },
                },
                "required": ["final_draft", "summary"],
            },
        },
    },
]


# ============================================================
# 工具分发器
# ============================================================

def execute_tool(name: str, args: dict, llm) -> str:
    """根据工具名调用对应的 Python 函数，返回字符串结果。"""
    if name == "search_exemplars":
        result = search_exemplars(args.get("query", ""), args.get("k", 4))
        return json.dumps(result, ensure_ascii=False)

    elif name == "check_format":
        result = check_format(args["draft"], args["doc_type"], llm)
        return json.dumps(result, ensure_ascii=False)

    elif name == "refine_draft":
        result = refine_draft(args["draft"], args["feedback"], llm)
        return result  # 纯文本，不 JSON 包装

    elif name == "ask_user":
        return ask_user(args.get("question", ""))

    elif name == "finish":
        return finish(args["final_draft"], args["summary"])

    else:
        logger.warning(f"未知工具调用：{name}")
        return json.dumps({"error": f"未知工具：{name}"}, ensure_ascii=False)
