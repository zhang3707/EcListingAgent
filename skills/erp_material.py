"""5.2.1 ERP 素材检索 Skill。"""
from __future__ import annotations

import logging

from integrations.erp.erp_client import ErpClient, MockErpClient
from skills.base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)


class ErpMaterialSkill(BaseSkill):
    name = "erp_material"

    async def execute(self, product_code: str, material_type: str = "all", **_) -> SkillResult:
        try:
            client = self._build_client()
            if client.supports_db():
                meta = client.query_by_code(product_code)
            else:
                meta = client.scrape_by_code(product_code)
            material = self._preprocess(meta)
            return self._ok({"material": material})
        except ConnectionError as e:
            return self._retry(str(e), "ERP_1001")
        except NotImplementedError as e:
            return self._fatal(str(e), "ERP_2002")
        except Exception as e:
            logger.exception("erp material failed")
            return self._fatal(str(e), "ERP_2001")

    def _build_client(self) -> ErpClient:
        erp_cfg = getattr(self.config, "erp", None) or {}
        if erp_cfg.get("mock", True):
            return MockErpClient(erp_cfg)
        return ErpClient(erp_cfg)

    def _preprocess(self, meta: dict) -> dict:
        """素材预处理：图片尺寸适配、压缩（占位，按平台要求扩展）。"""
        return {
            "title": meta.get("title", ""),
            "image_urls": meta.get("image_urls", []),
            "spec_params": meta.get("spec_params", {}),
            "detail_text": meta.get("detail_text", ""),
            "skus": meta.get("skus", []),
        }
