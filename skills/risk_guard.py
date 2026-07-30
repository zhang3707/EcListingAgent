"""风控熔断 Skill：检测页面级风控信号 + 计数阈值，触发即终止店铺任务。

纯逻辑 evaluate_risk 可脱离浏览器单测；RiskGuardSkill 负责采集页面信号并落库告警。
"""
from __future__ import annotations

import logging
from typing import Optional

from skills.base import BaseSkill, SkillResult, SkillStatus
from data.repositories.shop_repo import ShopRepo
from integrations.feishu.bot import FeishuBot

logger = logging.getLogger(__name__)

# 默认阈值（可被 config.captcha.risk 覆盖）
DEFAULT_THRESHOLDS = {
    "max_captcha_per_session": 3,
    "max_login_fail": 3,
}


def evaluate_risk(state: dict, signals: dict, thresholds: dict | None = None) -> dict:
    """纯逻辑风控判定。

    state: TaskState（取 captcha_fail_count / login_fail_count）
    signals: {restriction_text: str|None, restriction_element: bool}
    返回 {risk: bool, reason: str, code: str}
    """
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}

    # 1. 页面出现账号限制文案/元素 —— 最高优先级，立即熔断
    text = (signals.get("restriction_text") or "").strip()
    if text:
        return {"risk": True, "reason": f"账号限制提示: {text}", "code": "RISK_3001"}

    if signals.get("restriction_element"):
        return {"risk": True, "reason": "检测到风控限制元素", "code": "RISK_3002"}

    # 2. 验证码失败累计超阈值
    captcha_fail = state.get("captcha_fail_count", 0)
    if captcha_fail >= th["max_captcha_per_session"]:
        return {"risk": True,
                "reason": f"验证码失败 {captcha_fail} 次超阈值",
                "code": "RISK_3003"}

    # 3. 登录失败累计超阈值
    login_fail = state.get("login_fail_count", 0)
    if login_fail >= th["max_login_fail"]:
        return {"risk": True,
                "reason": f"登录失败 {login_fail} 次超阈值",
                "code": "RISK_3004"}

    return {"risk": False, "reason": "", "code": ""}


class RiskGuardSkill(BaseSkill):
    name = "risk_guard"

    @property
    def risk_cfg(self) -> dict:
        """店铺级 risk 配置（选择器/文案）。"""
        from data.repositories.shop_repo import ShopRepo
        shop = ShopRepo().get(self.browser.shop_id) if self.browser else None
        return (shop.selectors.get("risk", {}) if shop else {}) or {}

    @property
    def thresholds(self) -> dict:
        return self.config.captcha.get("risk", {}) or {}

    async def detect_signals(self) -> dict:
        """从当前页面采集风控信号。"""
        if not self.browser:
            return {"restriction_text": None, "restriction_element": False}
        page = self.browser.page
        # 元素信号
        for sel in self.risk_cfg.get("restriction_selectors", []):
            try:
                if await page.query_selector(sel):
                    return {"restriction_text": None, "restriction_element": True}
            except Exception as e:
                logger.debug("risk selector %s check failed: %s", sel, e)
        # 文案信号
        body_text = ""
        try:
            body_text = await page.inner_text("body")
        except Exception:
            pass
        for kw in self.risk_cfg.get("restriction_texts", []):
            if kw and kw in body_text:
                return {"restriction_text": kw, "restriction_element": False}
        return {"restriction_text": None, "restriction_element": False}

    async def execute(self, state: dict, **_) -> SkillResult:
        signals = await self.detect_signals()
        decision = evaluate_risk(state, signals, self.thresholds)
        if not decision["risk"]:
            return self._ok({"risk": False})

        # 触发熔断：置店铺风控态 + 飞书告警
        shop_id = self.browser.shop_id if self.browser else state.get("target_shop", "")
        if shop_id:
            ShopRepo().set_risk_status(shop_id, "limited")
        try:
            FeishuBot(self.config.feishu).notify_risk(
                shop_id, decision["reason"]
            )
        except Exception as e:
            logger.warning("risk feishu notify failed: %s", e)
        logger.warning("[risk_guard] %s triggered: %s", shop_id, decision["reason"])
        return self._ok({
            "risk": True,
            "reason": decision["reason"],
            "code": decision["code"],
        })
