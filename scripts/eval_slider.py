"""滑块缺口检测模型评估脚本：推理验证集 + 统计精度（≤2px 目标）。

对 val 集每张样本：
  1. YOLO 推理，取类别 0（缺口）的左边界 x
  2. 与 YOLO 标注的 ground truth x 对比
  3. 统计平均/中位/最大误差、≤2px 命中率、≤5px 命中率

用法：
  python scripts/eval_slider.py
  python scripts/eval_slider.py --model data_persist/slider_gap_yolov8n.pt --conf 0.4
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DS_ROOT = ROOT / "scripts" / "datasets" / "slider"
DEFAULT_MODEL = ROOT / "data_persist" / "slider_gap_yolov8n.pt"


def load_gt_x(lbl_path: Path) -> int | None:
    """从 YOLO 标注读取类别 0（缺口）的左边界 x（像素）。"""
    if not lbl_path.exists():
        return None
    for line in lbl_path.read_text("utf-8").strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cls = int(parts[0])
        if cls != 0:                      # 只看缺口
            continue
        cx, _, bw = float(parts[1]), float(parts[2]), float(parts[3])
        # YOLO 标注是归一化的，需要图宽转换；此处先返回归一化左边界，后续按图宽换算
        return (cx, bw)
    return None


def evaluate(model_path: str, conf: float, split: str = "val") -> dict:
    """评估模型在 val 集上的缺口定位精度。"""
    try:
        import cv2  # noqa: F401
        from ultralytics import YOLO
    except ImportError as e:
        print(f"[eval] 依赖缺失: {e}")
        return {}

    img_dir = DS_ROOT / "images" / split
    lbl_dir = DS_ROOT / "labels" / split
    if not img_dir.exists():
        print(f"[eval] 验证集不存在: {img_dir}")
        print("[eval] 请先运行: python scripts/gen_slider_dataset.py")
        return {}

    model = YOLO(model_path)
    imgs = sorted(img_dir.glob("*.jpg"))
    if not imgs:
        print(f"[eval] {split} 集无图片")
        return {}

    errors: list[float] = []
    detected = 0
    skipped = 0

    for img_path in imgs:
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        gt = load_gt_x(lbl_path)
        if gt is None:
            skipped += 1
            continue
        gt_cx, gt_bw = gt

        import cv2
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        gt_x = int((gt_cx - gt_bw / 2) * w)   # 像素级左边界

        results = model(img, conf=conf, verbose=False)
        pred_x = None
        for box in results[0].boxes:
            if int(box.cls[0]) == 0:          # 类别 0 = 缺口
                pred_x = int(box.xyxy[0][0])
                break
        if pred_x is None:
            continue
        detected += 1
        errors.append(abs(pred_x - gt_x))

    if not errors:
        print(f"[eval] 未检出任何缺口（共 {len(imgs)} 张，跳过 {skipped}）")
        return {"total": len(imgs), "detected": 0}

    errors.sort()
    n = len(errors)
    recall = detected / (len(imgs) - skipped)
    stats = {
        "total": len(imgs),
        "detected": detected,
        "skipped": skipped,
        "recall": recall,
        "mean_err": mean(errors),
        "median_err": median(errors),
        "max_err": max(errors),
        "hit_le2px": sum(1 for e in errors if e <= 2) / n,
        "hit_le5px": sum(1 for e in errors if e <= 5) / n,
        "hit_le10px": sum(1 for e in errors if e <= 10) / n,
    }
    return stats


def print_report(stats: dict):
    if not stats:
        return
    print("\n" + "=" * 50)
    print("滑块缺口检测评估报告")
    print("=" * 50)
    print(f"样本总数   : {stats.get('total', 0)}")
    print(f"检出数     : {stats.get('detected', 0)}  (recall={stats.get('recall', 0):.1%})")
    print(f"跳过(无标注): {stats.get('skipped', 0)}")
    print("-" * 50)
    if "mean_err" in stats:
        print(f"平均误差   : {stats['mean_err']:.2f} px")
        print(f"中位误差   : {stats['median_err']:.2f} px")
        print(f"最大误差   : {stats['max_err']:.2f} px")
        print(f"≤2px 命中率: {stats['hit_le2px']:.1%}  (目标)")
        print(f"≤5px 命中率: {stats['hit_le5px']:.1%}")
        print(f"≤10px 命中率: {stats['hit_le10px']:.1%}")
        # 目标判定
        if stats["hit_le2px"] >= 0.9:
            print("\n✓ 达标：≤2px 命中率 ≥ 90%")
        else:
            print(f"\n✗ 未达标：≤2px 命中率 {stats['hit_le2px']:.1%} < 90%，建议增加训练数据/epoch")
    print("=" * 50)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(DEFAULT_MODEL),
                    help="YOLO 模型路径")
    ap.add_argument("--conf", type=float, default=0.4,
                    help="置信度阈值")
    ap.add_argument("--split", default="val", choices=["val", "train"])
    args = ap.parse_args()

    if not Path(args.model).exists():
        print(f"[eval] 模型不存在: {args.model}")
        print("[eval] 请先运行: python scripts/train_slider.py")
        sys.exit(1)

    print(f"[eval] 模型: {args.model}")
    print(f"[eval] 置信度: {args.conf}  split: {args.split}")
    stats = evaluate(args.model, args.conf, args.split)
    print_report(stats)


if __name__ == "__main__":
    main()
