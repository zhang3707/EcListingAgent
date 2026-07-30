"""店铺配置管理 + 风控状态接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from config.settings import get_config, reload_config
from data.repositories.shop_repo import ShopRepo

router = APIRouter()


@router.get("/shops")
def list_shops():
    return [
        {"shop_id": s.shop_id, "shop_name": s.shop_name, "platform": s.platform,
         "base_url": s.base_url}
        for s in get_config().shops.values()
    ]


@router.get("/shops/{shop_id}")
def get_shop(shop_id: str):
    shop = get_config().shops.get(shop_id)
    if not shop:
        raise HTTPException(404, f"shop not found: {shop_id}")
    repo = ShopRepo()
    return {
        "shop_id": shop.shop_id,
        "shop_name": shop.shop_name,
        "platform": shop.platform,
        "base_url": shop.base_url,
        "price_strategy": shop.price_strategy,
        "risk_status": repo.get_risk_status(shop_id),
        "login_count_today": _safe_login_count(repo, shop_id),
    }


@router.post("/shops/reload")
def reload_shops():
    """店铺配置文件变更后强制重载。"""
    cfg = reload_config()
    return {"shops": len(cfg.shops)}


@router.get("/shops/{shop_id}/risk")
def get_risk(shop_id: str):
    """查询店铺风控状态。"""
    _get_shop_or_404(shop_id)
    return {"shop_id": shop_id, "risk_status": ShopRepo().get_risk_status(shop_id)}


@router.post("/shops/{shop_id}/risk/reset")
def reset_risk(shop_id: str):
    """重置店铺风控状态为 normal（人工解除限制后调用）。"""
    _get_shop_or_404(shop_id)
    ShopRepo().set_risk_status(shop_id, "normal")
    return {"ok": True, "shop_id": shop_id, "risk_status": "normal"}


def _safe_login_count(repo: ShopRepo, shop_id: str) -> int:
    """读取今日登录次数，DB 未初始化时返回 0 不阻断。"""
    try:
        with __import__("data.db", fromlist=["session_scope"]).session_scope() as s:
            row = s.get(__import__("data.models", fromlist=["Shop"]).Shop, shop_id)
            return row.login_count_today if row else 0
    except Exception:
        return 0


def _get_shop_or_404(shop_id: str):
    shop = get_config().shops.get(shop_id)
    if not shop:
        raise HTTPException(404, f"shop not found: {shop_id}")
    return shop
