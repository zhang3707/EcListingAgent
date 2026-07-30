"""数据库初始化：建表。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.db import get_engine
from data.models import Base


def main():
    Base.metadata.create_all(get_engine())
    print("[init_db] tables created")


if __name__ == "__main__":
    main()
