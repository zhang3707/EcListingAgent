"""图执行入口：新任务执行 + 挂起任务恢复 + DB 状态同步 + 回调触发。"""
from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from agent.graph import build_graph
from agent.state import TaskState, TaskStatus
from data.db import get_checkpointer
from data.repositories.task_repo import TaskRepo

logger = logging.getLogger(__name__)

# 单店铺并发锁：单店铺同时仅 1 个任务，避免风控
_shop_locks: dict[str, Any] = {}


def _thread_config(task_id: str) -> dict:
    return {"configurable": {"thread_id": task_id}}


def _finalize(task_id: str, final: dict):
    """统一收尾：更新 DB 状态 + 持久化节点轨迹 + 触发回调。"""
    TaskRepo().update_status(
        task_id,
        final.get("status", TaskStatus.FAILED.value),
        error_msg=final.get("error_msg", ""),
        platform_item_id=final.get("platform_item_id") or None,
        sku_count=len(final.get("sku_price_list", [])),
        retry_count=final.get("retry_count"),
        finished=True,
    )
    for i, tr in enumerate(final.get("node_trace", [])):
        TaskRepo().append_log(task_id, i, tr.get("node", ""),
                              tr.get("status", ""), tr.get("extra", ""))
    _fire_callback(task_id, final)


def _fire_callback(task_id: str, final: dict):
    """任务完成后，若注册了 callback_url，POST 结果到业务系统。

    失败不阻断主流程（仅记日志），回调幂等性由业务系统保证。
    """
    import requests
    url = TaskRepo().get_callback_url(task_id)
    if not url:
        return
    payload = {
        "task_id": task_id,
        "status": final.get("status", TaskStatus.FAILED.value),
        "platform_item_id": final.get("platform_item_id", ""),
        "error_msg": final.get("error_msg", ""),
        "sku_count": len(final.get("sku_price_list", [])),
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        logger.info("[callback] task=%s -> %s status=%s",
                    task_id, url, r.status_code)
    except Exception as e:
        logger.warning("[callback] task=%s -> %s failed: %s", task_id, url, e)


def run_task(task_id: str, product_code: str, target_shop: str) -> dict:
    """同步执行新任务（生产环境建议包到异步 worker）。"""
    import asyncio

    async def _run():
        graph = build_graph(checkpointer=get_checkpointer())
        initial: TaskState = {
            "task_id": task_id,
            "product_code": product_code,
            "target_shop": target_shop,
            "status": TaskStatus.PENDING.value,
            "retry_count": 0,
            "node_trace": [],
        }
        TaskRepo().update_status(task_id, TaskStatus.RUNNING.value)
        final = await graph.ainvoke(initial, config=_thread_config(task_id))
        _finalize(task_id, final)
        return final

    return asyncio.run(_run())


def resume_with_sms_code(task_id: str, code: str) -> dict:
    """运营人员飞书回复验证码后调用，恢复挂起任务。"""
    import asyncio

    async def _resume():
        graph = build_graph(checkpointer=get_checkpointer())
        return await graph.ainvoke(
            Command(resume=code), config=_thread_config(task_id)
        )

    return asyncio.run(_resume())


async def _arun_task(task_id: str, product_code: str, target_shop: str) -> dict:
    """异步执行入口，供 API 层 asyncio.create_task 调用。"""
    graph = build_graph(checkpointer=get_checkpointer())
    initial: TaskState = {
        "task_id": task_id,
        "product_code": product_code,
        "target_shop": target_shop,
        "status": TaskStatus.PENDING.value,
        "retry_count": 0,
        "node_trace": [],
    }
    TaskRepo().update_status(task_id, TaskStatus.RUNNING.value)
    final = await graph.ainvoke(initial, config=_thread_config(task_id))
    _finalize(task_id, final)
    return final
