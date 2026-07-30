"""任务仓储：创建、查询、状态更新。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from data.db import session_scope
from data.models import Task, RunLog


class TaskRepo:
    def create(self, product_code: str, target_shop: str, operator: str = "system",
               callback_url: str = "") -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        with session_scope() as s:
            s.add(Task(
                task_id=task_id,
                product_code=product_code,
                target_shop=target_shop,
                status="待执行",
                operator=operator,
                extra={"callback_url": callback_url} if callback_url else {},
            ))
        return task_id

    def get_callback_url(self, task_id: str) -> str:
        """读取任务回调 URL（存在 extra.callback_url）。"""
        with session_scope() as s:
            t = s.get(Task, task_id)
            if not t or not t.extra:
                return ""
            return (t.extra or {}).get("callback_url", "")

    def get(self, task_id: str) -> Optional[dict]:
        with session_scope() as s:
            t = s.get(Task, task_id)
            if not t:
                return None
            return {
                "task_id": t.task_id,
                "product_code": t.product_code,
                "target_shop": t.target_shop,
                "status": t.status,
                "platform_item_id": t.platform_item_id,
                "sku_count": t.sku_count,
                "error_msg": t.error_msg,
                "retry_count": t.retry_count,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            }

    def update_status(self, task_id: str, status: str, error_msg: str = "",
                      platform_item_id: str | None = None,
                      sku_count: int | None = None,
                      retry_count: int | None = None,
                      finished: bool = False):
        with session_scope() as s:
            t = s.get(Task, task_id)
            if not t:
                return
            t.status = status
            if error_msg:
                t.error_msg = error_msg
            if platform_item_id is not None:
                t.platform_item_id = platform_item_id
            if sku_count is not None:
                t.sku_count = sku_count
            if retry_count is not None:
                t.retry_count = retry_count
            if finished:
                t.finished_at = datetime.utcnow()

    def list_recent(self, limit: int = 50) -> list[dict]:
        with session_scope() as s:
            rows = s.execute(
                select(Task).order_by(Task.created_at.desc()).limit(limit)
            ).scalars().all()
            return [self._to_dict(t) for t in rows]

    def claim_next_pending(self, shop_id: str) -> str | None:
        """原子领取指定店铺最早一个待执行任务，标记为执行中。

        单店铺单 worker 容器模型下不会并发抢占；事务内 select+update 保证安全。
        返回 task_id，无待执行任务返回 None。
        """
        with session_scope() as s:
            row = s.execute(
                select(Task)
                .where(Task.target_shop == shop_id, Task.status == "待执行")
                .order_by(Task.created_at.asc())
                .limit(1)
            ).scalars().first()
            if not row:
                return None
            row.status = "执行中"
            return row.task_id

    def list_by_status(self, status: str, limit: int = 100) -> list[dict]:
        with session_scope() as s:
            rows = s.execute(
                select(Task)
                .where(Task.status == status)
                .order_by(Task.created_at.desc())
                .limit(limit)
            ).scalars().all()
            return [self._to_dict(t) for t in rows]

    def append_log(self, task_id: str, idx: int, node: str, status: str, detail: str = ""):
        with session_scope() as s:
            s.add(RunLog(
                id=f"{task_id}-{idx}",
                task_id=task_id,
                node=node,
                status=status,
                detail=detail,
            ))

    @staticmethod
    def _to_dict(t: Task) -> dict:
        return {
            "task_id": t.task_id,
            "product_code": t.product_code,
            "target_shop": t.target_shop,
            "status": t.status,
            "platform_item_id": t.platform_item_id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
