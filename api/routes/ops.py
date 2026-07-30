"""运维接口：飞书补偿触发 + 健康检查。"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from config.settings import get_config

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/feishu/compensate")
def compensate_feishu():
    """触发飞书归档补偿：重试本地落盘的失败记录。

    定时任务或人工触发，返回补偿/死信/剩余计数。
    """
    from integrations.feishu.bitable import compensate_fallback
    try:
        result = compensate_fallback(get_config().feishu)
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("feishu compensate failed")
        return {"ok": False, "error": str(e)}


@router.get("/health/detailed")
def health_detailed():
    """详细健康检查：DB / MinIO / 飞书配置 连通性。"""
    checks = {}

    # DB 连通性
    try:
        from data.db import get_engine
        with get_engine().connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["postgres"] = {"ok": True}
    except Exception as e:
        checks["postgres"] = {"ok": False, "error": str(e)}

    # MinIO 连通性
    try:
        from data.minio_client import get_minio_client
        cli = get_minio_client()
        cli.list_buckets()
        checks["minio"] = {"ok": True}
    except Exception as e:
        checks["minio"] = {"ok": False, "error": str(e)}

    # 飞书配置完整性
    try:
        feishu = get_config().feishu
        required = ["app_id", "app_secret", "app_token",
                    "table_id_task", "table_id_sku", "table_id_log"]
        missing = [k for k in required if not feishu.get(k)
                   or feishu[k].startswith("${")]
        checks["feishu"] = {"ok": not missing, "missing": missing}
    except Exception as e:
        checks["feishu"] = {"ok": False, "error": str(e)}

    all_ok = all(c.get("ok") for c in checks.values())
    return {"ok": all_ok, "checks": checks}
