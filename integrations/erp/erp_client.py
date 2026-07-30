"""ERP 对接：优先数据库直连，降级浏览器网页端检索。

实际 ERP 接入需按现场情况实现。此处提供统一接口与示例占位，
保证 Skill 层可调用、可在无 ERP 环境下用 mock 数据调试。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ErpClient:
    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    def supports_db(self) -> bool:
        return bool(self.cfg.get("db_dsn"))

    def query_by_code(self, product_code: str) -> dict:
        """数据库直连：SQL 查询素材元数据 + 对象存储拉图。"""
        if not self.supports_db():
            raise ConnectionError("erp db not configured")
        # TODO: 按 ERP 实际表结构实现
        raise NotImplementedError("erp db query not implemented for current site")

    def scrape_by_code(self, product_code: str) -> dict:
        """网页端：浏览器登录 ERP → 输入编码检索 → 下载素材并结构化。"""
        # TODO: 按 ERP 网页 DOM 实现，由 browser env 驱动
        raise NotImplementedError("erp web scrape not implemented for current site")


class MockErpClient(ErpClient):
    """开发期 mock：返回结构化样例素材，便于端到端联调。"""

    def query_by_code(self, product_code: str) -> dict:
        return {
            "title": f"示例商品 {product_code}",
            "image_urls": [f"https://picsum.photos/seed/{product_code}-{i}/800/800"
                           for i in range(3)],
            "spec_params": {"品牌": "示例品牌", "产地": "中国"},
            "detail_text": f"商品 {product_code} 详情描述示例文本。",
            "skus": [
                {"sku_code": f"{product_code}-RED-M", "spec": "红色-M", "cost": 50.0, "stock": 100},
                {"sku_code": f"{product_code}-RED-L", "spec": "红色-L", "cost": 50.0, "stock": 80},
                {"sku_code": f"{product_code}-BLK-M", "spec": "黑色-M", "cost": 52.0, "stock": 0},
            ],
        }

    def scrape_by_code(self, product_code: str) -> dict:
        return self.query_by_code(product_code)
