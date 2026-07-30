"""抖音 上架 Skill（抖店 fxg.jinritemai）。

后台入口：https://fxg.jinritemai.com
商品发布：https://fxg.jinritemai.com/index.html#/ffa/cshop/goods/create
登录：https://fxg.jinritemai.com/login（扫码 / 账号密码 + 短信验证码）

平台特性：
  - 商品发布表单在 iframe 内，需切换 frame
  - 类目为搜索选择 + 动态加载商品属性表单（必填属性较多）
  - 标题 30 字以内，主图至少 1 张 1:1，详情图必传
  - 提交前需勾选《商品发布承诺函》
  - 风控：滑块/短信双轨，新店首单常触发短信

注意：以下选择器基于已知 DOM 模式，需对照真实后台 DOM 校正后写入 YAML。
"""
from __future__ import annotations

import logging

from engine.humanize import random_sleep, human_click, ElementNotFoundError
from skills.listing import ListingSkill, register_listing, parse_spec_dims

logger = logging.getLogger(__name__)


@register_listing("douyin")
class DouyinListingSkill(ListingSkill):
    """抖音：iframe 表单 + 搜索类目 + 必填属性校验 + 承诺函。"""

    async def _get_form_frame(self, page):
        """抖店发布表单常嵌在 content iframe 内，切换进去；无则用 page。"""
        iframe_sel = self.listing_cfg.get("form_iframe")
        if iframe_sel:
            try:
                return page.frame_locator(iframe_sel)
            except Exception as e:
                logger.warning("douyin form iframe switch failed: %s", e)
        return page

    async def _select_category(self, page, category):
        """抖音类目搜索选择：键入关键字 → 等候选 → 点匹配项 → 下一步。

        category.value 形如 '服装/男装/T恤'，取最后一段作搜索关键字。
        """
        if not category or not category.get("value"):
            return
        cat_cfg = self.listing_cfg.get("category", {})
        input_sel = cat_cfg.get("search_input")
        if not input_sel:
            logger.warning("[douyin] no category.search_input in config, skip")
            return
        value = category["value"]
        levels = [s.strip() for s in value.split("/") if s.strip()]
        keyword = levels[-1] if levels else value
        candidate = levels[-1] if levels else value
        logger.info("[douyin] search_category keyword=%s", keyword)
        await self._search_select(page, input_sel, keyword, candidate,
                                  dropdown_wait=cat_cfg.get("dropdown_wait", 1.5))
        next_btn = cat_cfg.get("next_btn")
        if next_btn:
            try:
                await human_click(page, next_btn)
                await random_sleep(2.0, 0.4)  # 抖音属性表单加载较慢
            except (ElementNotFoundError, Exception) as e:
                logger.warning("douyin category next failed: %s", e)

    async def _fill_skus(self, page, sku_price_list):
        """抖音 SKU：规格名 + 规格值批量填，价格库存按行填。

        抖音默认双规格（颜色+尺码），规格值通过逗号分隔批量输入。
        """
        sku_cfg = self.listing_cfg.get("sku", {})
        if not sku_cfg or not sku_price_list:
            return
        # 推断规格值集合
        value_sets: list[list[str]] = [[], []]
        for sku in sku_price_list:
            parts = parse_spec_dims(sku.get("spec") or "")
            for i, v in enumerate(parts[:2]):
                if v and v not in value_sets[i]:
                    value_sets[i].append(v)
        spec_names = sku_cfg.get("spec_names") or ["颜色", "尺码"]

        logger.info("[douyin] fill_skus dims=%s values=%s", spec_names[:2], value_sets)
        # 规格名输入
        for i, name_sel in enumerate([sku_cfg.get("spec_name_1"),
                                      sku_cfg.get("spec_name_2")]):
            if name_sel and i < len(spec_names) and value_sets[i]:
                try:
                    await page.fill(name_sel, "")
                    await page.type(name_sel, spec_names[i])
                    await random_sleep(0.3, 0.1)
                except Exception as e:
                    logger.warning("douyin spec_name_%d fill failed: %s", i + 1, e)
        # 规格值批量输入
        for i, val_sel in enumerate([sku_cfg.get("spec_values_1"),
                                     sku_cfg.get("spec_values_2")]):
            if val_sel and i < len(value_sets) and value_sets[i]:
                try:
                    await page.fill(val_sel, "")
                    await page.type(val_sel, ",".join(value_sets[i]))
                    await random_sleep(0.4, 0.1)
                    await page.keyboard.press("Enter")
                    await random_sleep(0.6, 0.1)
                except Exception as e:
                    logger.warning("douyin spec_values_%d fill failed: %s", i + 1, e)

        # 行级价格/库存
        await random_sleep(1.0, 0.2)
        price_sel = sku_cfg.get("price")
        stock_sel = sku_cfg.get("stock")
        for idx, sku in enumerate(sku_price_list):
            try:
                if price_sel:
                    els = await page.query_selector_all(price_sel)
                    if idx < len(els):
                        await els[idx].fill(str(sku["price"]))
                if stock_sel:
                    els = await page.query_selector_all(stock_sel)
                    if idx < len(els):
                        await els[idx].fill(str(sku["stock"]))
                await random_sleep(0.2, 0.05)
            except Exception as e:
                logger.warning("douyin sku row %d fill failed: %s", idx, e)

    async def _quirk_before_submit(self, page, material):
        """提交前：勾选承诺函 + 校验必填属性。"""
        # 1. 承诺函
        agree = self.listing_cfg.get("agree_checkbox")
        if agree:
            try:
                cb = await page.query_selector(agree)
                if cb and not await cb.is_checked():
                    await cb.check()
                    await random_sleep(0.3, 0.1)
            except Exception as e:
                logger.warning("douyin check promise failed: %s", e)
        # 2. 必填属性兜底：扫描 required_attr_selectors，未填则用 material.spec_params 兜底
        attr_cfg = self.listing_cfg.get("required_attrs", {})
        spec_params = material.get("spec_params", {}) or {}
        for attr_name, sel in attr_cfg.items():
            try:
                el = await page.query_selector(sel)
                if el:
                    cur = (await el.input_value()).strip() if el else ""
                    if not cur and attr_name in spec_params:
                        await el.fill(str(spec_params[attr_name]))
                        await random_sleep(0.2, 0.05)
            except Exception as e:
                logger.debug("douyin attr %s backfill failed: %s", attr_name, e)
