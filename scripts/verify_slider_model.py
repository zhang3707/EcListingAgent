"""验证训练好的滑块缺口检测模型：对样本推理并对比 YOLO 标注真值。"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.captcha.slider_detect import SliderDetector
from config.settings import get_config


def parse_label(lbl_path: Path, img_w: int, img_h: int):
    """YOLO 标注 → 缺口左上 x（真值）。"""
    line = lbl_path.read_text("utf-8").strip().split()
    cls, cx, cy, w, h = int(line[0]), *map(float, line[1:])
    x0 = (cx - w / 2) * img_w
    return int(x0)


def main(n: int = 20):
    cfg = get_config()
    model_path = cfg.captcha.get("slider_model")
    print(f"[verify] model: {model_path}")
    detector = SliderDetector(model_path, conf=0.4)

    ds = ROOT / "scripts" / "datasets" / "slider" / "images" / "val"
    samples = sorted(ds.glob("*.jpg"))[:n]
    if not samples:
        print("[verify] no val samples found")
        return

    errs, ok = [], 0
    for img_path in samples:
        lbl_path = ROOT / "scripts" / "datasets" / "slider" / "labels" / "val" / (
            img_path.stem + ".txt"
        )
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        gt_x = parse_label(lbl_path, w, h)
        pred_x = detector.detect_gap_x(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if pred_x is None:
            print(f"  MISS  {img_path.name}  gt={gt_x}")
            continue
        err = abs(pred_x - gt_x)
        errs.append(err)
        if err <= 2:
            ok += 1
        print(f"  {img_path.name}  gt={gt_x:4d}  pred={pred_x:4d}  err={err}px")

    if errs:
        print(f"\n[verify] detected {len(errs)}/{len(samples)}, "
              f"≤2px accuracy={ok}/{len(errs)}, "
              f"mean_err={sum(errs)/len(errs):.2f}px, max_err={max(errs)}px")


if __name__ == "__main__":
    main()
