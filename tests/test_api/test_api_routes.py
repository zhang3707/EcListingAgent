"""API 接口测试：用 TestClient + mock DB 依赖，验证路由逻辑与响应格式。

不依赖真实 postgres/minio，全部仓储方法 mock。
任务执行用 worker 模式（EXECUTION_MODE=worker）避免触发真实 graph。
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """构造测试客户端，worker 模式避免 inline 执行。

    用 yield 而非 return：保证 patch.dict 的 EXECUTION_MODE=worker 在整个测试期间生效，
    否则 with 上下文会在 fixture 返回时立即退出，请求时已还原为 inline。
    """
    with patch.dict("os.environ", {"EXECUTION_MODE": "worker"}):
        from api.server import create_app
        yield TestClient(create_app())


@pytest.fixture
def cfg():
    from config.settings import reload_config
    return reload_config()


# ---- /health ----

def test_health_basic(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---- /api/tasks ----

def test_create_task_worker_mode(client, cfg):
    """worker 模式：只建记录，不执行，返回待执行。"""
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.create.return_value = "task_abc"
        r = client.post("/api/tasks", json={
            "product_code": "P1", "target_shop": "shop_taobao",
        })
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == "task_abc"
    assert body["status"] == "待执行"
    assert body["execution"] == "worker"
    MT.return_value.create.assert_called_once()


def test_create_task_with_callback_url(client, cfg):
    """callback_url 透传到 TaskRepo.create。"""
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.create.return_value = "task_cb"
        r = client.post("/api/tasks", json={
            "product_code": "P1", "target_shop": "shop_taobao",
            "callback_url": "https://biz.example.com/cb",
        })
    assert r.status_code == 200
    MT.return_value.create.assert_called_once_with(
        "P1", "shop_taobao", callback_url="https://biz.example.com/cb",
    )


def test_create_task_shop_not_found_404(client, cfg):
    r = client.post("/api/tasks", json={
        "product_code": "P1", "target_shop": "shop_nonexist",
    })
    assert r.status_code == 404


def test_get_task(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.get.return_value = {
            "task_id": "T1", "status": "成功", "product_code": "P1",
        }
        r = client.get("/api/tasks/T1")
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"] == "T1"
    assert body["running"] is False


def test_get_task_not_found_404(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.get.return_value = None
        r = client.get("/api/tasks/nope")
    assert r.status_code == 404


def test_list_tasks_with_status_filter(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.list_by_status.return_value = [{"task_id": "T1"}]
        r = client.get("/api/tasks?status=待执行")
    assert r.status_code == 200
    assert r.json() == [{"task_id": "T1"}]
    MT.return_value.list_by_status.assert_called_once_with("待执行", 50)


def test_list_tasks_no_filter(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.list_recent.return_value = [{"task_id": "T1"}]
        r = client.get("/api/tasks")
    assert r.status_code == 200
    MT.return_value.list_recent.assert_called_once()


def test_task_stats(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.list_recent.return_value = [
            {"status": "成功"}, {"status": "成功"}, {"status": "失败"},
        ]
        r = client.get("/api/tasks/stats/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["by_status"]["成功"] == 2
    assert body["by_status"]["失败"] == 1
    assert body["success_rate"] == pytest.approx(2 / 3)


def test_cancel_task(client):
    """取消任务：无运行中句柄时仍标记失败（用户取消）。"""
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.get.return_value = {"task_id": "T1", "status": "执行中"}
        r = client.post("/api/tasks/T1/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    MT.return_value.update_status.assert_called_once()
    args = MT.return_value.update_status.call_args
    assert args.args[1] == "失败"
    assert "用户取消" in args.kwargs.get("error_msg", "")


def test_cancel_task_not_found_404(client):
    with patch("api.routes.tasks.TaskRepo") as MT:
        MT.return_value.get.return_value = None
        r = client.post("/api/tasks/nope/cancel")
    assert r.status_code == 404


# ---- /api/shops ----

def test_list_shops(client, cfg):
    r = client.get("/api/shops")
    assert r.status_code == 200
    shops = r.json()
    assert len(shops) >= 4   # 含 4 真实平台 + 示例
    ids = [s["shop_id"] for s in shops]
    assert "shop_taobao" in ids
    assert "shop_pinduoduo" in ids


def test_get_shop_detail(client, cfg):
    with patch("api.routes.shops.ShopRepo") as MS:
        MS.return_value.get_risk_status.return_value = "normal"
        r = client.get("/api/shops/shop_taobao")
    assert r.status_code == 200
    body = r.json()
    assert body["shop_id"] == "shop_taobao"
    assert body["platform"] == "taobao"
    assert body["risk_status"] == "normal"


def test_get_shop_risk(client, cfg):
    with patch("api.routes.shops.ShopRepo") as MS:
        MS.return_value.get_risk_status.return_value = "limited"
        r = client.get("/api/shops/shop_taobao/risk")
    assert r.status_code == 200
    body = r.json()
    assert body["risk_status"] == "limited"


def test_reset_shop_risk(client, cfg):
    with patch("api.routes.shops.ShopRepo") as MS:
        r = client.post("/api/shops/shop_taobao/risk/reset")
    assert r.status_code == 200
    body = r.json()
    assert body["risk_status"] == "normal"
    MS.return_value.set_risk_status.assert_called_once_with("shop_taobao", "normal")


def test_reset_risk_shop_not_found_404(client, cfg):
    r = client.post("/api/shops/shop_nonexist/risk/reset")
    assert r.status_code == 404


def test_reload_shops(client):
    with patch("api.routes.shops.reload_config") as MR:
        MR.return_value.shops = {"a": 1, "b": 2}
        r = client.post("/api/shops/reload")
    assert r.status_code == 200
    assert r.json()["shops"] == 2


# ---- /api/feishu/compensate ----

def test_feishu_compensate_success(client):
    with patch("integrations.feishu.bitable.compensate_fallback") as MC:
        MC.return_value = {"compensated": 3, "dead_lettered": 0, "remaining": 0}
        r = client.post("/api/feishu/compensate")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["compensated"] == 3


def test_feishu_compensate_failure(client):
    with patch("integrations.feishu.bitable.compensate_fallback") as MC:
        MC.side_effect = RuntimeError("api down")
        r = client.post("/api/feishu/compensate")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "api down" in body["error"]


# ---- /api/health/detailed ----

def test_health_detailed(client):
    """详细健康检查：各组件 ok 状态返回。"""
    with patch("data.db.get_engine") as ME, \
         patch("data.minio_client.get_minio_client") as MM:
        ME.return_value.connect.return_value.__enter__.return_value.execute.return_value = 1
        MM.return_value.list_buckets.return_value = []
        r = client.get("/api/health/detailed")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    assert "postgres" in body["checks"]
    assert "minio" in body["checks"]
    assert "feishu" in body["checks"]
