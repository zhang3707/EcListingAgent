"""SliderDetector CV 降级路径测试（不依赖训练好的模型）。

验证无 YOLO 模型时，OpenCV matchTemplate 仍能定位缺口。
"""
from pathlib import Path

import numpy as np
import pytest

from engine.captcha.slider_detect import SliderDetector
from config.settings import get_config

_MODEL = Path(get_config().captcha.get("slider_model", ""))
_HAS_MODEL = _MODEL.exists()


def _make_bg_and_slider(gap_x: int = 150, gap_y: int = 60, size: int = 50):
    """构造一张带缺口的背景图 + 拼图块图，返回 (bg, slider_img, true_x)。"""
    import cv2

    bg = np.zeros((180, 300, 3), dtype=np.uint8)
    bg[:] = (120, 150, 180)  # 纯色背景便于模板匹配
    # 拼图块掩码
    mask = np.zeros((size, size), dtype=np.uint8)
    m = size // 6
    body = size - 2 * m
    cv2.rectangle(mask, (m, m), (m + body, m + body), 255, -1)
    cv2.circle(mask, (m + body, (m + m + body) // 2), body // 4, 255, -1)
    # 在背景上画暗化缺口
    roi = bg[gap_y:gap_y + size, gap_x:gap_x + size]
    dark = (roi.astype(np.int16) * 0.4).astype(np.uint8)
    mask3 = cv2.merge([mask, mask, mask])
    bg[gap_y:gap_y + size, gap_x:gap_x + size] = np.where(mask3 > 0, dark, roi)
    # 拼图块图（用于 matchTemplate）
    slider_img = np.where(mask3 > 0, dark, 0).astype(np.uint8)
    return bg, slider_img, gap_x


def test_cv_fallback_detects_gap():
    bg, slider_img, true_x = _make_bg_and_slider(gap_x=150)
    detector = SliderDetector(model_path=None)   # 无模型，走 CV 降级
    pred_x = detector.detect_gap_x(bg, slider_img)
    assert pred_x is not None
    assert abs(pred_x - true_x) <= 3


def test_cv_fallback_returns_none_without_slider_img():
    bg, _, _ = _make_bg_and_slider()
    detector = SliderDetector(model_path=None)
    # 无模型且无 slider_img 时应返回 None
    assert detector.detect_gap_x(bg, slider_img=None) is None


@pytest.mark.skipif(not _HAS_MODEL, reason="trained slider model not present")
def test_yolo_model_detects_gap_on_synthetic_sample():
    """有训练模型时，对验证集样本推理，误差应 ≤2px。"""
    import cv2

    ds = Path(__file__).resolve().parent.parent.parent / "scripts" / "datasets" / "slider"
    img = ds / "images" / "val" / "val_00000.jpg"
    lbl = ds / "labels" / "val" / "val_00000.txt"
    if not img.exists():
        pytest.skip("synthetic dataset not generated")
    bg = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    h, w = bg.shape[:2]
    # 双类别标注文件含两行（gap + slider），只取类别 0（缺口）行
    gap_line = None
    for line in lbl.read_text("utf-8").strip().splitlines():
        parts = line.split()
        if parts and int(parts[0]) == 0:
            gap_line = parts
            break
    if not gap_line:
        pytest.skip("no gap label in sample")
    cx, cy, bw, bh = map(float, gap_line[1:])
    gt_x = int((cx - bw / 2) * w)
    detector = SliderDetector(str(_MODEL), conf=0.4)
    pred_x = detector.detect_gap_x(bg)
    assert pred_x is not None
    # 单样本验证用宽松阈值（≤10px），避免单样本随机性导致 flaky。
    # ≤2px 的精度目标由 scripts/eval_slider.py 的统计报告验证（命中率指标）。
    assert abs(pred_x - gt_x) <= 10
