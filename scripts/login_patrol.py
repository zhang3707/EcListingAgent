"""登录态每日巡检：提前发现失效，避免任务阻塞。

可作为定时任务运行：
  python scripts/login_patrol.py
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import get_config
from data.repositories.shop_repo import ShopRepo
from engine.browser import build_browser_env
from skills.env_manager import EnvManagerSkill
from integrations.feishu.bot import FeishuBot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def check_shop(shop_id: str) -> bool:
    env = await build_browser_env(shop_id)
    try:
        skill = EnvManagerSkill(config=get_config(), browser=env)
        ok = await skill.check_login_state()
        if not ok:
            FeishuBot(get_config().feishu).notify_fail(
                "patrol", shop_id, "登录态失效，请及时处理"
            )
        return ok
    finally:
        await env.close()


async def main():
    shops = ShopRepo().list_all()
    if not shops:
        logger.warning("no shops configured")
        return
    for shop in shops:
        if ShopRepo().get_risk_status(shop.shop_id) == "limited":
            logger.info("skip risk-limited shop: %s", shop.shop_id)
            continue
        try:
            ok = await check_shop(shop.shop_id)
            logger.info("shop %s login state: %s", shop.shop_id, "ok" if ok else "INVALID")
        except Exception as e:
            logger.error("patrol shop %s failed: %s", shop.shop_id, e)


if __name__ == "__main__":
    asyncio.run(main())
