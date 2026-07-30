"""京东 上架 Skill（京麦工作台 shop.jd.com）。

后台入口：https://shop.jd.com
商品发布：京麦工作台 → 商品管理 → 发布商品（表单在 iframe 内）
登录：https://passport.jd.com（账号密码 + 短信验证码）

平台特性：
  - 发布表单在京麦 content iframe 内，需切换 frame
  - 类目为三级联动点击选择
  - SKU 矩阵：选颜色规格值 + 尺码规格值后，后台自动生成笛卡尔积矩阵
  - 主图至少 1 张 800×800，详情图必传
  - 提交前需勾选《商品承诺函》并二次确认

注意：以下选择器基于已知 DOM 模式，需对照真实后台 DOM 校正后写入 YAML。
"""
from __future__ import annotations

import logging

from engine.humanize import random_sleep, human_click, ElementNotFoundError
from skills.listing import ListingSkill, register_listing, parse_spec_dims

logger = logging.getLogger(__name__)


@register_listing("jingdong")
class JingdongListingSkill(ListingSkill):
    """京东：iframe 表单 + 三级类目联动 + SKU 矩阵 + 承诺函。"""

    async def _get_form_frame(self, page):
        """京麦发布表单常在 content iframe 内，切换进去；无则用 page。"""
        iframe_sel = self.listing_cfg.get("form_iframe")
        if iframe_sel:
            try:
                return page.frame_locator(iframe_sel)
            except Exception as e:
                logger.warning("jingdong form iframe switch failed: %s", e)
        return page

    async def _select_category(self, page, category):
        """三级类目联动：逐级点击。category.value 形如 '服装/男装/T恤'。"""
        if not category or not category.get("value"):
            return
        cat_cfg = self.listing_cfg.get("category", {})
        levels = [s.strip() for s in category["value"].split("/") if s.strip()]
        level_selectors = cat_cfg.get("level_selectors", [])
        logger.info("[jingdong] select_category levels=%s", levels)
        for i, name in enumerate(levels):
            if i >= len(level_selectors):
                break
            try:
                await page.click(level_selectors[i])
                await random_sleep(0.4, 0.1)
                await page.click(f"text={name}")
                await random_sleep(0.4, 0.1)
            except Exception as e:
                logger.warning("jingdong category level %d (%s) failed: %s", i, name, e)
        next_btn = cat_cfg.get("next_btn")
        if next_btn:
            try:
                await human_click(page, next_btn)
                await random_sleep(1.5, 0.3)
            except (ElementNotFoundError, Exception) as e:
                logger.warning("jingdong category next failed: %s", e)

    async def _fill_skus(self, page, sku_price_list):
        """京东 SKU 矩阵：先填两维规格值（触发后台生成矩阵），再逐行填价格库存。

        依赖 listing_cfg.sku：
          spec_name_1 / spec_name_2 : 规格名输入框
          spec_values_1 / spec_values_2 : 规格值批量输入（逗号分隔，回车确认）
          price / stock : 矩阵展开后的行级输入框
        """
        sku_cfg = self.listing_cfg.get("sku", {})
        if not sku_cfg or not sku_price_list:
            return
        # 推断两维规格值集合
        value_sets: list[list[str]] = [[], []]
        for sku in sku_price_list:
            parts = parse_spec_dims(sku.get("spec") or "")
            for i, v in enumerate(parts[:2]):
                if v and v not in value_sets[i]:
                    value_sets[i].append(v)
        spec_names = sku_cfg.get("spec_names") or ["颜色", "尺码"]

        logger.info("[jingdong] fill_skus matrix dims=%s values=%s",
                    spec_names[:2], value_sets)

        # 启用双规格：点击「添加规格」按钮（如有）
        add_btn = sku_cfg.get("add_spec_btn")
        if add_btn and value_sets[1]:
            try:
                await human_click(page, add_btn)
                await random_sleep(0.5, 0.1)
            except (ElementNotFoundError, Exception) as e:
                logger.warning("jingdong add_spec_btn failed: %s", e)

        # 填规格名
        for i, name_sel in enumerate([sku_cfg.get("spec_name_1"),
                                      sku_cfg.get("spec_name_2")]):
            if name_sel and i < len(spec_names) and value_sets[i]:
                try:
                    await page.fill(name_sel, "")
                    await page.type(name_sel, spec_names[i])
                    await random_sleep(0.3, 0.1)
                except Exception as e:
                    logger.warning("jingdong spec_name_%d fill failed: %s", i + 1, e)
        # 填规格值（逗号分隔 + 回车）
        for i, val_sel in enumerate([sku_cfg.get("spec_values_1"),
                                     sku_cfg.get("spec_values_2")]):
            if val_sel and i < len(value_sets) and value_sets[i]:
                try:
                    await page.fill(val_sel, "")
                    await page.type(val_sel, ",".join(value_sets[i]))
                    await random_sleep(0.4, 0.1)
                    await page.keyboard.press("Enter")
                    await random_sleep(0.8, 0.2)  # 等矩阵展开
                except Exception as e:
                    logger.warning("jingdong spec_values_%d fill failed: %s", i + 1, e)

        # 矩阵展开后逐行填价格/库存
        await random_sleep(1.2, 0.3)
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
                logger.warning("jingdong sku row %d fill failed: %s", idx, e)

    async def _quirk_before_submit(self, page, material):
        """提交前：勾选承诺函 + 二次确认弹窗。"""
        agree = self.listing_cfg.get("agree_checkbox")
        if agree:
            try:
                cb = await page.query_selector(agree)
                if cb and not await cb.is_checked():
                    await cb.check()
                    await random_sleep(0.3, 0.1)
            except Exception as e:
                logger.warning("jingdong check promise failed: %s", e)
        # 京东提交后常弹「确认发布」二次确认
        confirm_btn = self.listing_cfg.get("confirm_btn")
        if confirm_btn:
            try:
                await human_click(page, confirm_btn)
                await random_sleep(0.5, 0.1)
            except (ElementNotFoundError, Exception) as e:
                logger.debug("jingdong confirm_btn not present: %s", e)
