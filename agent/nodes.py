"""工作流节点：每个节点调用对应 Skill，更新 TaskState，追加 node_trace。"""
from __future__ import annotations

import logging
from datetime import datetime

from langgraph.types import interrupt

from agent.state import TaskState, TaskStatus, CaptchaType
from config.settings import get_config
from skills import (
    EnvManagerSkill, ErpMaterialSkill, SkuPriceSkill,
    CaptchaSkill, FeishuSyncSkill, RiskGuardSkill, SkillStatus,
)
from skills.listing import get_listing_skill

logger = logging.getLogger(__name__)


def _trace(state: TaskState, node: str, status: str, extra: str = "") -> TaskState:
    state.setdefault("node_trace", []).append({
        "node": node,
        "status": status,
        "ts": datetime.utcnow().isoformat(),
        "extra": extra,
    })
    return state


def _set_status(state: TaskState, ok: bool, ok_status: str = TaskStatus.RUNNING.value):
    if not ok:
        state["status"] = state.get("status", TaskStatus.FAILED.value)


# ---- 节点实现 ----

async def init_task(state: TaskState) -> TaskState:
    state["retry_count"] = state.get("retry_count", 0)
    state["status"] = TaskStatus.RUNNING.value
    state["captcha_type"] = CaptchaType.NONE.value
    state["captcha_fail_count"] = state.get("captcha_fail_count", 0)
    state["login_fail_count"] = state.get("login_fail_count", 0)
    state["risk_triggered"] = state.get("risk_triggered", False)
    state.setdefault("node_trace", [])
    return _trace(state, "init", "ok", f"task_id={state['task_id']}")


async def erp_material_search(state: TaskState) -> TaskState:
    skill = ErpMaterialSkill(config=get_config())
    res = await skill.execute(product_code=state["product_code"])
    if not res.ok:
        state["error_msg"] = res.error or "erp search failed"
        return _trace(state, "erp_search", "fail", state["error_msg"])
    state["product_material"] = res.data["material"]
    state["error_msg"] = ""
    return _trace(state, "erp_search", "ok")


async def sku_price_match(state: TaskState) -> TaskState:
    skill = SkuPriceSkill(config=get_config())
    res = await skill.execute(
        skus=state["product_material"].get("skus", []),
        shop_id=state["target_shop"],
    )
    if not res.ok:
        state["error_msg"] = res.error or "sku match failed"
        return _trace(state, "sku_match", "fail", state["error_msg"])
    state["sku_price_list"] = res.data["sku_price_list"]
    state["error_msg"] = ""
    return _trace(state, "sku_match", "ok")


async def start_env(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config())
    res = await skill.execute(shop_id=state["target_shop"], action="start")
    if not res.ok:
        state["error_msg"] = res.error or "env start failed"
        # 店铺已风控受限 → 标记熔断
        if res.status == SkillStatus.HUMAN_REQUIRED or (res.error_code or "").startswith("RISK"):
            state["risk_triggered"] = True
            state["status"] = TaskStatus.HUMAN.value
        return _trace(state, "env_start", "fail", state["error_msg"])
    state["browser_env"] = res.data["browser_env"]
    state["error_msg"] = ""
    return _trace(state, "env_start", "ok")


async def check_login(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state.get("browser_env"))
    logged_in = await skill.check_login_state()
    state["login_status"] = logged_in
    return _trace(state, "login_check", "ok", f"login={logged_in}")


async def do_login(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state.get("browser_env"))
    res = await skill.login()
    state["login_status"] = res.ok
    if not res.ok:
        state["login_fail_count"] = state.get("login_fail_count", 0) + 1
    return _trace(state, "login", "ok" if res.ok else "fail",
                  "" if res.ok else (res.error or ""))


async def handle_captcha(state: TaskState) -> TaskState:
    """验证码处理：自动识别类型，滑块走 CV，短信走 interrupt 人机协同。"""
    skill = CaptchaSkill(config=get_config(), browser=state.get("browser_env"))
    ctype = await skill.detect_type()
    state["captcha_type"] = ctype

    if ctype == CaptchaType.NONE.value:
        state["error_msg"] = ""
        return _trace(state, "captcha", "ok", "no captcha")

    if ctype == CaptchaType.SMS.value:
        await skill.trigger_sms_send()
        skill.notify_human_for_sms(state["task_id"], state["target_shop"])
        # 挂起等待运营人员在飞书回复验证码
        code = interrupt({"task_id": state["task_id"], "wait": "sms_code"})
        res = await skill.submit_sms_code(str(code))
    else:  # slide
        res = await skill.solve_slider()

    state["error_msg"] = "" if res.ok else (res.error or "captcha fail")
    if not res.ok:
        state["captcha_fail_count"] = state.get("captcha_fail_count", 0) + 1
    return _trace(state, "captcha", "ok" if res.ok else "fail",
                  "" if res.ok else (res.error or ""))


async def risk_guard(state: TaskState) -> TaskState:
    """风控守卫：在重操作前检测风控信号，触发即熔断转人工。"""
    if not state.get("browser_env"):
        return _trace(state, "risk_guard", "skip", "no browser")
    skill = RiskGuardSkill(config=get_config(), browser=state.get("browser_env"))
    res = await skill.execute(state)
    if res.data.get("risk"):
        state["risk_triggered"] = True
        state["status"] = TaskStatus.HUMAN.value
        state["error_msg"] = res.data.get("reason", "风控触发")
        return _trace(state, "risk_guard", "risk", state["error_msg"])
    return _trace(state, "risk_guard", "ok")


async def do_listing(state: TaskState) -> TaskState:
    skill = get_listing_skill(state["target_shop"],
                              config=get_config(),
                              browser=state.get("browser_env"))
    res = await skill.execute(
        material=state["product_material"],
        sku_price_list=state["sku_price_list"],
        shop_id=state["target_shop"],
    )
    state["shelf_result"] = res.data
    state["error_msg"] = "" if res.ok else (res.error or "listing failed")
    return _trace(state, "listing", "ok" if res.ok else "fail",
                  "" if res.ok else (res.error or ""))


async def verify_result(state: TaskState) -> TaskState:
    skill = get_listing_skill(state["target_shop"],
                              config=get_config(),
                              browser=state.get("browser_env"))
    res = await skill.verify(state.get("shelf_result", {}))
    state["shelf_result"] = res.data
    state["platform_item_id"] = res.data.get("platform_item_id", "")
    return _trace(state, "verify", "ok" if res.data.get("verified") else "fail")


async def sync_feishu(state: TaskState) -> TaskState:
    skill = FeishuSyncSkill(config=get_config())
    await skill.execute(task=state)
    return _trace(state, "feishu_sync", "ok")


async def cleanup(state: TaskState) -> TaskState:
    skill = EnvManagerSkill(config=get_config(), browser=state.get("browser_env"))
    if state.get("browser_env"):
        await skill.execute(shop_id=state["target_shop"], action="recycle")
    # 终态判定
    shelf = state.get("shelf_result", {})
    if state.get("status") == TaskStatus.HUMAN.value:
        pass
    elif shelf.get("verified"):
        state["status"] = TaskStatus.SUCCESS.value
    else:
        state["status"] = TaskStatus.FAILED.value
    return _trace(state, "cleanup", "ok", f"final_status={state['status']}")
