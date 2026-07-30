"""Skill 基类与统一返回结构。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from config.settings import get_config


class SkillStatus(IntEnum):
    SUCCESS = 0          # 成功
    RETRYABLE = 1        # 可重试失败
    FATAL = 2            # 不可重试失败
    HUMAN_REQUIRED = 3   # 需人工介入


@dataclass
class SkillResult:
    status: SkillStatus
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == SkillStatus.SUCCESS


class BaseSkill:
    """所有 Skill 的基类：统一注入配置与浏览器环境。"""

    name: str = ""

    def __init__(self, config=None, browser=None):
        self.config = config or get_config()
        self.browser = browser

    async def execute(self, **kwargs) -> SkillResult:
        raise NotImplementedError

    # ---- 便捷构造 ----
    def _ok(self, data: dict | None = None) -> SkillResult:
        return SkillResult(SkillStatus.SUCCESS, data or {})

    def _retry(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.RETRYABLE, error=error, error_code=code)

    def _fatal(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.FATAL, error=error, error_code=code)

    def _human(self, error: str, code: str = "") -> SkillResult:
        return SkillResult(SkillStatus.HUMAN_REQUIRED, error=error, error_code=code)
