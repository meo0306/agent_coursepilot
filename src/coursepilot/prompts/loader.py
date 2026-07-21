"""
统一读取 CoursePilot 的提示词
"""

from functools import cache
from pathlib import Path

# 提示词根目录
PROMPT_ROOT = Path(__file__).resolve().parent


@cache  # 缓存提示词内容，避免重复读取文件
def load_prompt(name: str) -> str:
    """
    按名称加载提示词
    """
    normalized = name.removesuffix(".md")  # 移除 .md 后缀，确保提示词名称一致
    path = (PROMPT_ROOT / f"{normalized}.md").resolve()  # 解析提示词路径
    # 确保提示词路径在提示词根目录下，防止路径穿越攻击
    if PROMPT_ROOT not in path.parents:
        raise ValueError(f"Invalid prompt path: {name}")
    # 如果提示词文件不存在，则抛出异常
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {name}")
    return path.read_text(encoding="utf-8").strip()
