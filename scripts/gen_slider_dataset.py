"""合成滑块验证码数据集生成器（含 YOLO 标注，双类别）。

用途：在无真实采集数据时，让 train_slider.py 训练管线可端到端跑通。
合成数据仅用于管线验证与基线，生产应替换为真实标注数据。

生成内容：
  scripts/datasets/slider/images/{train,val}/*.jpg   背景图（含缺口 + 滑块块）
  scripts/datasets/slider/labels/{train,val}/*.txt   YOLO 标注（0=缺口，1=滑块块）
  scripts/datasets/slider/data.yaml                  数据集描述

类别：
  0 = gap     缺口（暗化拼图凹槽）
  1 = slider  滑块块（亮色拼图凸块，独立绘制在画布左侧）

缺口/滑块块为拼图块形状，位置/尺寸/背景/明暗/对比度随机化，模拟真实滑块验证码外观。

用法：
  python scripts/gen_slider_dataset.py --train 400 --val 80
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    import cv2  # type: ignore
except ImportError as e:
    raise SystemExit("需要 opencv-python-headless：pip install opencv-python-headless") from e

DS_ROOT = ROOT / "scripts" / "datasets" / "slider"
CLASS_GAP = 0
CLASS_SLIDER = 1


def random_background(w: int, h: int) -> np.ndarray:
    """生成近似真实照片的彩色背景：多色块 + 渐变 + 噪点。"""
    bg = np.zeros((h, w, 3), dtype=np.uint8)
    # 基础渐变
    c1 = np.array([random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)])
    c2 = np.array([random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)])
    for y in range(h):
        bg[y, :] = c1 * (1 - y / h) + c2 * (y / h)
    # 随机色块（模拟景物）
    for _ in range(random.randint(8, 20)):
        x0, y0 = random.randint(0, w - 1), random.randint(0, h - 1)
        rw, rh = random.randint(15, 80), random.randint(15, 80)
        color = [random.randint(0, 255) for _ in range(3)]
        cv2.rectangle(bg, (x0, y0), (min(w - 1, x0 + rw), min(h - 1, y0 + rh)), color, -1)
    # 高斯噪点
    noise = np.random.normal(0, 12, bg.shape).astype(np.int16)
    bg = np.clip(bg.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    # 轻微模糊，更像压缩图
    bg = cv2.GaussianBlur(bg, (3, 3), 0)
    return bg


def random_brightness_contrast(img: np.ndarray) -> np.ndarray:
    """随机亮度/对比度扰动，增强模型对光照变化的鲁棒性。"""
    out = img.astype(np.float32)
    # 对比度
    alpha = random.uniform(0.75, 1.25)
    out = out * alpha
    # 亮度
    beta = random.randint(-35, 35)
    out = out + beta
    return np.clip(out, 0, 255).astype(np.uint8)


def puzzle_mask(size: int) -> np.ndarray:
    """拼图块形状掩码：方块 + 右侧凸起 + 左侧凹陷。返回单通道 0/255。"""
    m = np.zeros((size, size), dtype=np.uint8)
    margin = size // 6
    body = size - 2 * margin
    x0, y0, x1, y1 = margin, margin, margin + body, margin + body
    cv2.rectangle(m, (x0, y0), (x1, y1), 255, -1)
    # 右侧凸起
    cv2.circle(m, (x1, (y0 + y1) // 2), body // 4, 255, -1)
    # 左侧凹陷（挖空）
    cv2.circle(m, (x0, (y0 + y1) // 2), body // 4, 0, -1)
    return m


def draw_gap(bg: np.ndarray, mask: np.ndarray, gx: int, gy: int):
    """在 bg 上 (gx,gy) 处绘制缺口：暗化 + 边缘高光。"""
    h, w = bg.shape[:2]
    ms = mask.shape[0]
    x0, y0 = max(0, gx), max(0, gy)
    x1, y1 = min(w, gx + ms), min(h, gy + ms)
    mx0, my0 = x0 - gx, y0 - gy
    mx1, my1 = mx0 + (x1 - x0), my0 + (y1 - y0)
    roi = bg[y0:y1, x0:x1]
    sub_mask = mask[my0:my1, mx0:mx1]
    # 暗化缺口区域
    dark = (roi.astype(np.int16) * 0.45).astype(np.uint8)
    # 加阴影偏移
    dark = np.clip(dark.astype(np.int16) - 20, 0, 255).astype(np.uint8)
    mask3 = cv2.merge([sub_mask, sub_mask, sub_mask])
    bg[y0:y1, x0:x1] = np.where(mask3 > 0, dark, roi)
    # 边缘描边（模拟拼图缝隙）
    contours, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(bg[y0:y1, x0:x1], contours, -1, (220, 220, 220), 1)
    return (x0, y0, x1, y1)


def draw_slider_piece(bg: np.ndarray, mask: np.ndarray, sx: int, sy: int):
    """在 (sx, sy) 处绘制滑块块：亮色拼图块 + 描边 + 半透明阴影。

    滑块块独立于缺口，位于画布左侧，模拟真实滑块块外观。
    """
    h, w = bg.shape[:2]
    ms = mask.shape[0]
    x0, y0 = max(0, sx), max(0, sy)
    x1, y1 = min(w, sx + ms), min(h, sy + ms)
    mx0, my0 = x0 - sx, y0 - sy
    mx1, my1 = mx0 + (x1 - x0), my0 + (y1 - y0)
    roi = bg[y0:y1, x0:x1]
    sub_mask = mask[my0:my1, mx0:mx1]
    # 滑块块：亮色填充（白色半透明） + 描边
    bright = np.full_like(roi, 240)                      # 接近白
    mask3 = cv2.merge([sub_mask, sub_mask, sub_mask])
    # 半透明叠加：50% 亮色
    blended = (roi.astype(np.float32) * 0.4
               + bright.astype(np.float32) * 0.6).astype(np.uint8)
    bg[y0:y1, x0:x1] = np.where(mask3 > 0, blended, roi)
    # 描边（深色，与缺口区分）
    contours, _ = cv2.findContours(sub_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(bg[y0:y1, x0:x1], contours, -1, (40, 40, 40), 2)
    return (x0, y0, x1, y1)


def mask_bbox(mask: np.ndarray, offset_x: int, offset_y: int) -> tuple[int, int, int, int]:
    """返回掩码的紧致 bbox（绝对坐标）。"""
    ys, xs = np.where(mask > 0)
    if len(xs) == 0:
        return (0, 0, 0, 0)
    return (int(xs.min()) + offset_x, int(ys.min()) + offset_y,
            int(xs.max()) + offset_x, int(ys.max()) + offset_y)


def to_yolo(cls: int, x0: int, y0: int, x1: int, y1: int, w: int, h: int) -> str:
    cx = (x0 + x1) / 2 / w
    cy = (y0 + y1) / 2 / h
    bw = (x1 - x0) / w
    bh = (y1 - y0) / h
    return f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def gen_one(path_img: Path, path_lbl: Path):
    """生成一张含缺口 + 滑块块的样本，含双类别 YOLO 标注。"""
    w, h = random.choice([(300, 180), (320, 180), (280, 160)])
    bg = random_background(w, h)
    # 亮度/对比度随机化
    bg = random_brightness_contrast(bg)

    gap_size = random.randint(44, 58)
    mask = puzzle_mask(gap_size)
    # 缺口 x 在右半区，y 固定中带（贴合真实滑块）
    gx = random.randint(gap_size, w - gap_size - int(gap_size * 0.3))
    gy = (h - gap_size) // 2 + random.randint(-8, 8)

    # 绘制缺口
    gap_box = draw_gap(bg, mask, gx, gy)

    # 绘制滑块块：位于画布左侧，y 与缺口对齐（模拟真实滑块块起始位置）
    sx = random.randint(2, max(3, gap_size // 4))
    sy = gy + random.randint(-4, 4)
    slider_box = draw_slider_piece(bg, mask, sx, sy)

    cv2.imwrite(str(path_img), bg, [cv2.IMWRITE_JPEG_QUALITY, 85])
    # 双类别标注：缺口(0) + 滑块块(1)
    gap_yolo = to_yolo(CLASS_GAP, *gap_box, w, h)
    slider_yolo = to_yolo(CLASS_SLIDER, *slider_box, w, h)
    path_lbl.write_text(gap_yolo + "\n" + slider_yolo + "\n", encoding="utf-8")


def write_data_yaml():
    DS_ROOT.mkdir(parents=True, exist_ok=True)
    (DS_ROOT / "data.yaml").write_text(
        f"path: {DS_ROOT.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n  0: gap\n  1: slider\n",
        encoding="utf-8",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=400)
    ap.add_argument("--val", type=int, default=80)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    for split, n in [("train", args.train), ("val", args.val)]:
        img_dir = DS_ROOT / "images" / split
        lbl_dir = DS_ROOT / "labels" / split
        img_dir.mkdir(parents=True, exist_ok=True)
        lbl_dir.mkdir(parents=True, exist_ok=True)
        for i in range(n):
            gen_one(img_dir / f"{split}_{i:05d}.jpg",
                    lbl_dir / f"{split}_{i:05d}.txt")
        print(f"[gen] {split}: {n} samples (gap+slider dual-label) -> {img_dir}")
    write_data_yaml()
    print(f"[gen] data.yaml -> {DS_ROOT / 'data.yaml'}")


if __name__ == "__main__":
    main()
