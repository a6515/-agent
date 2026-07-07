"""
============================================================
公共辅助函数
============================================================
提取跨模块复用的通用逻辑，消除重复代码。
"""

import re
from datetime import datetime
from typing import Optional


# ---- 文种名称集合（用于 query 增强检查）----
_DOC_TYPE_NAMES = {"请示", "报告", "通知", "函", "纪要", "决定", "批复", "通报", "公告", "意见"}


def build_date_context() -> str:
    """
    构建当前日期上下文，注入到 LLM prompt 中。

    LLM 训练数据有截止日期，需要显式告知当前日期，
    确保所有时间相关表述（如「今年」「下个月」）以当前日期为基准。

    Returns:
        日期上下文字符串，可直接拼接到 System Prompt 后。
    """
    today = datetime.now()
    weekday_names = "一二三四五六日"
    return (
        f"\n\n# 当前日期\n\n"
        f"今天是 {today.year} 年 {today.month} 月 {today.day} 日"
        f"（星期{weekday_names[today.weekday()]}）。"
        f"当前是 {today.year} 年。所有时间相关表述"
        f"（如「今年」「明年」「年底」「下个月」等）都以这个日期为基准。"
    )


def build_date_hint() -> str:
    """
    构建简洁的日期提示，用于拼接在用户查询前。

    Returns:
        日期提示字符串。
    """
    today = datetime.now()
    return (
        f"当前日期：{today.year}年{today.month}月{today.day}日。"
        f"所有时间表述均以此为准。\n\n"
    )


def enhance_query_with_doc_type(query: str, doc_type: Optional[str] = None) -> str:
    """
    如果用户查询中未显式包含文种名称，则自动添加文种引导前缀。

    Args:
        query:    用户原始查询。
        doc_type: 识别出的文种（None 则不做增强）。

    Returns:
        可能增强后的查询字符串。
    """
    if not doc_type or doc_type == "公文":
        return query

    if any(kw in query for kw in _DOC_TYPE_NAMES):
        return query

    return f"请撰写一份{doc_type}：{query}"


def extract_title_from_content(content: str) -> str:
    """
    从生成的公文正文中提取标题。

    规则：
      1. 优先匹配以「关于」开头的前 60 字符内的第一行非空文本。
      2. 找不到「关于」则取前 30 字符作为标题。

    Args:
        content: 公文正文。

    Returns:
        提取的标题字符串。
    """
    content = re.sub(r"^#+\s*", "", content.strip())
    lines = [l.strip() for l in content.split("\n") if l.strip()]

    for line in lines[:3]:
        if "关于" in line and len(line) <= 80:
            return line

    return lines[0][:60] if lines else "（未提取到标题）"
