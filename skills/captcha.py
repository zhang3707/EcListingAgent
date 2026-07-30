"""5.2.4 验证码处理 Skill：滑块 CV + 短信人机协同。"""
from __future__ import annotations

import logging

from engine.captcha.slider import SliderSolver
from engine.captcha.slider_detect import SliderDetector
from engine.humanize import random_sleep
from integrations.feishu.bot import FeishuBot
from skills.base import BaseSkill, SkillResult, SkillStatus

logger = logging.getLogger(__name__)


class CaptchaSkill(BaseSkill):
    name = "captcha"

    @property
    def selectors(self) -> dict:
        from data.repositories.shop_repo import ShopRepo
        shop = ShopRepo().get(self.browser.shop_id) if self.browser else None
        return shop.selectors if shop else {}

    async def detect_type(self) -> str:
        """识别当前页面验证码类型：sms / slide / none。"""
        page = self.browser.page
        if await page.query_selector(self.selectors.get("sms_input", "")):
            return "sms"
        if await page.query_selector(self.selectors.get("slider_canvas", "")):
            return "slide"
        return "none"

    async def solve_slider(self) -> SkillResult:
        model_path = self.config.captcha.get("slider_model")
        max_retry = self.config.captcha.get("max_slide_retry", 3)
        detector = SliderDetector(model_path)
        solver = SliderSolver(detector, verify_fn=None)
        page = self.browser.page
        ok = await solver.solve(
            page,
            self.selectors.get("slider_handle", ".slider-btn"),
            self.selectors.get("slider_canvas", ".captcha-canvas"),
            slider_img_selector=self.selectors.get("slider_piece"),
            max_retry=max_retry,
        )
        if ok:
            return self._ok({"verified": True})
        return self._human("slide failed after retries", "CAP_3001")

    async def trigger_sms_send(self):
        page = self.browser.page
        btn = self.selectors.get("sms_send_btn", "#sendSmsBtn")
        try:
            await page.click(btn)
        except Exception as e:
            logger.warning("trigger sms send failed: %s", e)

    def notify_human_for_sms(self, task_id: str, shop_id: str):
        FeishuBot(self.config.feishu).notify_sms(task_id, shop_id)

    async def submit_sms_code(self, code: str) -> SkillResult:
        page = self.browser.page
        try:
            await page.fill(self.selectors.get("sms_input", "input[name=smscode]"), code)
            await page.click(self.selectors.get("sms_submit", "#submitBtn"))
            await random_sleep(1.5, 0.4)
            return self._ok({"verified": True})
        except Exception as e:
            return self._retry(f"sms submit failed: {e}", "CAP_1002")
