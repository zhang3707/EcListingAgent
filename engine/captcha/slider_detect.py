"""基于 YOLOv8 的滑块缺口横坐标检测，精度误差目标 ≤2 像素。

模型未就绪时降级为 OpenCV 边缘检测（cv2.matchTemplate），保证开发期可跑。
类别约定：0 = 缺口，1 = 滑块。
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # 开发期未装 opencv 时降级
    cv2 = None


class SliderDetector:
    def __init__(self, model_path: str | None = None, conf: float = 0.5):
        self.model_path = model_path
        self.conf = conf
        self._model = None
        if model_path and Path(model_path).exists():
            self._load_model(model_path)

    def _load_model(self, model_path: str):
        from ultralytics import YOLO  # 延迟导入，避免无模型环境启动失败
        self._model = YOLO(model_path)

    def detect_gap_x(self, image: np.ndarray, slider_img: np.ndarray | None = None) -> Optional[int]:
        """返回缺口左边界横坐标（相对画布），未检出返回 None。"""
        if self._model is not None:
            return self._detect_by_yolo(image)
        if cv2 is not None and slider_img is not None:
            return self._detect_by_cv(image, slider_img)
        return None

    def _detect_by_yolo(self, image: np.ndarray) -> Optional[int]:
        results = self._model(image, conf=self.conf, verbose=False)
        for box in results[0].boxes:
            if int(box.cls[0]) == 0:                       # 类别 0 = 缺口
                return int(box.xyxy[0][0])
        return None

    def _detect_by_cv(self, bg: np.ndarray, slider: np.ndarray) -> Optional[int]:
        """降级方案：Canny 边缘 + matchTemplate 定位缺口（对亮度无关）。"""
        bg_gray = cv2.cvtColor(bg, cv2.COLOR_BGR2GRAY)
        sl_gray = cv2.cvtColor(slider, cv2.COLOR_BGR2GRAY)
        bg_edge = cv2.Canny(bg_gray, 100, 200)
        sl_edge = cv2.Canny(sl_gray, 100, 200)
        if sl_edge.sum() == 0:
            return None
        res = cv2.matchTemplate(bg_edge, sl_edge, cv2.TM_CCOEFF_NORMED)
        _, _, _, max_loc = cv2.minMaxLoc(res)
        return int(max_loc[0])
