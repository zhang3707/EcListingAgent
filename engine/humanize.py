"""拟人化行为：贝塞尔鼠标轨迹、逐字符输入、正态分布等待。"""
from __future__ import annotations

import asyncio
import random


async def random_sleep(mean: float = 2.0, sigma: float = 0.5):
    """正态分布等待，拒绝固定间隔。"""
    await asyncio.sleep(max(0.1, random.gauss(mean, sigma)))


async def human_move(mouse, x: float, y: float, steps: int = 25):
    """贝塞尔曲线鼠标移动到 (x, y)。"""
    sx, sy = await mouse.position()
    ctrl = [
        (sx, sy),
        (sx + (x - sx) * 0.3, sy + (y - sy) * 0.1),
        (sx + (x - sx) * 0.7, sy + (y - sy) * 0.9),
        (x, y),
    ]
    for i in range(steps + 1):
        t = i / steps
        bx = ((1 - t) ** 3 * ctrl[0][0] + 3 * (1 - t) ** 2 * t * ctrl[1][0]
              + 3 * (1 - t) * t ** 2 * ctrl[2][0] + t ** 3 * ctrl[3][0])
        by = ((1 - t) ** 3 * ctrl[0][1] + 3 * (1 - t) ** 2 * t * ctrl[1][1]
              + 3 * (1 - t) * t ** 2 * ctrl[2][1] + t ** 3 * ctrl[3][1])
        await mouse.move(bx, by)
        await asyncio.sleep(random.uniform(0.005, 0.02))


async def human_click(page, selector: str, **kwargs):
    """拟人点击：移动 → 悬停 → 点击 → 随机停顿。"""
    el = await page.query_selector(selector)
    if not el:
        raise ElementNotFoundError(selector)
    box = await el.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    await human_move(page.mouse, cx, cy)
    await asyncio.sleep(random.uniform(0.1, 0.3))         # 悬停
    await page.mouse.click(cx, cy, **kwargs)
    await random_sleep(0.3, 0.1)


async def human_type(page, selector: str, text: str):
    """逐字符输入，间隔 50-200ms，偶发删除重输。"""
    await human_click(page, selector)
    for i, ch in enumerate(text):
        await page.keyboard.type(ch)
        await asyncio.sleep(random.uniform(0.05, 0.2))
        if random.random() < 0.02 and i < len(text) - 1:  # 2% 概率删重输
            await page.keyboard.press("Backspace")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await page.keyboard.type(ch)


async def human_scroll(page, times: int = 3):
    """随机滚动浏览。"""
    for _ in range(times):
        await page.mouse.wheel(0, random.randint(100, 400))
        await random_sleep(0.6, 0.2)


class ElementNotFoundError(Exception):
    def __init__(self, selector: str):
        super().__init__(f"element not found: {selector}")
        self.selector = selector
