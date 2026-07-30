"""SKU 价格匹配 Skill 测试。"""
import asyncio
from unittest.mock import patch

from skills.sku_price import SkuPriceSkill


def _fake_shop(markup_ratio=1.35, base=0.0, promo=None):
    class _Proxy:
        server = ""
    class _Shop:
        shop_id = "shop_001"
        price_strategy = {"markup_ratio": markup_ratio, "base": base, "promo": promo}
    return _Shop


def test_sku_price_filters_no_stock():
    skus = [
        {"sku_code": "S1", "spec": "红-M", "cost": 50.0, "stock": 100},
        {"sku_code": "S2", "spec": "红-L", "cost": 50.0, "stock": 0},
    ]
    with patch("data.repositories.shop_repo.ShopRepo.get", return_value=_fake_shop()):
        skill = SkuPriceSkill(config=object())
        res = asyncio.run(skill.execute(skus=skus, shop_id="shop_001"))
    assert res.ok
    lst = res.data["sku_price_list"]
    assert len(lst) == 1
    assert lst[0]["sku"] == "S1"
    assert lst[0]["price"] == round(50.0 * 1.35, 2)


def test_sku_price_all_no_stock_fatal():
    skus = [{"sku_code": "S1", "cost": 50.0, "stock": 0}]
    with patch("data.repositories.shop_repo.ShopRepo.get", return_value=_fake_shop()):
        skill = SkuPriceSkill(config=object())
        res = asyncio.run(skill.execute(skus=skus, shop_id="shop_001"))
    assert not res.ok
    assert res.error_code == "SKU_2001"


def test_sku_price_promo_cap():
    skus = [{"sku_code": "S1", "cost": 100.0, "stock": 10}]
    with patch("data.repositories.shop_repo.ShopRepo.get",
               return_value=_fake_shop(markup_ratio=2.0, promo=150.0)):
        skill = SkuPriceSkill(config=object())
        res = asyncio.run(skill.execute(skus=skus, shop_id="shop_001"))
    assert res.ok
    # 原价 200，被 promo 150 封顶
    assert res.data["sku_price_list"][0]["price"] == 150.0
