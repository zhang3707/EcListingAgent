"""LangGraph 工作流图构建。"""
from __future__ import annotations

from langgraph.graph import StateGraph, END

from agent.state import TaskState
from agent import nodes, routes


def build_graph(checkpointer=None):
    g: StateGraph = StateGraph(TaskState)

    # 节点注册
    g.add_node("init", nodes.init_task)
    g.add_node("erp_search", nodes.erp_material_search)
    g.add_node("sku_match", nodes.sku_price_match)
    g.add_node("env_start", nodes.start_env)
    g.add_node("login_check", nodes.check_login)
    g.add_node("login", nodes.do_login)
    g.add_node("captcha", nodes.handle_captcha)
    g.add_node("risk_guard", nodes.risk_guard)
    g.add_node("listing", nodes.do_listing)
    g.add_node("verify", nodes.verify_result)
    g.add_node("feishu_sync", nodes.sync_feishu)
    g.add_node("cleanup", nodes.cleanup)

    # 线性边
    g.set_entry_point("init")
    g.add_edge("init", "erp_search")
    g.add_edge("erp_search", "sku_match")
    g.add_edge("sku_match", "env_start")
    g.add_edge("login", "captcha")
    g.add_edge("feishu_sync", "cleanup")
    g.add_edge("cleanup", END)

    # 条件边
    # 环境启动：成功→登录校验；失败/风控→归档终止
    g.add_conditional_edges("env_start", routes.route_env, {
        "ok": "login_check",
        "abort": "feishu_sync",
    })
    # 登录校验：已登录→风控守卫；未登录→登录
    g.add_conditional_edges("login_check", routes.route_login, {
        "logged_in": "risk_guard",
        "need_login": "login",
    })
    # 验证码：通过→风控守卫；短信挂起/失败→归档
    g.add_conditional_edges("captcha", routes.route_captcha, {
        "ok": "risk_guard",
        "human": "feishu_sync",   # interrupt 挂起；人工恢复后继续
        "fail": "feishu_sync",
    })
    # 风控守卫：未触发→上架；触发→归档终止
    g.add_conditional_edges("risk_guard", routes.route_risk, {
        "ok": "listing",
        "abort": "feishu_sync",
    })
    # 上架校验：成功→归档；可重试→重试上架；不可重试→归档
    g.add_conditional_edges("verify", routes.route_verify, {
        "success": "feishu_sync",
        "retry": "listing",
        "fail": "feishu_sync",
    })

    return g.compile(checkpointer=checkpointer)
