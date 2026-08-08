# -*- coding: utf-8 -*-
"""
把 CIRA 光生命体（cira_lvgl_lifeform 的数学，即 LVGL 版星云）渲染成 PNG 预览，
让 Evan 在真机刷入前就能看到「长什么样」。
纯 Mac/CPython 运行；依赖 PIL。不进设备。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "micropython"))

from PIL import Image
from cira_lvgl_lifeform import Lifeform, W, H

OUT = os.path.join(os.path.dirname(__file__), "..", "preview")
os.makedirs(OUT, exist_ok=True)


def buf_to_png(buf, path):
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        for x in range(W):
            o = (y * W + x) * 2
            v = (buf[o] << 8) | buf[o + 1]
            r = (v >> 11) & 31
            g = (v >> 5) & 63
            b = v & 31
            px[x, y] = (r * 255 // 31, g * 255 // 63, b * 255 // 31)
    img.save(path)


# 五个状态：展示不同情绪配色（正好对应 HTML 原型的情绪色）
STATES = ["idle", "listen", "think", "speak", "offline"]

for st in STATES:
    lf = Lifeform(scale=0.6)
    lf.set_state(st)
    lf.set_audio_level(0.5)
    lf.set_subtitle("你好呀 我是 CIRA" if st in ("speak", "listen") else "")
    base = 1000
    # 模拟 ~4 秒，让星云沉积到稳态
    for i in range(90):
        lf.tick(now_ms=base + i * 50)
    path = os.path.join(OUT, "lifeform_%s.png" % st)
    buf_to_png(lf.buf, path)
    print("saved %-8s frames=%d err=%s -> %s" % (st, lf._frames, lf._err, path))
