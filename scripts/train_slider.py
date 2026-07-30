"""滑块缺口检测 YOLOv8 模型训练脚本（生产级数据增强 + 早停 + 模型固化）。

数据准备：
  scripts/datasets/slider/images/train/*.jpg   （含缺口 + 滑块块）
  scripts/datasets/slider/images/val/*.jpg
  scripts/datasets/slider/labels/train/*.txt   （YOLO 标注：0=缺口, 1=滑块块）
  scripts/datasets/slider/labels/val/*.txt

训练完成后自动把 best.pt 复制到 data_persist/slider_gap_yolov8n.pt，
供 engine/captcha/slider_detect.py 推理使用。

数据增强策略（针对滑块验证码特性）：
  - HSV 亮度/饱和度扰动：模拟不同光照条件
  - 平移/缩放：模拟缺口位置与尺寸抖动
  - 小角度旋转：模拟轻微倾斜
  - 关闭水平翻转：滑块缺口有方向性（凸起在右），翻转会破坏语义
  - Mosaic：提升小数据集泛化

用法：
  python scripts/train_slider.py --epochs 100 --imgsz 640
  python scripts/train_slider.py --quick        # 快速验证管线（3 epoch，关闭增强）
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA_YAML = ROOT / "scripts" / "datasets" / "slider" / "data.yaml"
# 训练后固化到此路径（config/captcha.yaml 的 slider_model 字段一致）
MODEL_FIX_PATH = ROOT / "data_persist" / "slider_gap_yolov8n.pt"

# 生产级数据增强参数（滑块验证码特化）
AUG_CONFIG = {
    "hsv_h": 0.015,        # 色相微扰
    "hsv_s": 0.5,          # 饱和度扰动
    "hsv_v": 0.4,          # 亮度扰动（核心：模拟光照变化）
    "degrees": 5.0,        # 小角度旋转
    "translate": 0.1,      # 平移
    "scale": 0.3,          # 缩放
    "shear": 2.0,          # 轻微剪切
    "perspective": 0.0,    # 关闭透视（滑块为平面）
    "flipud": 0.0,         # 关闭垂直翻转
    "fliplr": 0.0,         # 关闭水平翻转（凸起方向有语义）
    "mosaic": 0.5,         # 半概率 Mosaic
    "mixup": 0.0,          # 关闭 mixup
    "copy_paste": 0.0,     # 关闭 copy_paste
}


def ensure_data_yaml():
    ds = ROOT / "scripts" / "datasets" / "slider"
    ds.mkdir(parents=True, exist_ok=True)
    if not DATA_YAML.exists():
        DATA_YAML.write_text(
            f"path: {ds.as_posix()}\n"
            "train: images/train\n"
            "val: images/val\n"
            "names:\n  0: gap\n  1: slider\n",
            encoding="utf-8",
        )
        print(f"[train] wrote {DATA_YAML}")


def check_dataset():
    """校验数据集就绪，返回 (train_n, val_n)。"""
    ds = ROOT / "scripts" / "datasets" / "slider"
    train_imgs = list((ds / "images" / "train").glob("*.jpg")) if (ds / "images" / "train").exists() else []
    val_imgs = list((ds / "images" / "val").glob("*.jpg")) if (ds / "images" / "val").exists() else []
    if not train_imgs or not val_imgs:
        print(f"[train] 数据集未就绪：train={len(train_imgs)} val={len(val_imgs)}")
        print("[train] 请先运行: python scripts/gen_slider_dataset.py --train 400 --val 80")
        return 0, 0
    return len(train_imgs), len(val_imgs)


def fixate_best_model(save_dir):
    """训练完成后把 best.pt 复制到 data_persist 供推理使用。"""
    best = Path(save_dir) / "weights" / "best.pt"
    if not best.exists():
        print(f"[train] 警告：best.pt 未找到于 {best}")
        return None
    MODEL_FIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best, MODEL_FIX_PATH)
    print(f"[train] best.pt 已固化到 {MODEL_FIX_PATH}")
    return MODEL_FIX_PATH


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--batch", type=int, default=8,
                        help="batch size（显存不足时降到 4）")
    parser.add_argument("--workers", type=int, default=2,
                        help="DataLoader worker 数（Windows 建议 0-2，避免多进程异常）")
    parser.add_argument("--patience", type=int, default=20,
                        help="早停耐心值：连续 N epoch 无提升则停")
    parser.add_argument("--quick", action="store_true",
                        help="快速验证管线：3 epoch + 关闭增强")
    args = parser.parse_args()

    from ultralytics import YOLO

    ensure_data_yaml()
    train_n, val_n = check_dataset()
    if not train_n or not val_n:
        sys.exit(1)

    # quick 模式：覆盖参数用于管线验证
    epochs = 3 if args.quick else args.epochs
    aug = {} if args.quick else AUG_CONFIG
    if args.quick:
        print("[train] QUICK 模式：3 epoch，关闭数据增强，仅验证管线")

    print(f"[train] 数据集 train={train_n} val={val_n}")
    print(f"[train] epochs={epochs} imgsz={args.imgsz} batch={args.batch} "
          f"workers={args.workers} patience={args.patience}")

    model = YOLO(args.model)
    results = model.train(
        data=str(DATA_YAML),
        epochs=epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        patience=args.patience,
        project=str(ROOT / "data_persist"),
        name="slider_gap_yolov8n",
        exist_ok=True,
        # 验证监控
        val=True,
        # 数据增强（quick 模式下为空，用 ultralytics 默认最小增强）
        **aug,
    )

    save_dir = results.save_dir if hasattr(results, "save_dir") else None
    if save_dir:
        print(f"[train] 训练完成，save_dir={save_dir}")
        fixate_best_model(save_dir)
    else:
        print("[train] 训练完成（无 save_dir）")

    # 打印最佳验证指标
    try:
        metrics = results.results_dict if hasattr(results, "results_dict") else {}
        if metrics:
            print("[train] 最佳验证指标:")
            for k, v in metrics.items():
                print(f"  {k}: {v}")
    except Exception as e:
        print(f"[train] 指标读取失败: {e}")


if __name__ == "__main__":
    main()
