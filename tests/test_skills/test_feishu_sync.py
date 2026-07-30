"""飞书归档链路单元测试：upsert / 字段映射 / 死信 / 终态差异化 / 通知联动。

全部用 mock FeishuClient，不依赖真实网络与飞书 API。
补偿与死信用 tmp_path 隔离，不污染工作目录。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from integrations.feishu.bitable import (
    BitableWriter, compensate_fallback, DEAD_LETTER_THRESHOLD,
)
from integrations.feishu.bot import FeishuBot
from skills.feishu_sync import FeishuSyncSkill
from agent.state import TaskStatus


def _cfg(**overrides):
    base = {
        "app_id": "id", "app_secret": "secret",
        "app_token": "token",
        "table_id_task": "t_task", "table_id_sku": "t_sku",
        "table_id_log": "t_log",
    }
    base.update(overrides)
    return base


def _make_writer(cfg, mock_cli=None):
    """构造 BitableWriter，cli 替换为 mock。"""
    with patch("integrations.feishu.bitable.FeishuClient") as MockCli:
        MockCli.return_value = mock_cli or MagicMock()
        return BitableWriter(cfg)


# ---- 真 upsert ----

def test_upsert_task_creates_when_not_found(tmp_path):
    """记录不存在时走 create。"""
    cli = MagicMock()
    cli.post.side_effect = [
        {"data": {"items": []}},                  # search 返回空
        {"data": {"record_id": "r1"}},            # create 返回
    ]
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    w.upsert_task({"task_id": "T1", "product_code": "P1", "status": "执行中"})
    # 第一次 search，第二次 create
    assert cli.post.call_count == 2
    # create 调用路径
    create_call = cli.post.call_args_list[1]
    assert "/records" in create_call.args[0]
    assert "batch_create" not in create_call.args[0]


def test_upsert_task_updates_when_found(tmp_path):
    """记录已存在时走 update（put）。"""
    cli = MagicMock()
    cli.post.return_value = {"data": {"items": [{"record_id": "rid_123"}]}}
    cli.put.return_value = {"data": {"record_id": "rid_123"}}
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    w.upsert_task({"task_id": "T1", "status": "成功", "platform_item_id": "X99"})
    # search 走 post
    assert cli.post.called
    # update 走 put
    assert cli.put.called
    put_path = cli.put.call_args.args[0]
    assert "rid_123" in put_path
    # 字段值透传
    put_body = cli.put.call_args.kwargs["json"]["fields"]
    assert put_body["任务 ID"] == "T1"
    assert put_body["上架状态"] == "成功"
    assert put_body["平台商品 ID"] == "X99"


def test_upsert_task_search_failure_falls_back_to_create(tmp_path):
    """search 接口异常时不阻断，回退到 create。"""
    cli = MagicMock()
    cli.post.side_effect = [
        RuntimeError("search boom"),              # search 抛错
        {"data": {"record_id": "r1"}},            # create 成功
    ]
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    w.upsert_task({"task_id": "T1"})
    assert cli.post.call_count == 2


# ---- 字段映射 ----

def test_field_mapping_default():
    """缺省字段映射含全部默认表头。"""
    w = _make_writer(_cfg())
    assert "任务 ID" in w.task_fields
    assert "商品编码" in w.task_fields
    assert "SKU 规格" in w.sku_fields
    assert "节点名称" in w.log_fields


def test_field_mapping_override():
    """配置 field_mapping 覆盖默认表头名（key 改变，state 字段提取依据保留）。"""
    cfg = _cfg(field_mapping={
        "task": {"任务 ID": "task_col", "上架状态": "status_col"},
        "sku": {"SKU 规格": "spec_col"},
    })
    w = _make_writer(cfg)
    # 新表头名作为 key
    assert "task_col" in w.task_fields
    assert w.task_fields["task_col"] == "task_id"      # state 字段不变
    assert w.task_fields["status_col"] == "status"
    # 未覆盖的保留默认表头名
    assert w.task_fields["商品编码"] == "product_code"
    # 原表头名被替换，不再存在
    assert "任务 ID" not in w.task_fields
    # SKU 同理
    assert "spec_col" in w.sku_fields
    assert w.sku_fields["spec_col"] == "sku"


def test_map_sku_fields_uses_spec_fallback():
    """SKU 缺 sku 字段时用 spec 兜底。"""
    w = _make_writer(_cfg())
    fields = w._map_sku_fields("T1", {"spec": "红-M", "price": 99, "stock": 5})
    assert fields["SKU 规格"] == "红-M"
    assert fields["售价"] == 99
    assert fields["库存"] == 5
    assert fields["上架状态"] == "成功"   # 默认


# ---- 日志/SKU 批量写入 ----

def test_append_logs_batch_create(tmp_path):
    cli = MagicMock()
    cli.post.return_value = {"data": {}}
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    traces = [
        {"node": "init", "status": "ok", "ts": "t1", "extra": "start"},
        {"node": "erp_search", "status": "ok", "ts": "t2", "extra": ""},
    ]
    w.append_logs("T1", traces)
    # batch_create 调用
    batch_call = cli.post.call_args
    assert "batch_create" in batch_call.args[0]
    body = batch_call.kwargs["json"]["records"]
    assert len(body) == 2
    assert body[0]["fields"]["日志 ID"] == "T1-0"
    assert body[0]["fields"]["执行状态"] == "成功"
    assert body[1]["fields"]["执行状态"] == "成功"


def test_append_logs_empty_skips():
    w = _make_writer(_cfg())
    cli = w.cli
    w.append_logs("T1", [])
    assert not cli.post.called


# ---- 本地兜底 ----

def test_safe_write_falls_back_to_local(tmp_path):
    """create 连续失败后落本地兜底文件。"""
    cli = MagicMock()
    cli.post.side_effect = RuntimeError("api down")
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    w._safe_write("t_task", {"任务 ID": "T1"}, "T1")
    fb_file = tmp_path / "T1.json"
    assert fb_file.exists()
    data = json.loads(fb_file.read_text("utf-8"))
    assert len(data) == 1
    assert data[0]["table_id"] == "t_task"
    assert data[0]["fields"]["任务 ID"] == "T1"
    assert "api down" in data[0]["error"]


def test_safe_write_succeeds_before_retries_exhaustioned(tmp_path):
    """前两次失败、第三次成功时不落本地。"""
    cli = MagicMock()
    cli.post.side_effect = [RuntimeError("e1"), RuntimeError("e2"), {"ok": True}]
    w = _make_writer(_cfg(fallback_dir=str(tmp_path)), cli)
    w._safe_write("t_task", {"任务 ID": "T1"}, "T1", retries=3)
    assert not (tmp_path / "T1.json").exists()
    assert cli.post.call_count == 3


# ---- 补偿 + 死信 ----

def _write_fallback(fb_dir: Path, key: str, items: list[dict]):
    fb_dir.mkdir(parents=True, exist_ok=True)
    (fb_dir / f"{key}.json").write_text(
        json.dumps(items, ensure_ascii=False), "utf-8"
    )


def test_compensate_success_clears_file(tmp_path):
    """补偿成功后兜底文件被删除。"""
    _write_fallback(tmp_path, "T1", [
        {"table_id": "t_task", "fields": {"任务 ID": "T1"}, "retries": 0},
    ])
    with patch("integrations.feishu.bitable.FeishuClient") as MC:
        MC.return_value.post.return_value = {"data": {"record_id": "r1"}}
        r = compensate_fallback(_cfg(), fb_dir=tmp_path)
    assert r["compensated"] == 1
    assert r["remaining"] == 0
    assert not (tmp_path / "T1.json").exists()


def test_compensate_failure_increments_retries(tmp_path):
    """补偿仍失败时 retries 自增，保留在文件中。"""
    _write_fallback(tmp_path, "T1", [
        {"table_id": "t_task", "fields": {"任务 ID": "T1"}, "retries": 0},
    ])
    with patch("integrations.feishu.bitable.FeishuClient") as MC:
        MC.return_value.post.side_effect = RuntimeError("still down")
        r = compensate_fallback(_cfg(), fb_dir=tmp_path)
    assert r["compensated"] == 0
    assert r["remaining"] == 1
    data = json.loads((tmp_path / "T1.json").read_text("utf-8"))
    assert data[0]["retries"] == 1


def test_compensate_dead_letter_after_threshold(tmp_path):
    """retries 达阈值后移入死信文件，不再重试。"""
    items = [{"table_id": "t_task", "fields": {"任务 ID": "T1"},
              "retries": DEAD_LETTER_THRESHOLD - 1}]
    _write_fallback(tmp_path, "T1", items)
    with patch("integrations.feishu.bitable.FeishuClient") as MC:
        MC.return_value.post.side_effect = RuntimeError("permanent fail")
        r = compensate_fallback(_cfg(), fb_dir=tmp_path)
    assert r["dead_lettered"] == 1
    # 原文件被清，死信文件存在
    assert not (tmp_path / "T1.json").exists()
    dl = tmp_path / "dead_letter" / "T1.json"
    assert dl.exists()
    dl_data = json.loads(dl.read_text("utf-8"))
    assert len(dl_data) == 1


def test_compensate_empty_dir_returns_zero(tmp_path):
    r = compensate_fallback(_cfg(), fb_dir=tmp_path / "nonexist")
    assert r == {"compensated": 0, "dead_lettered": 0, "remaining": 0}


# ---- FeishuSyncSkill 终态差异化 ----

@pytest.fixture
def cfg():
    from config.settings import reload_config
    return reload_config()


def _task(status: str, **kw) -> dict:
    base = {
        "task_id": "T1", "product_code": "P1", "target_shop": "shop_taobao",
        "status": status, "node_trace": [], "sku_price_list": [],
        "shelf_result": {}, "error_msg": "",
    }
    base.update(kw)
    return base


async def test_feishu_sync_success_writes_skus_and_no_notify(cfg, tmp_path, monkeypatch):
    """成功终态：写 SKU 明细，不触发通知。"""
    # 用临时 fallback_dir 避免污染
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.SUCCESS.value,
                 shelf_result={"verified": True},
                 sku_price_list=[{"sku": "S1", "price": 99, "stock": 5}])
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot") as MBot:
        MB.return_value = MagicMock()
        res = await skill.execute(task)
    assert res.ok
    # SKU 明细写入
    MB.return_value.batch_insert_skus.assert_called_once()
    # 通知未被调用
    assert not MBot.called


async def test_feishu_sync_failed_triggers_notify_fail(cfg, tmp_path, monkeypatch):
    """失败终态：触发 notify_fail。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.FAILED.value, error_msg="submit timeout")
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot") as MBot:
        MB.return_value = MagicMock()
        bot = MBot.return_value
        res = await skill.execute(task)
    assert res.ok
    MBot.assert_called_once()
    bot.notify_fail.assert_called_once()
    # 参数含 task_id/shop_id/error
    args = bot.notify_fail.call_args.args
    assert args[0] == "T1"
    assert args[1] == "shop_taobao"
    assert "submit timeout" in args[2]


async def test_feishu_sync_human_sms_triggers_notify_sms(cfg, tmp_path, monkeypatch):
    """待人工 + sms：触发 notify_sms 兜底。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.HUMAN.value, captcha_type="sms")
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot") as MBot:
        MB.return_value = MagicMock()
        bot = MBot.return_value
        res = await skill.execute(task)
    assert res.ok
    bot.notify_sms.assert_called_once_with("T1", "shop_taobao")


async def test_feishu_sync_human_non_sms_no_notify(cfg, tmp_path, monkeypatch):
    """待人工但非 sms（如风控）：不触发 sms 通知（风控由 risk_guard 负责）。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.HUMAN.value, captcha_type="slide", risk_triggered=True)
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot") as MBot:
        MB.return_value = MagicMock()
        bot = MBot.return_value
        res = await skill.execute(task)
    assert res.ok
    # 风控不在此节点通知（risk_guard 已处理）
    assert not bot.notify_sms.called
    assert not bot.notify_fail.called


async def test_feishu_sync_skus_only_when_verified(cfg, tmp_path, monkeypatch):
    """未 verified 时不写 SKU 明细。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.FAILED.value,
                 shelf_result={"verified": False},
                 sku_price_list=[{"sku": "S1", "price": 99}])
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot"):
        MB.return_value = MagicMock()
        await skill.execute(task)
    MB.return_value.batch_insert_skus.assert_not_called()


async def test_feishu_sync_sku_status_enriched(cfg, tmp_path, monkeypatch):
    """verified 时 SKU status 标「成功」。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.SUCCESS.value,
                 shelf_result={"verified": True},
                 sku_price_list=[{"sku": "S1", "price": 99}])
    with patch("skills.feishu_sync.BitableWriter") as MB, \
         patch("skills.feishu_sync.FeishuBot"):
        MB.return_value = MagicMock()
        await skill.execute(task)
    args = MB.return_value.batch_insert_skus.call_args.args
    sku_list = args[1]
    assert sku_list[0]["status"] == "成功"


async def test_feishu_sync_bubble_exception_returns_retry(cfg, tmp_path, monkeypatch):
    """BitableWriter 抛未捕获异常时返回可重试。"""
    monkeypatch.setitem(cfg.feishu, "fallback_dir", str(tmp_path))
    skill = FeishuSyncSkill(config=cfg)
    task = _task(TaskStatus.RUNNING.value)
    with patch("skills.feishu_sync.BitableWriter") as MB:
        MB.return_value.upsert_task.side_effect = RuntimeError("api 500")
        res = await skill.execute(task)
    assert not res.ok
    assert res.error_code == "FS_1001"
