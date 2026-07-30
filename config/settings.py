"""全局配置：环境变量 + 店铺/飞书 YAML 加载，支持 ${VAR} 环境变量替换。"""
from __future__ import annotations

import os
import re
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ROOT / ".env"), extra="ignore")

    pg_dsn: str = "postgresql+psycopg://ec:ec@localhost:5432/ecagent"
    minio_endpoint: str = "localhost:9000"
    minio_access: str = "minioadmin"
    minio_secret: str = "minioadmin"
    minio_secure: bool = False
    headless: bool = False

    # 以下由 get_config() 装配
    shops: dict[str, "ShopCfg"] = field(default_factory=dict)
    feishu: dict[str, Any] = field(default_factory=dict)
    captcha: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProxyCfg:
    server: str = ""
    username: str = ""
    password: str = ""


@dataclass
class ShopCfg:
    shop_id: str
    shop_name: str = ""
    platform: str = ""
    base_url: str = ""
    account: dict = field(default_factory=dict)
    fingerprint: dict = field(default_factory=dict)
    proxy: ProxyCfg = field(default_factory=ProxyCfg)
    price_strategy: dict = field(default_factory=dict)
    feishu_notify: dict = field(default_factory=dict)
    selectors: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ShopCfg":
        proxy = ProxyCfg(**(d.get("proxy") or {}))
        return cls(
            shop_id=d["shop_id"],
            shop_name=d.get("shop_name", ""),
            platform=d.get("platform", ""),
            base_url=d.get("base_url", ""),
            account=d.get("account", {}),
            fingerprint=d.get("fingerprint", {}),
            proxy=proxy,
            price_strategy=d.get("price_strategy", {}),
            feishu_notify=d.get("feishu_notify", {}),
            selectors=d.get("selectors", {}),
        )


def _substitute_env(value: Any) -> Any:
    """递归把字符串中的 ${VAR} 替换为环境变量值，未设置则保留空串。"""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    return value


def _load_yaml(path: pathlib.Path) -> dict:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _substitute_env(raw)


def _load_shops(cfg_dir: pathlib.Path) -> dict[str, ShopCfg]:
    shops: dict[str, ShopCfg] = {}
    for f in sorted(cfg_dir.glob("*.yaml")):
        d = _load_yaml(f)
        if d.get("shop_id"):
            shops[d["shop_id"]] = ShopCfg.from_dict(d)
    return shops


_settings: Settings | None = None


def get_config() -> Settings:
    global _settings
    if _settings is None:
        s = Settings()
        s.shops = _load_shops(_ROOT / "config" / "shops")
        s.feishu = _load_yaml(_ROOT / "config" / "feishu.yaml")
        s.captcha = _load_yaml(_ROOT / "config" / "captcha.yaml")
        _settings = s
    return _settings


def reload_config() -> Settings:
    """强制重新加载配置（配置文件变更后调用）。"""
    global _settings
    _settings = None
    return get_config()
