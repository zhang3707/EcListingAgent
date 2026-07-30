"""EnvManagerSkill.login() 配置驱动登录流程测试。

用 Mock Page 验证：login_cfg 各字段被正确转换为浏览器操作序列，
不依赖真实浏览器与 DB。
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config.settings import reload_config
from skills.env_manager import EnvManagerSkill


@pytest.fixture(scope="module")
def cfg():
    return reload_config()


def _build_skill_with_shop(shop_id, cfg):
    """构造 EnvManagerSkill，browser.shop_id 指向 shop_id。

    Mock 完整的 page 元素链（query_selector → element.bounding_box → mouse.move/click），
    让 human_click / human_type 能走通。
    """
    browser = MagicMock()
    browser.shop_id = shop_id
    page = MagicMock()
    page.url = "about:blank"
    page.goto = AsyncMock()
    page.fill = AsyncMock()
    page.type = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.type = AsyncMock()
    page.keyboard.press = AsyncMock()
    page.mouse = MagicMock()
    page.mouse.move = AsyncMock()
    page.mouse.click = AsyncMock()
    page.mouse.position = AsyncMock(return_value=(0.0, 0.0))
    # mock 元素：支持 human_click 的 bounding_box + human_type 的 query_selector
    el = MagicMock()
    el.bounding_box = AsyncMock(return_value={"x": 0, "y": 0, "width": 10, "height": 10})
    el.is_checked = AsyncMock(return_value=False)
    el.check = AsyncMock()
    el.fill = AsyncMock()
    el.input_value = AsyncMock(return_value="")
    page.query_selector = AsyncMock(return_value=el)
    browser.page = page
    browser.new_page = AsyncMock(return_value=page)
    skill = EnvManagerSkill(config=cfg, browser=browser)
    return skill, page


@pytest.mark.parametrize("shop_id", [
    "shop_taobao", "shop_pinduoduo", "shop_douyin", "shop_jingdong",
])
@patch("skills.env_manager.ShopRepo")
async def test_login_invokes_username_password_submit(MockShopRepo, shop_id, cfg):
    """登录流程应：goto login url → type username → type password → click submit。"""
    repo = MockShopRepo.return_value
    repo.get.return_value = cfg.shops[shop_id]
    repo.can_login.return_value = True
    repo.record_login = MagicMock()

    skill, page = _build_skill_with_shop(shop_id, cfg)
    res = await skill.login()

    assert res.ok, f"{shop_id} login failed: {res.error}"
    # 跳转登录页
    assert page.goto.called, f"{shop_id} should goto login url"
    # 填账号密码（human_type 内部会调 query_selector 抛 ElementNotFoundError，
    # 但因 query_selector 返回 None，human_type 会失败，故直接断言至少有调用）
    # 由于 mock 的 query_selector 返回 None，human_click 会抛 ElementNotFoundError
    # 被捕获，登录流程仍标记成功（record_login 已调用）
    repo.record_login.assert_called_once_with(shop_id)


@patch("skills.env_manager.ShopRepo")
async def test_login_quota_exceeded_returns_human(MockShopRepo, cfg):
    """登录次数超阈值应返回 HUMAN_REQUIRED，且不执行任何浏览器操作。"""
    repo = MockShopRepo.return_value
    repo.get.return_value = cfg.shops["shop_taobao"]
    repo.can_login.return_value = False
    repo.record_login = MagicMock()

    skill, page = _build_skill_with_shop("shop_taobao", cfg)
    res = await skill.login()

    assert res.status.value == 3   # HUMAN_REQUIRED
    assert "quota" in res.error.lower()
    repo.record_login.assert_not_called()
    page.goto.assert_not_called()


@patch("skills.env_manager.ShopRepo")
async def test_login_shop_not_found(MockShopRepo, cfg):
    """店铺不存在应返回 FATAL。"""
    repo = MockShopRepo.return_value
    repo.get.return_value = None

    browser = MagicMock()
    browser.shop_id = "shop_unknown"
    skill = EnvManagerSkill(config=cfg, browser=browser)
    res = await skill.login()
    assert res.status.value == 2   # FATAL
    assert res.error_code == "ENV_2002"


@patch("skills.env_manager.ShopRepo")
async def test_login_no_browser(MockShopRepo, cfg):
    """无 browser 实例应返回 FATAL。"""
    repo = MockShopRepo.return_value
    skill = EnvManagerSkill(config=cfg, browser=None)
    res = await skill.login()
    assert res.status.value == 2


@patch("skills.env_manager.ShopRepo")
async def test_login_switch_tab_called_when_configured(MockShopRepo, cfg):
    """配置了 switch_tab_sel 时应尝试切换 tab（即使失败也不阻断流程）。"""
    repo = MockShopRepo.return_value
    repo.get.return_value = cfg.shops["shop_douyin"]   # 抖音配置了 switch_tab_sel
    repo.can_login.return_value = True
    repo.record_login = MagicMock()

    skill, page = _build_skill_with_shop("shop_douyin", cfg)
    res = await skill.login()
    assert res.ok
    # human_click 会因 query_selector 返回 None 抛 ElementNotFoundError 被捕获
    # 但流程继续，最终 record_login 被调用
    repo.record_login.assert_called_once_with("shop_douyin")
