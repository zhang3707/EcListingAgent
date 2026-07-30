"""浏览器环境封装：独立用户数据目录、代理、指纹、Cookie 持久化。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext

from config.settings import get_config
from engine.fingerprint import Fingerprint, FingerprintManager
from engine.stealth import apply_stealth, LAUNCH_ARGS


class BrowserEnv:
    """单店铺隔离浏览器环境。"""

    def __init__(self, profile_dir: Path, fingerprint: Fingerprint,
                 proxy: dict | None = None, headless: bool = False):
        self.profile_dir = Path(profile_dir)
        self.fingerprint = fingerprint
        self.proxy = proxy
        self.headless = headless
        self.shop_id: Optional[str] = fingerprint.shop_id
        self._pw = None
        self._context: Optional[BrowserContext] = None

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            raise RuntimeError("browser not started, call start() first")
        return self._context

    async def start(self) -> "BrowserEnv":
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        launch_kwargs = dict(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            args=LAUNCH_ARGS,
            user_agent=self.fingerprint.user_agent,
            viewport=self.fingerprint.viewport,
            locale=self.fingerprint.locale,
            timezone_id=self.fingerprint.timezone_id,
            color_scheme="light",
            ignore_default_args=["--enable-automation"],
        )
        if self.proxy and self.proxy.get("server"):
            launch_kwargs["proxy"] = self.proxy
        self._context = await self._pw.chromium.launch_persistent_context(**launch_kwargs)
        await apply_stealth(self._context)
        return self

    @property
    def page(self):
        """当前活动页（无则新建）。"""
        pages = self.context.pages
        return pages[0] if pages else None

    async def new_page(self):
        return await self.context.new_page()

    async def persist_cookies(self):
        """任务结束前持久化 Cookie/LocalStorage，保留登录态。"""
        if self._context:
            await self._context.storage_state(
                path=str(self.profile_dir / "storage_state.json")
            )

    async def close(self):
        try:
            if self._context:
                await self.persist_cookies()
                await self._context.close()
        finally:
            if self._pw:
                await self._pw.stop()
            self._context = None
            self._pw = None


async def build_browser_env(shop_id: str) -> BrowserEnv:
    """根据 shop_id 装配指纹、代理、用户数据目录并启动。"""
    cfg = get_config()
    shop = cfg.shops[shop_id]
    fp = FingerprintManager(Path("data_persist/fingerprints")).get(shop_id)
    proxy = None
    if shop.proxy.server:
        proxy = {
            "server": shop.proxy.server,
            "username": shop.proxy.username,
            "password": shop.proxy.password,
        }
    profile_dir = Path(shop.fingerprint.get("profile_dir",
                       f"data_persist/browser_profiles/{shop_id}"))
    env = BrowserEnv(profile_dir, fp, proxy, headless=cfg.headless)
    await env.start()
    return env
