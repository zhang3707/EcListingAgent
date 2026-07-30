"""贝塞尔轨迹生成：先加速 → 后减速 → 微小过冲 → 小幅回退。"""
from __future__ import annotations

import random
import numpy as np


def _bezier(points, n: int = 50) -> np.ndarray:
    """De Casteljau 算法，返回 n 个采样点。"""
    pts = np.array(points, dtype=float)             # (k,) 控制点
    t = np.linspace(0, 1, n)                         # (n,) 参数
    # 在 (n, k) 空间归约，避免与采样维度混淆
    B = np.broadcast_to(pts, (n, len(pts))).astype(float).copy()
    while B.shape[1] > 1:
        B = (1 - t)[:, None] * B[:, :-1] + t[:, None] * B[:, 1:]
    return B[:, 0]


def gen_track(distance: int) -> list[tuple[float, float, int]]:
    """生成 [(x, y, dt_ms), ...] 轨迹点。

    distance 为需要滑动的水平像素距离（缺口 x - 滑块起点 x）。
    """
    if distance <= 0:
        return [(0.0, 0.0, 0)]
    overshoot = distance + random.randint(2, 6)             # 过冲
    control_x = [0, distance * 0.3, distance * 0.7, overshoot, distance]
    control_y = [0, random.uniform(-1, 1), random.uniform(-2, 2),
                 random.uniform(-1, 1), random.uniform(-1, 1)]
    xs = _bezier(control_x, n=50)
    ys = _bezier(control_y, n=50)
    # 速度：先快后慢，dt 递增
    dts = np.linspace(8, 22, len(xs)).astype(int) + np.random.randint(-3, 4, len(xs))
    track = [(float(xs[i]), float(ys[i]), int(max(5, dts[i]))) for i in range(len(xs))]
    # 末端回退修正
    track.append((float(distance), 0.0, random.randint(30, 60)))
    return track
