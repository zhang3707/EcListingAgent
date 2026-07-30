"""5.2.3 店铺上架 Skill（配置驱动）。

选择器与字段映射全部来自店铺 YAML 的 listing 配置块，实现：
类目选择 → 标题/卖点/详情填充 → 主图/详情图本地上传 → SKU 矩阵 → 运费 → 提交 → 列表校验。

平台相关差异通过子类覆写 _quirk_* 钩子处理；新增平台只需注册子类并补充配置。
build_listing_plan 为纯逻辑，可脱离浏览器单测。
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Optional

import requests
from playwright.async_api import Page, TimeoutError as PWTimeout

from engine.humanize import human_click, human_type, random_sleep, human_scroll, ElementNotFoundError
from skills.base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)

LISTING_REGISTRY: dict[str, type["ListingSkill"]] = {}


def register_listing(platform: str):
    def deco(cls):
        LISTING_REGISTRY[platform] = cls
        return cls
    return deco


def get_listing_skill(shop_id: str, config=None, browser=None) -> "ListingSkill":
    from data.repositories.shop_repo import ShopRepo
    shop = ShopRepo().get(shop_id)
    platform = shop.platform if shop else "platform_a"
    cls = LISTING_REGISTRY.get(platform, PlatformAListingSkill)
    return cls(config=config, browser=browser)


# ---------------- 纯逻辑：上架计划构建（可单测） ----------------

def parse_spec_dims(spec: str, sep: str = "-") -> list[str]:
    """拆分 SKU 规格字符串为维度值列表，如 "红色-M" → ["红色", "M"]。"""
    if not spec:
        return []
    return [p.strip() for p in spec.split(sep) if p.strip()]


def build_listing_plan(material: dict, sku_price_list: list,
                       listing_cfg: dict) -> dict:
    """把商品素材 + SKU 价格表 + listing 配置 → 结构化上架计划。

    返回：
      {
        category: {selector, value} | None,
        text_fields: [{selector, value, type, max}],
        images: [{selector, urls, multiple}],
        skus: [...],
        shipping: {selector, value} | None,
        submit: selector,
        list_verify: {...} | None,
      }
    """
    fields = listing_cfg.get("fields", {})
    text_fields: list[dict] = []

    # 标题
    if "title" in fields:
        max_len = fields["title"].get("max", 999)
        text_fields.append({
            "selector": fields["title"]["selector"],
            "value": (material.get("title", "") or "")[:max_len],
            "type": fields["title"].get("type", "input"),
        })

    # 卖点：由规格参数派生（可被 material.sellpoint 覆盖）
    if "sellpoint" in fields:
        spec = material.get("spec_params", {}) or {}
        sellpoint = material.get("sellpoint") or "；".join(f"{k}:{v}" for k, v in spec.items())
        max_len = fields["sellpoint"].get("max", 999)
        text_fields.append({
            "selector": fields["sellpoint"]["selector"],
            "value": sellpoint[:max_len],
            "type": fields["sellpoint"].get("type", "textarea"),
        })

    # 详情描述
    if "detail" in fields:
        max_len = fields["detail"].get("max", 99999)
        text_fields.append({
            "selector": fields["detail"]["selector"],
            "value": (material.get("detail_text", "") or "")[:max_len],
            "type": fields["detail"].get("type", "textarea"),
        })

    # 图片上传
    images: list[dict] = []
    image_cfg = fields.get("image_upload", {})
    urls = material.get("image_urls", []) or []
    for key, cfg in image_cfg.items():
        if not cfg.get("selector"):
            continue
        images.append({
            "selector": cfg["selector"],
            "urls": urls,
            "multiple": cfg.get("multiple", key == "main"),
        })

    return {
        "category": listing_cfg.get("category"),
        "text_fields": text_fields,
        "images": images,
        "skus": sku_price_list,
        "shipping": listing_cfg.get("shipping"),
        "submit": listing_cfg.get("submit_btn", "button[type=submit]"),
        "list_verify": listing_cfg.get("list_verify"),
    }


# ---------------- Skill 实现 ----------------

class ListingSkill(BaseSkill):
    name = "listing"

    @property
    def shop(self):
        from data.repositories.shop_repo import ShopRepo
        return ShopRepo().get(self.browser.shop_id) if self.browser else None

    @property
    def listing_cfg(self) -> dict:
        return (self.shop.selectors.get("listing", {}) if self.shop else {})

    async def _get_form_frame(self, page: Page):
        """表单所在 frame/page。默认即 page；千牛/京麦等 iframe 后台子类覆写切换。"""
        return page

    async def execute(self, material: dict, sku_price_list: list,
                      shop_id: str, **_) -> SkillResult:
        if not self.browser:
            return self._fatal("browser env not provided", "LST_2002")
        page = self.browser.page or await self.browser.new_page()
        plan = build_listing_plan(material, sku_price_list, self.listing_cfg)
        base = self.shop.base_url if self.shop else ""
        publish_path = self.listing_cfg.get("publish_path", "/item/publish")
        try:
            await page.goto(f"{base}{publish_path}", wait_until="domcontentloaded")
            await random_sleep(1.0, 0.3)

            await self._select_category(page, plan["category"])
            await self._fill_text_fields(page, plan["text_fields"])
            await self._upload_images(page, plan["images"])
            await self._fill_skus(page, plan["skus"])
            await self._set_shipping(page, plan["shipping"])
            await self._quirk_before_submit(page, material)
            await self._submit(page, plan["submit"])
            return self._ok({"submitted": True, "plan": plan})
        except PWTimeout as e:
            return self._retry(f"submit timeout: {e}", "LST_1001")
        except Exception as e:
            logger.exception("listing failed")
            return self._retry(str(e), "LST_1002")

    async def verify(self, shelf_result: dict) -> SkillResult:
        if not self.browser:
            return self._ok({"verified": False, "platform_item_id": ""})
        page = self.browser.page
        base = self.shop.base_url if self.shop else ""
        list_path = self.listing_cfg.get("list_path", "/item/list")
        try:
            await page.goto(f"{base}{list_path}", wait_until="domcontentloaded")
            await random_sleep(1.0, 0.3)
            verified, pid = await self._inspect_list(page, shelf_result)
            return self._ok({"verified": verified, "platform_item_id": pid})
        except Exception as e:
            return self._retry(str(e), "LST_1003")

    # ---- 步骤实现 ----
    async def _select_category(self, page: Page, category: dict | None):
        if not category or not category.get("selector"):
            return
        logger.info("[listing] select_category value=%s", category.get("value"))
        try:
            await page.select_option(category["selector"], category["value"])
            await random_sleep(0.5, 0.1)
        except Exception as e:
            logger.warning("select_category failed: %s", e)

    async def _fill_text_fields(self, page: Page, text_fields: list[dict]):
        for f in text_fields:
            try:
                if f["type"] == "rich":
                    # 富文本：先点击聚焦，再逐字符输入
                    await human_type(page, f["selector"], f["value"])
                else:
                    await human_type(page, f["selector"], f["value"])
                await random_sleep(0.4, 0.1)
            except ElementNotFoundError as e:
                logger.warning("fill field %s failed: %s", f["selector"], e)

    async def _upload_images(self, page: Page, images: list[dict]):
        for img in images:
            if not img["urls"]:
                continue
            paths = await self._download_images(img["urls"])
            if not paths:
                continue
            try:
                # 模拟本地上传：set_input_files
                files = [str(p) for p in paths] if img["multiple"] else [str(paths[0])]
                await page.set_input_files(img["selector"], files)
                await random_sleep(0.8, 0.2)
                logger.info("[listing] uploaded %d images to %s", len(files), img["selector"])
            except Exception as e:
                logger.warning("upload to %s failed: %s", img["selector"], e)

    async def _download_images(self, urls: list[str]) -> list[Path]:
        """下载图片到临时目录，返回本地路径列表。"""
        import asyncio
        tmp = Path(tempfile.mkdtemp(prefix="ecimg_"))
        out: list[Path] = []
        for i, url in enumerate(urls):
            try:
                path = await asyncio.to_thread(self._download_one, url, tmp / f"img_{i}.jpg")
                if path:
                    out.append(path)
            except Exception as e:
                logger.warning("download %s failed: %s", url, e)
        return out

    @staticmethod
    def _download_one(url: str, dest: Path) -> Optional[Path]:
        if url.startswith("file://"):
            src = Path(url[7:])
            if src.exists():
                import shutil
                shutil.copy(src, dest)
                return dest
            return None
        r = requests.get(url, timeout=20, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return dest

    async def _fill_skus(self, page: Page, sku_price_list: list):
        """批量添加 SKU 规格、价格、库存。

        通用流程：点「添加规格」→ 填规格名/值 → 逐行填价格、库存。
        选择器由 listing_cfg.sku 提供。
        """
        sku_cfg = self.listing_cfg.get("sku", {})
        if not sku_cfg or not sku_price_list:
            logger.info("[listing] no sku config or empty sku list, skip")
            return
        logger.info("[listing] fill_skus count=%d", len(sku_price_list))
        add_btn = sku_cfg.get("add_spec_btn")
        if add_btn:
            try:
                await human_click(page, add_btn)
                await random_sleep(0.5, 0.1)
            except ElementNotFoundError as e:
                logger.warning("click add_spec_btn failed: %s", e)

        for idx, sku in enumerate(sku_price_list):
            try:
                if sku_cfg.get("spec_value"):
                    await human_type(page, sku_cfg["spec_value"], sku.get("spec", ""))
                if sku_cfg.get("price"):
                    await self._fill_input(page, sku_cfg["price"], str(sku["price"]))
                if sku_cfg.get("stock"):
                    await self._fill_input(page, sku_cfg["stock"], str(sku["stock"]))
                await random_sleep(0.3, 0.1)
            except ElementNotFoundError as e:
                logger.warning("fill sku row %d failed: %s", idx, e)

    async def _fill_input(self, page: Page, selector: str, value: str):
        try:
            await page.fill(selector, value)
        except ElementNotFoundError:
            raise
        except Exception:
            await human_type(page, selector, value)

    async def _search_select(self, page: Page, input_sel: str, keyword: str,
                             candidate_text: str, dropdown_wait: float = 1.0):
        """搜索候选下拉通用流程：清空输入 → 键入关键字 → 等候选 → 点匹配项。

        用于拼多多/抖音类目搜索选择，避免每个子类重复实现。
        """
        try:
            await page.fill(input_sel, "")
            await human_type(page, input_sel, keyword)
            await random_sleep(dropdown_wait, 0.2)
            # 优先精确文案，回退包含匹配
            try:
                await page.click(f"text={candidate_text}", timeout=2000)
            except Exception:
                await page.click(f"text*={candidate_text}", timeout=2000)
            await random_sleep(0.4, 0.1)
        except Exception as e:
            logger.warning("search_select '%s' failed: %s", keyword, e)

    async def _set_shipping(self, page: Page, shipping: dict | None):
        if not shipping or not shipping.get("selector"):
            await human_scroll(page, times=2)
            return
        logger.info("[listing] set_shipping value=%s", shipping.get("value"))
        try:
            await page.select_option(shipping["selector"], shipping["value"])
        except Exception as e:
            logger.warning("set_shipping failed: %s", e)
        await human_scroll(page, times=2)

    async def _submit(self, page: Page, submit_selector: str):
        logger.info("[listing] submit")
        try:
            await human_click(page, submit_selector)
        except ElementNotFoundError:
            # 退而用键盘 Enter
            await page.keyboard.press("Enter")
        # 等待跳转或成功提示
        try:
            await page.wait_for_url("**/item/**", timeout=15000)
        except PWTimeout:
            pass
        await random_sleep(2.0, 0.5)

    async def _inspect_list(self, page: Page, shelf_result: dict) -> tuple[bool, str]:
        verify_cfg = self.listing_cfg.get("list_verify") or {}
        if not verify_cfg:
            return True, shelf_result.get("platform_item_id", "")
        row_sel = verify_cfg.get("item_row", ".item-row")
        status_sel = verify_cfg.get("item_status", ".item-status")
        success_text = verify_cfg.get("success_status", "上架中")
        try:
            await page.wait_for_selector(row_sel, timeout=10000)
        except PWTimeout:
            return False, ""
        rows = await page.query_selector_all(row_sel)
        for row in rows:
            status_el = await row.query_selector(status_sel) if status_sel else None
            if status_el:
                text = (await status_el.inner_text()).strip()
                if success_text in text:
                    return True, ""
        return False, ""

    # ---- 平台差异钩子（子类覆写） ----
    async def _quirk_before_submit(self, page: Page, material: dict):
        """提交前平台特有操作，如勾选协议、二次确认。"""


@register_listing("platform_a")
class PlatformAListingSkill(ListingSkill):
    """平台 A：通用配置驱动实现，覆盖多数电商后台共性流程。

    实际选择器值需对照目标站点 DOM 校正（config/shops/*.yaml 的 listing 块）。
    """


@register_listing("platform_b")
class PlatformBListingSkill(ListingSkill):
    """平台 B 示例：演示多平台注册扩展。

    差异：提交前需勾选服务协议。
    """

    async def _quirk_before_submit(self, page: Page, material: dict):
        agree = self.listing_cfg.get("agree_checkbox")
        if agree:
            try:
                await page.check(agree)
                await random_sleep(0.3, 0.1)
            except Exception as e:
                logger.warning("check agree failed: %s", e)
