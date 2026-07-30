"""飞书机器人告警：短信人工介入、风控触发、任务失败。"""
from __future__ import annotations

import logging

from integrations.feishu.client import FeishuClient

logger = logging.getLogger(__name__)


class FeishuBot:
    def __init__(self, cfg: dict):
        self.cli = FeishuClient(cfg["app_id"], cfg["app_secret"])
        self.chat_id = cfg.get("notify_chat_id", "")

    def _send(self, text: str, chat_id: str | None = None):
        target = chat_id or self.chat_id
        if not target:
            logger.warning("feishu notify skipped: no chat_id")
            return
        try:
            self.cli.post(
                "/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                json={
                    "receive_id": target,
                    "msg_type": "text",
                    "content": json_text(text),
                },
            )
        except Exception as e:
            logger.error("feishu notify failed: %s", e)

    def notify_sms(self, task_id: str, shop_id: str):
        self._send(
            f"[待人工] 短信验证码\n店铺: {shop_id}\n任务: {task_id}\n"
            f"请在 5 分钟内回复验证码（格式: code:<验证码>）"
        )

    def notify_risk(self, shop_id: str, msg: str):
        self._send(f"[风控告警] 店铺: {shop_id} 触发账号限制\n{msg}\n已暂停该店铺所有任务")

    def notify_fail(self, task_id: str, shop_id: str, err: str):
        self._send(f"[任务失败] 店铺: {shop_id} 任务: {task_id}\n原因: {err}")


def json_text(text: str) -> str:
    import json
    return json.dumps({"text": text})
