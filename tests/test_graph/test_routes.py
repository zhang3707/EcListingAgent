"""条件路由逻辑测试。"""
from agent.routes import route_login, route_captcha, route_verify


def test_route_login():
    assert route_login({"login_status": True}) == "logged_in"
    assert route_login({"login_status": False}) == "need_login"


def test_route_captcha_ok():
    assert route_captcha({"error_msg": ""}) == "ok"


def test_route_captcha_sms_human():
    state = {"error_msg": "sms timeout", "captcha_type": "sms"}
    assert route_captcha(state) == "human"


def test_route_captcha_slide_fail():
    state = {"error_msg": "slide failed", "captcha_type": "slide"}
    assert route_captcha(state) == "fail"


def test_route_verify_success():
    assert route_verify({"shelf_result": {"verified": True}}) == "success"


def test_route_verify_retry_then_fail():
    state = {"shelf_result": {"verified": False}, "retry_count": 0}
    assert route_verify(state) == "retry"
    assert state["retry_count"] == 1
    state = {"shelf_result": {"verified": False}, "retry_count": 3}
    assert route_verify(state) == "fail"
