"""5.2.2 SKU 价格匹配 Skill。"""
from __future__ import annotations

from skills.base import BaseSkill, SkillResult
from data.repositories.shop_repo import ShopRepo


class SkuPriceSkill(BaseSkill):
    name = "sku_price"

    async def execute(self, skus: list[dict], shop_id: str, **_) -> SkillResult:
        try:
            shop = ShopRepo().get(shop_id)
            if not shop:
                return self._fatal(f"shop not found: {shop_id}", "SKU_2002")
            strategy = shop.price_strategy or {"markup_ratio": 1.3, "base": 0.0}
            markup = strategy.get("markup_ratio", 1.3)
            base = strategy.get("base", 0.0)
            promo = strategy.get("promo")

            out = []
            for sku in skus:
                stock = sku.get("stock", 0)
                if stock <= 0:
                    continue                                  # 过滤无库存
                cost = sku.get("cost", 0)
                price = round(cost * markup + base, 2)
                if promo is not None:
                    price = min(price, float(promo))
                out.append({
                    "sku": sku.get("sku_code", ""),
                    "spec": sku.get("spec", ""),
                    "price": price,
                    "stock": stock,
                    "status": "pending",
                })
            if not out:
                return self._fatal("no sku with stock", "SKU_2001")
            return self._ok({"sku_price_list": out})
        except Exception as e:
            return self._retry(str(e), "SKU_1001")
