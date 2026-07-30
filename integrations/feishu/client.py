"""飞书 API 客户端：tenant_access_token 缓存 + 自动续期。"""
from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


class FeishuClient:
    BASE = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: str | None = None
        self._expire_at: float = 0

    def tenant_token(self) -> str:
        if self._token and time.time() < self._expire_at - 60:
            return self._token
        r = requests.post(
            f"{self.BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        if d.get("code") != 0:
            raise RuntimeError(f"feishu token failed: {d}")
        self._token = d["tenant_access_token"]
        self._expire_at = time.time() + d["expire"]
        return self._token

    def request(self, method: str, path: str, **kwargs) -> dict:
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.tenant_token()}"
        resp = requests.request(method, f"{self.BASE}{path}", headers=headers, timeout=15, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, **kwargs) -> dict:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> dict:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> dict:
        return self.request("PUT", path, **kwargs)
