"""飞书写入失败补偿同步：定时重试本地落盘的失败记录。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import get_config
from integrations.feishu.bitable import compensate_fallback


def main():
    n = compensate_fallback(get_config().feishu)
    print(f"[feishu_compensate] synced {n} fallback records")


if __name__ == "__main__":
    main()
