"""条件路由：根据状态决定下一节点。"""
from __future__ import annotations

from agent.state import TaskState


def route_env(state: TaskState) -> str:
    """环境启动后：成功→登录校验，失败/风控→归档终止。"""
    if state.get("browser_env"):
        return "ok"
    return "abort"


def route_login(state: TaskState) -> str:
    return "logged_in" if state.get("login_status") else "need_login"


def route_captcha(state: TaskState) -> str:
    # 验证码节点成功则 error_msg 为空
    if not state.get("error_msg"):
        return "ok"
    # 短信验证码走人机协同（interrupt 挂起），失败也先同步挂起态
    return "human" if state.get("captcha_type") == "sms" else "fail"


def route_risk(state: TaskState) -> str:
    """风控守卫后：未触发→进入上架，触发→归档终止。"""
    return "ok" if not state.get("risk_triggered") else "abort"


def route_verify(state: TaskState) -> str:
    result = state.get("shelf_result", {})
    if result.get("verified"):
        return "success"
    retry_count = state.get("retry_count", 0)
    if retry_count < 3:
        state["retry_count"] = retry_count + 1
        return "retry"
    return "fail"

