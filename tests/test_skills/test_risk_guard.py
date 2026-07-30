"""风控熔断纯逻辑测试：evaluate_risk + route_risk + route_env。"""
from skills.risk_guard import evaluate_risk, DEFAULT_THRESHOLDS
from agent.routes import route_risk, route_env


# ---- evaluate_risk ----

def test_no_risk_when_clean():
    d = evaluate_risk({"captcha_fail_count": 0, "login_fail_count": 0},
                      {"restriction_text": None, "restriction_element": False})
    assert d["risk"] is False


def test_restriction_text_triggers_immediately():
    d = evaluate_risk({}, {"restriction_text": "账号已被限制", "restriction_element": False})
    assert d["risk"] is True
    assert d["code"] == "RISK_3001"
    assert "账号已被限制" in d["reason"]


def test_restriction_element_triggers():
    d = evaluate_risk({}, {"restriction_text": None, "restriction_element": True})
    assert d["risk"] is True
    assert d["code"] == "RISK_3002"


def test_captcha_threshold_triggers():
    d = evaluate_risk(
        {"captcha_fail_count": DEFAULT_THRESHOLDS["max_captcha_per_session"], "login_fail_count": 0},
        {"restriction_text": None, "restriction_element": False},
    )
    assert d["risk"] is True
    assert d["code"] == "RISK_3003"


def test_login_threshold_triggers():
    d = evaluate_risk(
        {"captcha_fail_count": 0, "login_fail_count": DEFAULT_THRESHOLDS["max_login_fail"]},
        {"restriction_text": None, "restriction_element": False},
    )
    assert d["risk"] is True
    assert d["code"] == "RISK_3004"


def test_custom_thresholds_override():
    d = evaluate_risk(
        {"captcha_fail_count": 2, "login_fail_count": 0},
        {"restriction_text": None, "restriction_element": False},
        {"max_captcha_per_session": 2},
    )
    assert d["risk"] is True


def test_restriction_overrides_thresholds_priority():
    """页面限制文案优先于计数阈值，且即使计数为 0 也熔断。"""
    d = evaluate_risk(
        {"captcha_fail_count": 0, "login_fail_count": 0},
        {"restriction_text": "店铺已被冻结", "restriction_element": False},
    )
    assert d["risk"] is True
    assert d["code"] == "RISK_3001"


# ---- route_risk / route_env ----

def test_route_risk_ok():
    assert route_risk({"risk_triggered": False}) == "ok"


def test_route_risk_abort():
    assert route_risk({"risk_triggered": True}) == "abort"


def test_route_env_ok():
    from engine.browser import BrowserEnv
    assert route_env({"browser_env": object()}) == "ok"


def test_route_env_abort_when_no_browser():
    assert route_env({}) == "abort"
