"""滑块轨迹生成测试。"""
from engine.captcha.slider_track import gen_track


def test_gen_track_distance_zero():
    track = gen_track(0)
    assert track == [(0.0, 0.0, 0)]


def test_gen_track_basic_properties():
    track = gen_track(200)
    assert len(track) > 10
    # 起点 x 为 0，终点 x 回到目标距离
    assert track[0][0] == 0.0
    assert abs(track[-1][0] - 200.0) < 1e-6
    # 每点 dt 为非负整数
    for _, _, dt in track:
        assert isinstance(dt, int) and dt >= 0


def test_gen_track_has_overshoot():
    """轨迹应出现过冲（中间某点 x 超过目标距离）。"""
    track = gen_track(150)
    xs = [p[0] for p in track]
    assert max(xs) > 150.0
