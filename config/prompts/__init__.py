"""
============================================================
Prompt 模板加载器
============================================================
支持两种方式加载 prompt：
  1. YAML 文件（优先，可在运行时编辑，下次请求生效）
  2. Python 代码中的默认值（兜底）

用法：
    from config.prompts import load_prompt
    prompt_text = load_prompt("rag_system")  # → str
"""

import yaml
from pathlib import Path
from functools import lru_cache
from typing import Optional

_PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=16)
def load_prompt(name: str, default: Optional[str] = None) -> str:
    """
    按名称加载 prompt 模板。

    查找顺序：
      1. {name}.yaml → 解析 YAML，取其中的 "prompt" 字段
      2. 回退到 default 参数

    Args:
        name:    prompt 名称（不含扩展名），如 "rag_system"。
        default: YAML 文件不存在时的兜底文本。

    Returns:
        prompt 文本字符串。

    Raises:
        FileNotFoundError: YAML 文件不存在且 default 未提供。
    """
    yaml_path = _PROMPTS_DIR / f"{name}.yaml"

    if yaml_path.exists():
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "prompt" in data:
                return data["prompt"].strip()
            # 向后兼容：如果是纯文本 YAML
            if isinstance(data, str):
                return data.strip()
        except Exception:
            # YAML 解析失败 → 回退到 default
            pass

    if default is not None:
        return default.strip()

    raise FileNotFoundError(
        f"Prompt '{name}' not found: {yaml_path} does not exist, "
        f"and no default was provided."
    )
