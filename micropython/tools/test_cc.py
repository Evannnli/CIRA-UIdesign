# -*- coding: utf-8 -*-
# 本机桩件验证 cira_control_center：所有视图绘制不崩 + 状态机进/出正确。
import sys, os, types, time as _time
# MicroPython 专有 time API 桩（本机 CPython 没有）
_clk = [0]
def _ticks_ms():
    _clk[0] += 40
    return _clk[0]
def _ticks_diff(a, b):
    return a - b
_time.ticks_ms = _ticks_ms
_time.ticks_diff = _ticks_diff
_time.sleep_ms = lambda ms: None   # 本机不真睡
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 桩 disp
class FakeDisp:
    def __init__(self):
        self.rects = 0
    def fill(self, c): pass
    def fill_rect(self, x, y, w, h, c):
        self.rects += 1

# 桩 touch：seq = [(touching_bool, point_or_None), ...]，每个 touching() 调用消费一个；
# read_point 向后扫描最近一次 True 对应的坐标（脚本尾部耗尽也能拿到正确点）。
class FakeTouch:
    def __init__(self, seq):
        self._seq = seq
        self._i = 0
    def touching(self):
        v = self._seq[self._i][0] if self._i < len(self._seq) else False
        self._i += 1
        return v
    def take_edge(self):
        return False
    def read_point(self):
        for k in range(min(self._i, len(self._seq) - 1), -1, -1):
            if self._seq[k][0] and self._seq[k][1] is not None:
                p = self._seq[k][1]
                return (p[0], p[1], 1)
        return (180, 180, 0)
    def clear_edge(self):
        pass


def _make_seq(taps):
    seq = [(False, None)]          # 进场 wait_release
    for (x, y) in taps:
        seq.append((True, (x, y)))
        for _ in range(8):          # 足够多的释放帧（覆盖 RELEASE_MS）
            seq.append((False, None))
    return seq

# 桩 subtitle_font / 依赖（让模块可导入）
_nce = "设置Wi-Fi蓝牙音量亮度模式正常轻声故事完成%"
sf = types.SimpleNamespace(CHARSET=_nce,
                           CELL=12, GLYPHS=bytes(len(_nce) * 18), BYTES_PER_GLYPH=18)
sys.modules["subtitle_font"] = sf
sys.modules["cira_pins"] = types.SimpleNamespace(VOLUME_DB=-20.0, LCD_W=360, LCD_H=360)
sys.modules["cira_audio"] = types.SimpleNamespace(get_codec=lambda: types.SimpleNamespace(set_volume=lambda v: None))
sys.modules["cira_display"] = types.SimpleNamespace(set_nit=lambda v: None)

import cira_control_center as CC

fdisp = FakeDisp()

# 1) 所有视图绘制不崩
views = ["home", "wifi", "bt", "vol", "bri", "mode"]
for v in views:
    for sel in range(0, 6):
        CC._redraw(fdisp, v, sel)
print("[OK] _redraw 所有视图/选中态无异常")

# 2) 调节
CC._state["volume_db"] = -20.0
CC._adjust("vol", +1); assert CC._vol_pct() == 84, CC._vol_pct()   # -20+5=-15 → 84%
CC._adjust("vol", -1); assert CC._vol_pct() == 79, CC._vol_pct()   # -15-5=-20 → 79%
CC._state["nit"] = 250
CC._adjust("bri", +1); assert CC._state["nit"] == 255, CC._state["nit"]   # 250+20=270 → 钳位 255
CC._adjust("bri", -1); assert CC._state["nit"] == 235, CC._state["nit"]
CC._state["mode"] = 0
CC._adjust("mode", +1); assert CC._state["mode"] == 1
CC._adjust("mode", +1); assert CC._state["mode"] == 2
CC._adjust("mode", +1); assert CC._state["mode"] == 0
print("[OK] _adjust 音量/亮度/模式 调节正确（含钳位）")

# 3) 行命中 / 完成区
assert CC._row_at(170) == 2
assert CC._row_at(60) == 0
assert CC._in_done(320) is True
assert CC._in_done(200) is False
print("[OK] _row_at / _in_done 命中正确")

# 4) 状态机：进 vol → 返回 → 点完成退出
# 点序：行2(vol,y=170) → 中点返回(x=180) → 完成按钮(y=320)
ft = FakeTouch(_make_seq([(180, 170), (180, 170), (180, 320)]))
try:
    CC.run(None, ft, fdisp)
    print("[OK] run() 状态机：home→vol→home→done 正常退出，无异常")
except Exception as e:
    import traceback; traceback.print_exc()
    print("[FAIL] run() 异常:", e)
    sys.exit(1)
print("disp.rects 总调用:", fdisp.rects)
