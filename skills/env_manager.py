"""5.2.6 环境管理 Skill：浏览器环境创建/启动/回收/Cookie 持久化。"""
from __future__ import annotations

import logging

from engine.browser import build_browser_env
from skills.base import BaseSkill, SkillResult
from data.repositories.shop_repo import ShopRepo

logger = logging.getLogger(__name__)


class EnvManagerSkill(BaseSkill):
    name = "env_manager"

    async def execute(self, shop_id: str, action: str = "start", **_) -> SkillResult:
        if action == "start":
            return await self._start(shop_id)
        if action == "recycle":
            return await self._recycle()
        if action == "reset":
            return await self._reset(shop_id)
        return self._fatal(f"unknown action: {action}", "ENV_2001")

    async def _start(self, shop_id: str) -> SkillResult:
        # 风控前置校验
        if ShopRepo().get_risk_status(shop_id) == "limited":
            return self._human(f"shop {shop_id} is risk-limited", "RISK_3001")
        try:
            env = await build_browser_env(shop_id)
            return self._ok({"browser_env": env})
        except Exception as e:
            return self._retry(f"env start failed: {e}", "ENV_1002")

    async def check_login_state(self) -> bool:
        """访问商家后台首页，检测是否跳转登录页。"""
        if not self.browser:
            return False
        shop = ShopRepo().get(self.browser.shop_id)
        if not shop:
            return False
        page = self.browser.page or await self.browser.new_page()
        try:
            await page.goto(f"{shop.base_url}{shop.selectors.get('home_path', '/home')}",
                            wait_until="domcontentloaded")
            login_pattern = shop.selectors.get("login_url_pattern", "/login")
            return login_pattern not in page.url
        except Exception as e:
            logger.warning("check login state failed: %s", e)
            return False

    async def login(self) -> SkillResult:
        """配置驱动登录：按 shop.selectors.login 块走 URL→账号→密码→提交。

        login 块字段（全部可选，缺省跳过该步）：
          url          : 登录页 URL（相对 base_url 或绝对）
          username_sel : 账号输入框选择器
          password_sel : 密码输入框选择器
          submit_sel   : 提交按钮选择器
          switch_tab_sel: 切换到「账号密码登录」标签的选择器（部分平台默认扫码）
        验证码（滑块/短信）由后续 captcha 节点处理，本节点只负责表单填充与提交。
        """
        from engine.humanize import human_click, human_type, random_sleep, ElementNotFoundError

        shop = ShopRepo().get(self.browser.shop_id) if self.browser else None
        if not shop:
            return self._fatal("shop not found", "ENV_2002")
        if not ShopRepo().can_login(shop.shop_id,
                                    self.config.captcha.get("max_login_per_day", 1)):
            return self._human("login quota exceeded today", "ENV_3001")

        login_cfg = shop.selectors.get("login", {}) or {}
        page = self.browser.page or await self.browser.new_page()

        try:
            # 1. 切换到账号密码登录 tab（如配置）
            switch_sel = login_cfg.get("switch_tab_sel")
            if switch_sel:
                try:
                    await human_click(page, switch_sel)
                    await random_sleep(0.6, 0.2)
                except (ElementNotFoundError, Exception) as e:
                    logger.debug("login switch tab skip: %s", e)

            # 2. 跳到登录页（仅当显式配置 url 且当前不在登录页）
            url = login_cfg.get("url")
            if url:
                full = url if url.startswith("http") else f"{shop.base_url}{url}"
                if full not in page.url:
                    await page.goto(full, wait_until="domcontentloaded")
                    await random_sleep(0.8, 0.2)
                    # 切换 tab 可能在跳转后再次出现
                    if switch_sel:
                        try:
                            await human_click(page, switch_sel)
                            await random_sleep(0.4, 0.1)
                        except (ElementNotFoundError, Exception):
                            pass

            # 3. 填账号密码
            acct = shop.account or {}
            username = acct.get("username", "")
            password = acct.get("password", "")
            if username and login_cfg.get("username_sel"):
                try:
                    await human_type(page, login_cfg["username_sel"], username)
                    await random_sleep(0.4, 0.1)
                except (ElementNotFoundError, Exception) as e:
                    logger.warning("login fill username failed: %s", e)
                    ShopRepo().record_login(shop.shop_id)
                    return self._retry(f"login username fill failed: {e}", "ENV_1003")
            if password and login_cfg.get("password_sel"):
                try:
                    await human_type(page, login_cfg["password_sel"], password)
                    await random_sleep(0.4, 0.1)
                except (ElementNotFoundError, Exception) as e:
                    logger.warning("login fill password failed: %s", e)
                    ShopRepo().record_login(shop.shop_id)
                    return self._retry(f"login password fill failed: {e}", "ENV_1004")

            # 4. 提交（验证码由 captcha 节点处理）
            if login_cfg.get("submit_sel"):
                try:
                    await human_click(page, login_cfg["submit_sel"])
                    await random_sleep(1.2, 0.3)
                except (ElementNotFoundError, Exception) as e:
                    logger.warning("login submit failed: %s", e)
                    ShopRepo().record_login(shop.shop_id)
                    return self._retry(f"login submit failed: {e}", "ENV_1005")

            ShopRepo().record_login(shop.shop_id)
            return self._ok({"logged_in": True})
        except Exception as e:
            logger.exception("login unexpected error")
            ShopRepo().record_login(shop.shop_id)
            return self._retry(f"login unexpected: {e}", "ENV_1006")

    async def _recycle(self) -> SkillResult:
        if self.browser:
            try:
                await self.browser.close()
            except Exception as e:
                logger.warning("browser close failed: %s", e)
        return self._ok({"recycled": True})

    async def _reset(self, shop_id: str) -> SkillResult:
        """清空 profile 目录，下次启动重新登录。"""
        import shutil
        from pathlib import Path
        shop = ShopRepo().get(shop_id)
        profile = Path(shop.fingerprint.get("profile_dir",
                       f"data_persist/browser_profiles/{shop_id}"))
        if profile.exists():
            shutil.rmtree(profile, ignore_errors=True)
        return self._ok({"reset": True})
