"""指纹管理测试：固定性 + 持久化。"""
import json
from pathlib import Path

from engine.fingerprint import FingerprintManager


def test_fingerprint_persistent(tmp_path: Path):
    mgr = FingerprintManager(tmp_path)
    fp1 = mgr.get("shop_test")
    fp2 = mgr.get("shop_test")
    assert fp1.user_agent == fp2.user_agent          # 二次取值一致
    assert (tmp_path / "shop_test.json").exists()    # 已落盘


def test_fingerprint_per_shop_isolated(tmp_path: Path):
    mgr = FingerprintManager(tmp_path)
    a = mgr.get("shop_a")
    b = mgr.get("shop_b")
    assert a.shop_id != b.shop_id
    assert (tmp_path / "shop_a.json").exists()
    assert (tmp_path / "shop_b.json").exists()
