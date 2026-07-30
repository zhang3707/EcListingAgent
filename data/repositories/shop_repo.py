"""店铺仓储：DB 配置读取 + 风控状态/登录计数维护。

实际店铺参数以 YAML 为准（config/shops/*.yaml），DB 侧仅维护运行态字段
（风控状态、登录计数、最后登录时间）。
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import select

from config.settings import get_config, ShopCfg
from data.db import session_scope
from data.models import Shop


class ShopRepo:
    # ---- YAML 配置读取 ----
    def get(self, shop_id: str) -> Optional[ShopCfg]:
        return get_config().shops.get(shop_id)

    def list_all(self) -> list[ShopCfg]:
        return list(get_config().shops.values())

    # ---- 运行态 ----
    def get_risk_status(self, shop_id: str) -> str:
        with session_scope() as s:
            row = s.get(Shop, shop_id)
            return row.risk_status if row else "normal"

    def set_risk_status(self, shop_id: str, status: str):
        with session_scope() as s:
            row = s.get(Shop, shop_id)
            if not row:
                s.add(Shop(shop_id=shop_id, risk_status=status))
            else:
                row.risk_status = status

    def can_login(self, shop_id: str, max_per_day: int = 1) -> bool:
        """校验今日登录次数是否超阈值。"""
        with session_scope() as s:
            row = s.get(Shop, shop_id)
            if not row:
                return True
            today = date.today()
            last = row.last_login_at.date() if row.last_login_at else None
            if last != today:
                return True
            return row.login_count_today < max_per_day

    def record_login(self, shop_id: str):
        with session_scope() as s:
            row = s.get(Shop, shop_id)
            today = date.today()
            if not row:
                s.add(Shop(shop_id=shop_id, login_count_today=1,
                           last_login_at=datetime.utcnow()))
            else:
                last = row.last_login_at.date() if row.last_login_at else None
                row.login_count_today = 1 if last != today else row.login_count_today + 1
                row.last_login_at = datetime.utcnow()
