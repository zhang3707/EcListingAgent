"""多平台注册、配置加载与 SKU 维度拆分测试。

覆盖 4 个真实平台（淘宝/拼多多/抖音/京东）+ 2 个示例平台（platform_a/b）：
  - LISTING_REGISTRY 注册完整性
  - 各平台 Skill 子类类型正确
  - 各店铺 YAML 配置加载 + 关键字段存在
  - login 配置块结构校验
  - parse_spec_dims 维度拆分
  - build_listing_plan 在各平台配置下能产出计划
"""
import pytest

import skills  # noqa: F401  触发平台子类注册
from skills.listing import (
    LISTING_REGISTRY, get_listing_skill, parse_spec_dims, build_listing_plan,
)
from skills.platforms.taobao import TaobaoListingSkill
from skills.platforms.pinduoduo import PinduoduoListingSkill
from skills.platforms.douyin import DouyinListingSkill
from skills.platforms.jingdong import JingdongListingSkill

from config.settings import reload_config


# ---- 平台注册完整性 ----

EXPECTED_PLATFORMS = {
    "taobao": TaobaoListingSkill,
    "pinduoduo": PinduoduoListingSkill,
    "douyin": DouyinListingSkill,
    "jingdong": JingdongListingSkill,
    "platform_a": None,   # 基类示例
    "platform_b": None,
}


def test_all_platforms_registered():
    """4 真实平台 + 2 示例平台 全部注册到 LISTING_REGISTRY。"""
    for name in EXPECTED_PLATFORMS:
        assert name in LISTING_REGISTRY, f"platform {name} not registered"


@pytest.mark.parametrize("name,cls", [(k, v) for k, v in EXPECTED_PLATFORMS.items() if v])
def test_platform_class_matches(name, cls):
    """各平台注册的类与子模块定义一致。"""
    assert LISTING_REGISTRY[name] is cls


# ---- 店铺 YAML 配置加载 ----

@pytest.fixture(scope="module")
def cfg():
    return reload_config()


SHOP_PLATFORM_MAP = {
    "shop_taobao": "taobao",
    "shop_pinduoduo": "pinduoduo",
    "shop_douyin": "douyin",
    "shop_jingdong": "jingdong",
}


@pytest.mark.parametrize("shop_id,platform", list(SHOP_PLATFORM_MAP.items()))
def test_shop_yaml_loaded(cfg, shop_id, platform):
    """4 个店铺 YAML 均加载成功，platform 字段对齐。"""
    assert shop_id in cfg.shops, f"{shop_id} not loaded"
    assert cfg.shops[shop_id].platform == platform


@pytest.mark.parametrize("shop_id", list(SHOP_PLATFORM_MAP.keys()))
def test_shop_has_base_url_and_account(cfg, shop_id):
    shop = cfg.shops[shop_id]
    assert shop.base_url.startswith("http"), f"{shop_id} base_url invalid"
    assert "username" in shop.account
    assert "password" in shop.account   # 可能是 ${VAR} 占位


@pytest.mark.parametrize("shop_id", list(SHOP_PLATFORM_MAP.keys()))
def test_shop_login_block_complete(cfg, shop_id):
    """每个店铺都有完整 login 块：url + 账号/密码选择器 + 提交按钮。"""
    login = cfg.shops[shop_id].selectors.get("login", {})
    assert login.get("url"), f"{shop_id} login.url missing"
    assert login.get("username_sel"), f"{shop_id} login.username_sel missing"
    assert login.get("password_sel"), f"{shop_id} login.password_sel missing"
    assert login.get("submit_sel"), f"{shop_id} login.submit_sel missing"


@pytest.mark.parametrize("shop_id", list(SHOP_PLATFORM_MAP.keys()))
def test_shop_risk_block(cfg, shop_id):
    """每个店铺都有风控信号配置（restriction_selectors 或 restriction_texts）。"""
    risk = cfg.shops[shop_id].selectors.get("risk", {})
    assert risk.get("restriction_texts"), f"{shop_id} risk.restriction_texts missing"
    assert risk.get("restriction_selectors"), f"{shop_id} risk.restriction_selectors missing"


@pytest.mark.parametrize("shop_id", list(SHOP_PLATFORM_MAP.keys()))
def test_shop_listing_block(cfg, shop_id):
    """每个店铺都有 listing 块含 publish_path/list_path/category/fields/submit_btn。"""
    listing = cfg.shops[shop_id].selectors.get("listing", {})
    assert listing.get("publish_path"), f"{shop_id} listing.publish_path missing"
    assert listing.get("list_path"), f"{shop_id} listing.list_path missing"
    assert listing.get("category"), f"{shop_id} listing.category missing"
    assert listing.get("fields"), f"{shop_id} listing.fields missing"
    assert listing.get("submit_btn"), f"{shop_id} listing.submit_btn missing"


# ---- get_listing_skill 路由 ----

@pytest.mark.parametrize("shop_id,platform", list(SHOP_PLATFORM_MAP.items()))
def test_get_listing_skill_routes_correctly(shop_id, platform):
    """get_listing_skill 根据店铺 platform 字段返回对应子类实例。"""
    skill = get_listing_skill(shop_id)
    expected_cls = EXPECTED_PLATFORMS[platform]
    assert isinstance(skill, expected_cls)


# ---- 平台特有配置校验 ----

def test_taobao_has_form_iframe(cfg):
    """淘宝配置含 form_iframe（千牛 iframe 表单）。"""
    listing = cfg.shops["shop_taobao"].selectors["listing"]
    assert listing.get("form_iframe")
    assert listing["category"].get("level_selectors"), "taobao should use level_selectors"


def test_pinduoduo_has_search_category_and_promise(cfg):
    """拼多多配置：搜索式类目 + 承诺函勾选。"""
    listing = cfg.shops["shop_pinduoduo"].selectors["listing"]
    assert listing["category"].get("search_input"), "pinduoduo should use search_input"
    assert listing.get("agree_checkbox"), "pinduoduo should have agree_checkbox"
    # 双规格 SKU 字段
    sku = listing["sku"]
    assert sku.get("spec_name_1") and sku.get("spec_name_2")
    assert sku.get("spec_values_1") and sku.get("spec_values_2")


def test_douyin_has_iframe_and_required_attrs(cfg):
    """抖音配置：iframe + 必填属性兜底。"""
    listing = cfg.shops["shop_douyin"].selectors["listing"]
    assert listing.get("form_iframe"), "douyin should have form_iframe"
    assert listing["category"].get("search_input")
    assert listing.get("required_attrs"), "douyin should have required_attrs"
    assert listing.get("agree_checkbox")


def test_jingdong_has_iframe_and_confirm_btn(cfg):
    """京东配置：iframe + 三级类目 + 二次确认按钮。"""
    listing = cfg.shops["shop_jingdong"].selectors["listing"]
    assert listing.get("form_iframe")
    assert listing["category"].get("level_selectors"), "jingdong should use level_selectors"
    assert listing.get("agree_checkbox")
    assert listing.get("confirm_btn"), "jingdong should have confirm_btn for二次确认"


# ---- parse_spec_dims 维度拆分 ----

def test_parse_spec_dims_basic():
    assert parse_spec_dims("红色-M") == ["红色", "M"]


def test_parse_spec_dims_three_dims():
    assert parse_spec_dims("红色-M-棉") == ["红色", "M", "棉"]


def test_parse_spec_dims_empty():
    assert parse_spec_dims("") == []
    assert parse_spec_dims(None) == []


def test_parse_spec_dims_custom_sep():
    assert parse_spec_dims("红色|M", sep="|") == ["红色", "M"]


def test_parse_spec_dims_strips_whitespace():
    assert parse_spec_dims(" 红色 - M ") == ["红色", "M"]


# ---- build_listing_plan 在各平台配置下能产出计划 ----

def _material():
    return {
        "title": "测试商品标题" * 5,
        "image_urls": ["http://x/a.jpg", "http://x/b.jpg"],
        "spec_params": {"品牌": "示例", "产地": "中国"},
        "detail_text": "详情描述文本",
        "skus": [{"sku_code": "S1", "spec": "红色-M", "cost": 50, "stock": 10}],
    }


@pytest.mark.parametrize("shop_id", list(SHOP_PLATFORM_MAP.keys()))
def test_build_listing_plan_for_each_platform(cfg, shop_id):
    """每个平台配置都能驱动 build_listing_plan 产出结构化计划。"""
    listing_cfg = cfg.shops[shop_id].selectors["listing"]
    plan = build_listing_plan(_material(), [{"sku": "S1", "price": 67.5, "stock": 10,
                                              "spec": "红色-M"}], listing_cfg)
    assert plan["submit"]
    assert plan["category"] is not None
    assert len(plan["text_fields"]) >= 1    # 至少有 title
    # 图片计划
    assert any(img["urls"] for img in plan["images"]) or len(plan["images"]) == 0


def test_build_listing_plan_respects_jingdong_title_max(cfg):
    """京东标题上限 50 字，超出应截断。"""
    listing_cfg = cfg.shops["shop_jingdong"].selectors["listing"]
    mat = _material()
    mat["title"] = "标题" * 30   # 60 字
    plan = build_listing_plan(mat, [], listing_cfg)
    tf = {f["selector"]: f for f in plan["text_fields"]}
    title_sel = listing_cfg["fields"]["title"]["selector"]
    assert len(tf[title_sel]["value"]) == 50
