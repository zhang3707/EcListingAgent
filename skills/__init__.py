from skills.base import BaseSkill, SkillResult, SkillStatus  # noqa: F401
from skills.erp_material import ErpMaterialSkill  # noqa: F401
from skills.sku_price import SkuPriceSkill  # noqa: F401
from skills.listing import (  # noqa: F401
    ListingSkill, PlatformAListingSkill, PlatformBListingSkill,
    LISTING_REGISTRY, get_listing_skill,
)
from skills.captcha import CaptchaSkill  # noqa: F401
from skills.feishu_sync import FeishuSyncSkill  # noqa: F401
from skills.env_manager import EnvManagerSkill  # noqa: F401
from skills.risk_guard import RiskGuardSkill, evaluate_risk  # noqa: F401

# 平台子类集中注册（导入即注册到 LISTING_REGISTRY）
from skills import platforms  # noqa: F401

SKILL_REGISTRY = {
    ErpMaterialSkill.name: ErpMaterialSkill,
    SkuPriceSkill.name: SkuPriceSkill,
    ListingSkill.name: ListingSkill,
    CaptchaSkill.name: CaptchaSkill,
    FeishuSyncSkill.name: FeishuSyncSkill,
    EnvManagerSkill.name: EnvManagerSkill,
    RiskGuardSkill.name: RiskGuardSkill,
}
