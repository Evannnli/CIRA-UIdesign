# -*- coding: utf-8 -*-
# 本机冒烟：cira_lifeform 用软斑 _BLOB 渲染不崩 + 各状态可切。
import sys, os, types, time as _time
_clk = [0]
_time.ticks_ms = lambda: (_clk.__setitem__(0, _clk[0]+40) or _clk[0])
_time.ticks_diff = lambda a, b: a - b
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules["cira_emotions"] = types.SimpleNamespace(
    C_CORE=0xFF17, C_WARM=0xFD40, C_PINK=0xFC0F, C_PURPLE=0xCC99)
sf = types.SimpleNamespace(CHARSET="测试", CELL=12, GLYPHS=bytes(18), BYTES_PER_GLYPH=18)
sys.modules["subtitle_font"] = sf

import cira_lifeform as LF

class FakeCanvas:
    def __init__(self):
        self.W = 360; self.H = 360; self.blits = 0
    def blit(self, buf, x, y, w, h):
        self.blits += 1
    def fill(self, c):
        pass

cv = FakeCanvas()
lf = LF.Lifeform(cv, scale=0.6)
print("[OK] 构建完成（blobs=%d）" % len(LF._BLOB))
for st in ("idle", "listen", "think", "speak", "wake", "offline"):
    lf.set_state(st)
    for _ in range(3):
        lf.tick()
print("[OK] 六态各 tick 数帧无异常，blits=%d" % cv.blits)
print("[OK] 星云软斑渲染冒烟通过")
