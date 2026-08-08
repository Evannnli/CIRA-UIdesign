# -*- coding: utf-8 -*-
"""
路线 B（v0.8.8）冒烟测试 · Mac 桩（不依赖硬件，验证改动逻辑不崩 + 行为正确）

验证两件事：
  1) 星云 cira_lifeform._interval == 0 → 取消限帧，每帧 tick 都 blit（不再 220ms 跳变）。
  2) 控制中心 cira_control_center._redraw_sub_dynamic 只刷局部（大数值+滑块区），
     重绘面积远小于整屏（根治拖动时整屏闪）。
cira_control_center 顶部 import 了硬件模块（cira_display/cira_audio/...），
这里在 import 前用 sys.modules 注入 mock，避免 Mac 上 import 失败。
"""
import sys
import os
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MICRO = os.path.join(os.path.dirname(HERE), "micropython")
sys.path.insert(0, MICRO)

# ── mock 硬件依赖模块（仅 Mac 桩用；设备上由真实固件提供）──
for _m in ("machine", "cira_audio", "cira_display", "cira_pins", "cira_expander"):
    if _m not in sys.modules:
        sys.modules[_m] = types.ModuleType(_m)
sys.modules["cira_display"].set_nit = lambda *a, **k: None
sys.modules["cira_audio"].get_codec = lambda: types.SimpleNamespace(
    set_volume=lambda *a, **k: None)
sys.modules["cira_pins"].VOLUME_DB = -20.0

# CPython 无 MicroPython 的 time.ticks_ms / ticks_diff，补垫片供 Mac 桩用（不碰设备代码）
import time as _time
if not hasattr(_time, "ticks_ms"):
    _time.ticks_ms = lambda: 0
    _time.ticks_diff = lambda a, b: a - b


# ── Fake 显示对象（记录调用）──
class FakeDisp:
    def __init__(self):
        self.calls = []

    def fill(self, c):
        self.calls.append(("fill", c))

    def fill_rect(self, x, y, w, h, c):
        self.calls.append(("fill_rect", x, y, w, h, c))

    def blit(self, *a):
        self.calls.append(("blit",) + a)


class FakeCanvas:
    def __init__(self):
        self.blits = 0

    def blit(self, buf, x, y, w, h):
        self.blits += 1

    def fill(self, c):
        pass


def _count(disp):
    """统计 fill_rect 调用次数（SPI 交易次数的代理：每次 fill_rect 一次 SPI 写）。"""
    return sum(1 for c in disp.calls if c[0] == "fill_rect")


def main():
    # ── 1) 星云：取消限帧 ──
    import cira_lifeform as LF
    cv = FakeCanvas()
    lf = LF.Lifeform(cv, scale=0.3)
    assert lf._interval == 0, "路线 B：_interval 应为 0（取消限帧）"
    # 连续三帧（手动传 now_ms 绕过 CPython 无 ticks_ms）
    lf.tick(0)
    lf.tick(50)
    lf.tick(100)
    assert cv.blits >= 3, "取消限帧后每帧都应 blit"
    assert lf._frames >= 3, "帧计数器应增长"
    print("[1] 星云取消限帧 OK: blits=%d frames=%d" % (cv.blits, lf._frames))

    # 状态切换不崩
    lf.set_state("listen"); lf.tick(200)
    lf.set_state("think"); lf.tick(300)
    lf.set_state("speak"); lf.tick(400)
    lf.set_state("offline"); lf.tick(500)
    print("[1] 星云六态切换 OK: frames=%d" % lf._frames)

    # ── 2) 控制中心：局部刷新 ──
    import cira_control_center as CC
    # 基准：整屏 redraw home 的面积
    disp = FakeDisp()
    CC._redraw(disp, "home", 0)
    home_count = _count(disp)
    # 拖动子视图：只刷局部
    disp.calls.clear()
    CC._redraw_sub_dynamic(disp, "vol")
    dyn_count = _count(disp)
    print("[2] 整屏 redraw fill_rect 次数=%d, 局部刷新 fill_rect 次数=%d"
          % (home_count, dyn_count))
    assert dyn_count < home_count * 0.5, "局部刷新调用次数应远少于整屏重绘（SPI 交易更少→更顺）"

    # mode 子视图（非滑块）也应不崩且只刷局部
    disp.calls.clear()
    CC._redraw_sub_dynamic(disp, "mode")
    mode_count = _count(disp)
    print("[2] mode 子视图局部刷新 OK: fill_rect 次数=%d" % mode_count)
    assert mode_count < home_count * 0.5

    print("\nROUTE B SMOKE: ALL OK")


if __name__ == "__main__":
    main()
