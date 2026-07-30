"""5.2.5 飞书多维表格同步 Skill：终态差异化归档 + 通知联动。

归档策略：
  - 任务总表：始终 upsert（含终态、错误备注、平台商品 ID）
  - 日志表：始终追加节点轨迹
  - SKU 明细表：仅上架成功(verified)时批量写入，status 透传

通知策略（与 risk_guard/captcha 节点互补，feishu_sync 做兜底）：
  - SUCCESS：不通知（成功无需打扰）
  - FAILED：notify_fail 告警责任运营
  - HUMAN + sms：notify_sms 兜底（captcha 节点已触发，中断时由本节点兜底）
  - 风控：由 risk_guard 节点负责 notify_risk，本节点不重复
"""
from __future__ import annotations

import logging

from agent.state import TaskStatus
from integrations.feishu.bitable import BitableWriter
from integrations.feishu.bot import FeishuBot
from skills.base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)


class FeishuSyncSkill(BaseSkill):
    name = "feishu_sync"

    async def execute(self, task: dict, **_) -> SkillResult:
        writer = BitableWriter(self.config.feishu)
        try:
            # 1. 任务总表 upsert（含终态）
            writer.upsert_task(task)
            # 2. 日志表追加节点轨迹
            writer.append_logs(task.get("task_id", ""), task.get("node_trace", []))
            # 3. SKU 明细：仅上架成功时写入，status 透传
            shelf = task.get("shelf_result", {}) or {}
            if shelf.get("verified"):
                sku_list = self._enrich_sku_status(task.get("sku_price_list", []),
                                                   shelf)
                writer.batch_insert_skus(task.get("task_id", ""), sku_list)
            # 4. 终态通知联动
            self._notify_by_terminal_state(task)
            return self._ok({"synced": True})
        except Exception as e:
            logger.exception("feishu sync failed")
            # _safe_write 已本地兜底；此处返回可重试，由编排层决定
            return self._retry(str(e), "FS_1001")

    def _enrich_sku_status(self, sku_list: list, shelf: dict) -> list:
        """给每个 SKU 标注上架状态。整体 verified 则全部成功，否则标失败。"""
        if not sku_list:
            return []
        status = "成功" if shelf.get("verified") else "失败"
        out = []
        for s in sku_list:
            item = dict(s)
            item.setdefault("status", status)
            out.append(item)
        return out

    def _notify_by_terminal_state(self, task: dict):
        """按任务终态触发飞书通知（成功不打扰，失败/人工兜底告警）。"""
        status = task.get("status", "")
        task_id = task.get("task_id", "")
        shop_id = task.get("target_shop", "")
        err = task.get("error_msg", "") or ""

        # 成功：不通知
        if status == TaskStatus.SUCCESS.value:
            return

        # 待人工 + 短信验证码：notify_sms 兜底
        if status == TaskStatus.HUMAN.value:
            if task.get("captcha_type") == "sms":
                try:
                    bot = self._build_bot(shop_id)
                    bot.notify_sms(task_id, shop_id)
                except Exception as e:
                    logger.warning("feishu notify_sms fallback failed: %s", e)
            return

        # 失败：notify_fail
        if status == TaskStatus.FAILED.value:
            try:
                bot = self._build_bot(shop_id)
                bot.notify_fail(task_id, shop_id, err)
            except Exception as e:
                logger.warning("feishu notify_fail failed: %s", e)

    def _build_bot(self, shop_id: str) -> FeishuBot:
        """构造飞书机器人，优先用店铺级告警群，缺省用全局群。"""
        cfg = dict(self.config.feishu)
        if shop_id:
            try:
                from data.repositories.shop_repo import ShopRepo
                shop = ShopRepo().get(shop_id)
                if shop and shop.feishu_notify.get("chat_id"):
                    cfg["notify_chat_id"] = shop.feishu_notify["chat_id"]
            except Exception as e:
                logger.debug("load shop chat_id failed, use global: %s", e)
        return FeishuBot(cfg)
