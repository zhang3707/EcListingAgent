"""滑块验证码编排：截图 → 定位缺口 → 派发原生鼠标事件拖动。"""
from __future__ import annotations

import io
import logging
from typing import Awaitable, Callable

from playwright.async_api import Page

from engine.captcha.slider_detect import SliderDetector
from engine.captcha.slider_track import gen_track
from engine.humanize import random_sleep

logger = logging.getLogger(__name__)

# 验证通过判定函数：(page) -> Awaitable[bool]
VerifyFn = Callable[[Page], Awaitable[bool]]


class SliderSolver:
    def __init__(self, detector: SliderDetector, verify_fn: VerifyFn | None = None):
        self.detector = detector
        self.verify_fn = verify_fn

    async def solve(
        self,
        page: Page,
        slider_handle_selector: str,
        canvas_selector: str,
        slider_img_selector: str | None = None,
        max_retry: int = 3,
    ) -> bool:
        for attempt in range(1, max_retry + 1):
            gap_x = await self._locate_gap(page, canvas_selector, slider_img_selector)
            if gap_x is None:
                logger.warning("slider gap not detected, attempt %d/%d", attempt, max_retry)
                await random_sleep(0.5, 1.0)
                continue
            await self._drag(page, slider_handle_selector, gap_x)
            await random_sleep(0.8, 1.5)
            if await self._verify(page):
                logger.info("slider passed at attempt %d", attempt)
                return True
            await random_sleep(0.6, 0.8)
        return False

    async def _locate_gap(self, page: Page, canvas_selector: str,
                          slider_img_selector: str | None) -> int | None:
        canvas = await page.query_selector(canvas_selector)
        if not canvas:
            return None
        from PIL import Image
        import numpy as np
        shot = await canvas.screenshot()
        bg = np.array(Image.open(io.BytesIO(shot)).convert("RGB"))
        slider_img = None
        if slider_img_selector:
            sl_el = await page.query_selector(slider_img_selector)
            if sl_el:
                sl_shot = await sl_el.screenshot()
                slider_img = np.array(Image.open(io.BytesIO(sl_shot)).convert("RGB"))
        return self.detector.detect_gap_x(bg, slider_img)

    async def _drag(self, page: Page, handle_selector: str, gap_x: int):
        handle = await page.query_selector(handle_selector)
        if not handle:
            raise RuntimeError(f"slider handle not found: {handle_selector}")
        box = await handle.bounding_box()
        start_x = box["x"] + box["width"] / 2
        start_y = box["y"] + box["height"] / 2
        # 原生鼠标事件，不直接改 style/left
        await page.mouse.move(start_x, start_y)
        await page.mouse.down()
        distance = gap_x - int(box["x"])
        for dx, dy, dt in gen_track(distance):
            await page.mouse.move(start_x + dx, start_y + dy)
            await page.wait_for_timeout(dt)
        await page.mouse.up()

    async def _verify(self, page: Page) -> bool:
        if self.verify_fn is None:
            # 默认：等待 1.5s 内页面无滑块元素即视为通过
            await random_sleep(1.0, 0.3)
            return not await page.query_selector(".captcha-canvas")
        return await self.verify_fn(page)
