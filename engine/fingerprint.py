"""店铺指纹管理：每店铺固定指纹，持久化，模拟真实固定设备。"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict, field
from pathlib import Path

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

VIEWPORT_POOL = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
]

WEBGL_RENDERERS = [
    ("Intel Inc.", "Intel(R) UHD Graphics 630"),
    ("Intel Inc.", "Intel(R) Iris(R) Xe Graphics"),
    ("Google Inc. (Intel)", "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0)"),
]


@dataclass
class Fingerprint:
    shop_id: str
    user_agent: str
    viewport: dict
    device_scale_factor: float
    locale: str
    timezone_id: str
    platform: str
    hardware_concurrency: int
    color_depth: int
    webgl_vendor: str
    webgl_renderer: str
    canvas_noise: float
    fonts: list = field(default_factory=list)


class FingerprintManager:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get(self, shop_id: str) -> Fingerprint:
        fp_file = self.base_dir / f"{shop_id}.json"
        if fp_file.exists():
            return Fingerprint(**json.loads(fp_file.read_text(encoding="utf-8")))
        fp = self._generate(shop_id)
        fp_file.write_text(
            json.dumps(asdict(fp), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return fp

    def _generate(self, shop_id: str) -> Fingerprint:
        ua = random.choice(UA_POOL)
        vp = random.choice(VIEWPORT_POOL)
        vendor, renderer = random.choice(WEBGL_RENDERERS)
        return Fingerprint(
            shop_id=shop_id,
            user_agent=ua,
            viewport=vp,
            device_scale_factor=1.0,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            platform="Win32",
            hardware_concurrency=8,
            color_depth=24,
            webgl_vendor=vendor,
            webgl_renderer=renderer,
            canvas_noise=round(random.uniform(-0.0001, 0.0001), 6),
            fonts=["Microsoft YaHei", "SimSun", "Arial", "Calibri", "Segoe UI"],
        )
