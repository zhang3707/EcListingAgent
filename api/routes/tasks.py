"""任务触发、查询、取消与回调接口。"""
from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.runner import _arun_task, resume_with_sms_code
from data.repositories.task_repo import TaskRepo

router = APIRouter()
logger = logging.getLogger(__name__)

# 进程内任务句柄，用于查询运行态与取消（inline 模式）
_running: dict[str, asyncio.Task] = {}


class TaskCreateReq(BaseModel):
    product_code: str
    target_shop: str
    callback_url: str = ""          # 任务完成后 POST 结果到此 URL（可选）


class SmsResumeReq(BaseModel):
    code: str


def _execution_mode() -> str:
    """执行模式：inline（API 进程内执行）或 worker（仅建记录，worker 容器轮询）。"""
    return os.environ.get("EXECUTION_MODE", "inline").lower()


@router.post("/tasks")
async def create_task(req: TaskCreateReq):
    shop_cfg = _get_shop_or_404(req.target_shop)
    task_id = TaskRepo().create(
        req.product_code, req.target_shop,
        callback_url=req.callback_url,
    )
    mode = _execution_mode()
    if mode == "worker":
        # 容器模式：仅创建记录，由 worker 容器轮询执行
        logger.info("[api] task %s created (worker mode, pending)", task_id)
        return {"task_id": task_id, "status": "待执行", "execution": "worker"}
    # inline 模式：进程内异步执行
    task = asyncio.create_task(_arun_task(task_id, req.product_code, req.target_shop))
    _running[task_id] = task
    return {"task_id": task_id, "status": "已提交", "execution": "inline"}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    t = TaskRepo().get(task_id)
    if not t:
        raise HTTPException(404, "task not found")
    running = task_id in _running and not _running[task_id].done()
    return {**t, "running": running}


@router.get("/tasks")
def list_tasks(limit: int = 50, status: str = ""):
    if status:
        return TaskRepo().list_by_status(status, limit)
    return TaskRepo().list_recent(limit)


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str, req: SmsResumeReq):
    """短信验证码人工协同：运营人员回复后恢复挂起任务。"""
    if not TaskRepo().get(task_id):
        raise HTTPException(404, "task not found")
    task = asyncio.create_task(asyncio.to_thread(resume_with_sms_code, task_id, req.code))
    _running[task_id] = task
    return {"ok": True, "task_id": task_id}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """取消运行中任务（inline 模式有效；worker 模式需 worker 配合）。

    取消已完成的任务是 no-op。
    """
    t = TaskRepo().get(task_id)
    if not t:
        raise HTTPException(404, "task not found")
    task = _running.get(task_id)
    cancelled = False
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        cancelled = True
    TaskRepo().update_status(task_id, "失败", error_msg="用户取消", finished=True)
    _running.pop(task_id, None)
    return {"ok": True, "task_id": task_id, "cancelled": cancelled}


@router.get("/tasks/stats/summary")
def task_stats():
    """任务统计聚合：按状态分组计数 + 近期成功率。"""
    from collections import Counter
    recent = TaskRepo().list_recent(500)
    counter = Counter(t.get("status", "") for t in recent)
    total = len(recent)
    success = counter.get("成功", 0)
    return {
        "total": total,
        "by_status": dict(counter),
        "success_rate": (success / total) if total else 0.0,
    }


def _get_shop_or_404(shop_id: str):
    from config.settings import get_config
    shop = get_config().shops.get(shop_id)
    if not shop:
        raise HTTPException(404, f"shop not found: {shop_id}")
    return shop
