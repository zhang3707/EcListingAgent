"""拼多多 上架 Skill（拼多多商家后台 mms）。

后台入口：https://mms.pinduoduo.com
商品发布：https://mms.pinduoduo.com/goods/goods_create.html
登录：https://mms.pinduoduo.com/login.html（账号密码 + 短信验证码必发）

平台特性：
  - 类目为「搜索关键字 → 下拉候选 → 点选」，非级联点击
  - 商品发布分步骤：基础信息 → SKU 规格 → 物流，每步可独立校验
  - 单/双规格切换：双规格时颜色+尺码两维
  - 提交前必须勾选《商品承诺函》

注意：以下选择器基于已知 DOM 模式，需对照真实后台 DOM 校正后写入 YAML。
"""
from __future__ import annotations

import logging

from engine.humanize import random_sleep, human_click, ElementNotFoundError
from skills.listing import ListingSkill, register_listing, parse_spec_dims

logger = logging.getLogger(__name__)


@register_listing("pinduoduo")
class PinduoduoListingSkill(ListingSkill):
    """拼多多：搜索式类目 + 双规格 SKU + 承诺函勾选。"""

    async def _select_category(self, page, category):
        """类目搜索选择：键入关键字 → 等候选 → 点匹配项 → 下一步。

        category.value 形如 '服装/男装/T恤'，取最后一段作搜索关键字，
        整串作候选匹配文案兜底。
        """
        if not category or not category.get("value"):
            return
        cat_cfg = self.listing_cfg.get("category", {})
        input_sel = cat_cfg.get("search_input")
        if not input_sel:
            logger.warning("[pinduoduo] no category.search_input in config, skip")
            return
        value = category["value"]
        # 取最后一段作为搜索词，整串作为候选兜底文案
        levels = [s.strip() for s in value.split("/") if s.strip()]
        keyword = levels[-1] if levels else value
        candidate = levels[-1] if levels else value
        logger.info("[pinduoduo] search_category keyword=%s", keyword)
        await self._search_select(page, input_sel, keyword, candidate,
                                  dropdown_wait=cat_cfg.get("dropdown_wait", 1.2))
        # 选完点「下一步」进入属性表单
        next_btn = cat_cfg.get("next_btn")
        if next_btn:
            try:
                await human_click(page, next_btn)
                await random_sleep(1.5, 0.3)
            except (ElementNotFoundError, Exception) as e:
                logger.warning("pinduoduo category next failed: %s", e)

    async def _fill_skus(self, page, sku_price_list):
        """拼多多双规格 SKU：先填规格名/值，再逐行填价格库存。

        依赖 listing_cfg.sku：
          spec_name_1 / spec_name_2  : 规格名输入框（如"颜色""尺码"）
          spec_values_1 / spec_values_2 : 规格值批量输入（逗号分隔）
          price / stock : 行级价格库存
        若配置缺双规格字段，回退到基类单规格流程。
        """
        sku_cfg = self.listing_cfg.get("sku", {})
        if not sku_cfg or not sku_price_list:
            return
        has_dual = sku_cfg.get("spec_name_2")
        if not has_dual:
            return await super()._fill_skus(page, sku_price_list)

        # 推断规格名：从首个 SKU 的 spec 字段拆分
        first_spec = (sku_price_list[0].get("spec") or "")
        dims = parse_spec_dims(first_spec)
        spec_names = sku_cfg.get("spec_names") or ["颜色", "尺码"]
        # 收集每维去重值
        value_sets: list[list[str]] = [[], []]
        for sku in sku_price_list:
            parts = parse_spec_dims(sku.get("spec") or "")
            for i, v in enumerate(parts[:2]):
                if v and v not in value_sets[i]:
                    value_sets[i].append(v)

        logger.info("[pinduoduo] fill_skus dual dims=%s values=%s",
                    spec_names[:2], value_sets)
        # 填规格名
        for i, name_sel in enumerate([sku_cfg.get("spec_name_1"),
                                      sku_cfg.get("spec_name_2")]):
            if name_sel and i < len(spec_names):
                try:
                    await page.fill(name_sel, "")
                    await page.type(name_sel, spec_names[i])
                    await random_sleep(0.3, 0.1)
                except Exception as e:
                    logger.warning("pinduoduo spec_name_%d fill failed: %s", i + 1, e)
        # 填规格值（逗号分隔）
        for i, val_sel in enumerate([sku_cfg.get("spec_values_1"),
                                     sku_cfg.get("spec_values_2")]):
            if val_sel and i < len(value_sets) and value_sets[i]:
                try:
                    await page.fill(val_sel, "")
                    await page.type(val_sel, ",".join(value_sets[i]))
                    await random_sleep(0.4, 0.1)
                    # 触发回车确认
                    await page.keyboard.press("Enter")
                    await random_sleep(0.5, 0.1)
                except Exception as e:
                    logger.warning("pinduoduo spec_values_%d fill failed: %s", i + 1, e)

        # 矩阵生成后逐行填价格/库存（依赖后台自动展开行）
        await random_sleep(1.0, 0.2)
        price_sel = sku_cfg.get("price")
        stock_sel = sku_cfg.get("stock")
        for idx, sku in enumerate(sku_price_list):
            try:
                if price_sel:
                    # 多行同名输入框，按 idx 定位
                    await self._fill_nth_input(page, price_sel, idx, str(sku["price"]))
                if stock_sel:
                    await self._fill_nth_input(page, stock_sel, idx, str(sku["stock"]))
                await random_sleep(0.2, 0.05)
            except Exception as e:
                logger.warning("pinduoduo sku row %d fill failed: %s", idx, e)

    async def _fill_nth_input(self, page, selector: str, idx: int, value: str):
        """按索引填第 N 个匹配输入框。"""
        try:
            els = await page.query_selector_all(selector)
            if idx < len(els):
                await els[idx].fill(value)
            else:
                logger.warning("pinduoduo nth_input idx=%d out of range (%d found)",
                               idx, len(els))
        except Exception as e:
            logger.warning("pinduoduo nth_input fill failed: %s", e)

    async def _quirk_before_submit(self, page, material):
        """提交前勾选《商品承诺函》。"""
        agree = self.listing_cfg.get("agree_checkbox")
        if not agree:
            return
        try:
            cb = await page.query_selector(agree)
            if cb and not await cb.is_checked():
                await cb.check()
                await random_sleep(0.3, 0.1)
        except Exception as e:
            logger.warning("pinduoduo check promise failed: %s", e)
