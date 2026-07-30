"""淘宝/天猫 上架 Skill（千牛工作台）。

后台入口：千牛工作台 / 卖家中心 https://myseller.taobao.com
商品发布：https://item.taobao.com/publish.htm（需先选类目）
登录：https://login.taobao.com（账号密码 + 滑块/短信）

平台特性：
  - 发布表单常嵌在千牛 content iframe 内，需切换 frame
  - 类目为三级联动点击选择（一级/二级/三级），非 select 下拉
  - 标题 60 字，主图 5 张 800×800，天猫有卖点字段

注意：以下选择器基于已知 DOM 模式，需对照真实后台 DOM 校正后写入 YAML。
"""
from __future__ import annotations

import logging

from engine.humanize import random_sleep, human_click, ElementNotFoundError
from skills.listing import ListingSkill, register_listing

logger = logging.getLogger(__name__)


@register_listing("taobao")
class TaobaoListingSkill(ListingSkill):
    """淘宝：iframe 表单 + 三级类目联动。"""

    async def _get_form_frame(self, page):
        """千牛发布表单常在 content iframe 内，切换进去；无则用 page。"""
        iframe_sel = self.listing_cfg.get("form_iframe")
        if iframe_sel:
            try:
                frame = page.frame_locator(iframe_sel)
                return frame
            except Exception as e:
                logger.warning("taobao form iframe switch failed: %s", e)
        return page

    async def _select_category(self, page, category):
        """三级类目联动：逐级点击。category.value 形如 '服装/男装/T恤'。"""
        if not category or not category.get("value"):
            return
        cat_cfg = self.listing_cfg.get("category", {})
        levels = [s.strip() for s in category["value"].split("/") if s.strip()]
        level_selectors = cat_cfg.get("level_selectors", [])
        logger.info("[taobao] select_category levels=%s", levels)
        for i, name in enumerate(levels):
            if i >= len(level_selectors):
                break
            try:
                await page.click(level_selectors[i])
                await random_sleep(0.4, 0.1)
                # 按文案点选级联项
                await page.click(f"text={name}")
                await random_sleep(0.4, 0.1)
            except Exception as e:
                logger.warning("taobao category level %d (%s) failed: %s", i, name, e)
        next_btn = cat_cfg.get("next_btn")
        if next_btn:
            try:
                await human_click(page, next_btn)
                await random_sleep(1.2, 0.3)
            except (ElementNotFoundError, Exception) as e:
                logger.warning("taobao category next failed: %s", e)
