"""飞书多维表格读写：真 upsert、日志追加、SKU 批量写入、失败本地兜底 + 死信。

字段映射支持配置化：feishu.yaml 的 field_mapping 块可覆盖默认中文表头，
缺省时使用内置默认映射，保证零配置可用。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from integrations.feishu.client import FeishuClient

logger = logging.getLogger(__name__)

# 默认字段映射：表头名 → TaskState/SKU 字段提取函数（可选，可被 cfg.field_mapping 覆盖）
DEFAULT_TASK_FIELDS = {
    "任务 ID": "task_id",
    "商品编码": "product_code",
    "目标店铺": "target_shop",
    "上架状态": "status",
    "平台商品 ID": "platform_item_id",
    "错误备注": "error_msg",
}
DEFAULT_LOG_FIELDS = {
    "日志 ID": "log_id",
    "关联任务 ID": "task_id",
    "节点名称": "node",
    "执行状态": "status",
    "时间戳": "ts",
    "日志详情": "extra",
}
DEFAULT_SKU_FIELDS = {
    "关联任务 ID": "task_id",
    "SKU 规格": "sku",
    "售价": "price",
    "库存": "stock",
    "上架状态": "status",
}

# 死信阈值：补偿仍失败的记录超过此次数后移入死信文件
DEAD_LETTER_THRESHOLD = 5


class BitableWriter:
    def __init__(self, cfg: dict):
        # cfg: {app_id, app_secret, app_token, table_id_task, table_id_sku, table_id_log,
        #       field_mapping?(可选), notify_chat_id?(可选)}
        self.cfg = cfg
        self.cli = FeishuClient(cfg["app_id"], cfg["app_secret"])
        self.app_token = cfg["app_token"]
        self.t_task = cfg["table_id_task"]
        self.t_sku = cfg["table_id_sku"]
        self.t_log = cfg["table_id_log"]
        # 字段映射：允许配置覆盖默认表头名（多表/英文化场景）
        # DEFAULT_*_FIELDS: {表头名: state字段名}；field_mapping: {默认表头: 新表头}
        fm = cfg.get("field_mapping", {}) or {}
        self.task_fields = self._merge_fields(DEFAULT_TASK_FIELDS, fm.get("task") or {})
        self.log_fields = self._merge_fields(DEFAULT_LOG_FIELDS, fm.get("log") or {})
        self.sku_fields = self._merge_fields(DEFAULT_SKU_FIELDS, fm.get("sku") or {})
        # 本地兜底目录（可配置，便于测试隔离）
        self.fb_dir = Path(cfg.get("fallback_dir", "logs/feishu_fallback"))

    @staticmethod
    def _merge_fields(default: dict, override: dict) -> dict:
        """合并字段映射：override 的 key 是默认表头，value 是新表头名。

        保留 state 字段提取依据，仅允许覆盖表头名（key）。
        """
        out = {}
        for header, state_key in default.items():
            new_header = override.get(header, header)
            out[new_header] = state_key
        return out

    # ---- 单条写入 ----
    def _create_record(self, table_id: str, fields: dict) -> dict:
        return self.cli.post(
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records",
            json={"fields": fields},
        )

    def _update_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        return self.cli.put(
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/{record_id}",
            json={"fields": fields},
        )

    def _batch_create(self, table_id: str, records: list[dict]) -> dict:
        return self.cli.post(
            f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/batch_create",
            json={"records": records},
        )

    def _search_record(self, table_id: str, field_name: str, value: str) -> str | None:
        """按字段值搜索记录，返回首个匹配的 record_id，无则 None。"""
        try:
            r = self.cli.post(
                f"/bitable/v1/apps/{self.app_token}/tables/{table_id}/records/search",
                json={"filter": {
                    "conjunction": "and",
                    "conditions": [{
                        "field_name": field_name,
                        "operator": "is",
                        "value": [value],
                    }],
                }},
            )
            items = r.get("data", {}).get("items", []) or []
            return items[0].get("record_id") if items else None
        except Exception as e:
            logger.debug("search record failed (table=%s value=%s): %s",
                         table_id, value, e)
            return None

    # ---- 业务方法 ----
    def upsert_task(self, task: dict):
        """真 upsert：按任务 ID 搜索，存在则更新，不存在则新建。"""
        task_id = task.get("task_id", "")
        fields = self._map_task_fields(task)
        # 主键字段名（用于搜索）
        pk_name = next(iter(self.task_fields))   # 默认 "任务 ID"
        rid = self._search_record(self.t_task, pk_name, task_id) if task_id else None
        if rid:
            self._safe_update(self.t_task, rid, fields, task_id)
        else:
            self._safe_write(self.t_task, fields, task_id)

    def append_logs(self, task_id: str, traces: list[dict]):
        if not traces:
            return
        records = []
        for i, tr in enumerate(traces):
            fields = self._map_log_fields(task_id, i, tr)
            records.append({"fields": fields})
        for i in range(0, len(records), 500):       # 飞书批量上限
            self._batch_create(self.t_log, records[i:i + 500])

    def batch_insert_skus(self, task_id: str, sku_list: list[dict]):
        if not sku_list:
            return
        records = []
        for s in sku_list:
            fields = self._map_sku_fields(task_id, s)
            records.append({"fields": fields})
        for i in range(0, len(records), 500):
            self._batch_create(self.t_sku, records[i:i + 500])

    # ---- 字段映射 ----
    def _map_task_fields(self, task: dict) -> dict:
        out = {}
        for header, key in self.task_fields.items():
            val = task.get(key, "")
            out[header] = val if val is not None else ""
        return out

    def _map_log_fields(self, task_id: str, idx: int, tr: dict) -> dict:
        """日志字段映射：表头名作为 key，tr 字段值作为 value。

        state 字段名 → 取值规则：
          log_id   → f"{task_id}-{idx}"
          task_id  → task_id
          status   → ok→成功，否则失败
          node/ts/extra → tr[state_key]
        """
        out = {}
        for header, state_key in self.log_fields.items():
            if state_key == "log_id":
                out[header] = f"{task_id}-{idx}"
            elif state_key == "task_id":
                out[header] = task_id
            elif state_key == "status":
                out[header] = "成功" if tr.get("status") == "ok" else "失败"
            else:
                out[header] = tr.get(state_key, "") or ""
        return out

    def _map_sku_fields(self, task_id: str, s: dict) -> dict:
        """SKU 字段映射：表头名作为 key。

        state 字段名 → 取值规则：
          task_id → task_id
          sku     → s.get("sku") or s.get("spec")  （spec 兜底）
          status  → s.get("status", "成功")
          price/stock → s[state_key]，缺省 0
        """
        out = {}
        for header, state_key in self.sku_fields.items():
            if state_key == "task_id":
                out[header] = task_id
            elif state_key == "sku":
                out[header] = s.get("sku", "") or s.get("spec", "")
            elif state_key == "status":
                out[header] = s.get("status", "成功")
            elif state_key in ("price", "stock"):
                out[header] = s.get(state_key, 0)
            else:
                out[header] = s.get(state_key, "")
        return out

    # ---- 容错：失败本地落盘 + 重试 + 死信 ----
    def _safe_write(self, table_id: str, fields: dict, key: str, retries: int = 3):
        for attempt in range(1, retries + 1):
            try:
                self._create_record(table_id, fields)
                return
            except Exception as e:
                logger.warning("feishu write failed (attempt %d): %s", attempt, e)
                if attempt == retries:
                    self._fallback_to_local(table_id, fields, key, str(e))

    def _safe_update(self, table_id: str, record_id: str, fields: dict,
                     key: str, retries: int = 3):
        for attempt in range(1, retries + 1):
            try:
                self._update_record(table_id, record_id, fields)
                return
            except Exception as e:
                logger.warning("feishu update failed (attempt %d): %s", attempt, e)
                if attempt == retries:
                    # 更新失败也落本地兜底，补偿时重新走 create
                    self._fallback_to_local(table_id, fields, key, str(e))

    def _fallback_to_local(self, table_id: str, fields: dict, key: str, err: str):
        self.fb_dir.mkdir(parents=True, exist_ok=True)
        fb_file = self.fb_dir / f"{key}.json"
        data = []
        if fb_file.exists():
            data = json.loads(fb_file.read_text("utf-8"))
        data.append({
            "table_id": table_id,
            "fields": fields,
            "error": err,
            "ts": time.time(),
            "retries": 0,
        })
        fb_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        logger.error("feishu write fallback to local: %s", fb_file)

    def _to_dead_letter(self, fb_file: Path, data: list[dict]):
        """多次补偿仍失败的记录移入死信文件，避免无限重试。"""
        dl_dir = fb_file.parent / "dead_letter"
        dl_dir.mkdir(parents=True, exist_ok=True)
        dl_file = dl_dir / fb_file.name
        existing = []
        if dl_file.exists():
            existing = json.loads(dl_file.read_text("utf-8"))
        existing.extend(data)
        dl_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), "utf-8")
        fb_file.unlink()
        logger.error("feishu record moved to dead letter: %s", dl_file)


def compensate_fallback(cfg: dict, fb_dir: Path | str | None = None) -> dict:
    """补偿同步本地落盘的失败记录。

    返回 {compensated: int, dead_lettered: int, remaining: int}。
    单条记录累计补偿超 DEAD_LETTER_THRESHOLD 次后移入死信文件。
    fb_dir 可指定兜底目录（测试隔离用），缺省用 BitableWriter.fb_dir。
    """
    writer = BitableWriter(cfg)
    base = Path(fb_dir) if fb_dir else writer.fb_dir
    if not base.exists():
        return {"compensated": 0, "dead_lettered": 0, "remaining": 0}

    compensated = 0
    dead_lettered = 0
    for fb_file in list(base.glob("*.json")):
        try:
            data = json.loads(fb_file.read_text("utf-8"))
        except Exception as e:
            logger.error("read fallback file %s failed: %s", fb_file, e)
            continue

        ok_items, fail_items = [], []
        for item in data:
            try:
                writer._create_record(item["table_id"], item["fields"])
                compensated += 1
                ok_items.append(item)
            except Exception:
                item["retries"] = item.get("retries", 0) + 1
                if item["retries"] >= DEAD_LETTER_THRESHOLD:
                    dead_lettered += 1
                else:
                    fail_items.append(item)

        if fail_items:
            fb_file.write_text(json.dumps(fail_items, ensure_ascii=False, indent=2),
                               "utf-8")
        elif ok_items and not fail_items:
            fb_file.unlink()
        else:
            # 全部进死信
            dead = [it for it in data if it.get("retries", 0) >= DEAD_LETTER_THRESHOLD]
            if dead:
                writer._to_dead_letter(fb_file, dead)

    remaining = sum(1 for _ in base.glob("*.json")) if base.exists() else 0
    return {"compensated": compensated, "dead_lettered": dead_lettered,
            "remaining": remaining}
