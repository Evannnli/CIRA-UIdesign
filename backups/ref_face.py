# -*- coding: utf-8 -*-
"""
CIRA 表情屏渲染（MicroPython）
==============================
一个极简「画布」抽象 + 两个后端（圆形 TFT / OLED），
face.draw_emotion() 只调用画布的通用图元，所以换屏不用改表情逻辑。

后端只需实现：fill(c) / hline(x,y,w,c) / vline(x,y,h,c) / line(x0,y0,x1,y1,c)
（颜色整数，单色屏自动把非零当亮）。

依赖（烧录时一起传进板子）：
  - 圆形屏（1.85C-BOX）：st77916.py（ST77916 QSPI 驱动，已点亮；见该文件头部协议说明）
  - OLED          ：ssd1306.py（micropython-lib 自带）

🎁 1.85C-BOX 板载能力（可后续利用）：
  · RTC（PCF85063）—— CIRA 可感知当前时间，"早上好/该睡觉啦"等时间交互
  · Micro SD 卡槽 —— 可存离线 NIMO 表情包 / 语音素材
  · 262K 色 TFT —— 画 NIMO 几何脸够用（GIF 硬解能力以官方 wiki 为准，不确定）
"""

import math
from emotions import spec


# ── 画布抽象：只用最基础的图元，所有几何都在这里实现 ──────────
class Canvas:
    W = 128
    H = 64

    def fill(self, c): raise NotImplementedError
    def hline(self, x, y, w, c): raise NotImplementedError
    def vline(self, x, y, h, c): raise NotImplementedError
    def line(self, x0, y0, x1, y1, c): raise NotImplementedError

    # 以下几何基于上面的图元，两个后端通用 ——
    def disc(self, cx, cy, r, c):
        r2 = r * r
        for y in range(-r, r + 1):
            yy = cy + y
            if yy < 0 or yy >= self.H:
                continue
            half = int(math.sqrt(max(0, r2 - y * y)))
            self.hline(cx - half, yy, half * 2 + 1, c)

    def ring(self, cx, cy, r, c, t=2):
        # 用「外实心圆 + 内背景圆」抠出圆环，避免各驱动 arc 接口不一致
        self.disc(cx, cy, r, c)
        self.disc(cx, cy, r - t, 0)  # 中间填背景（0=黑）

    def polyline(self, pts, c):
        for i in range(len(pts) - 1):
            self.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], c)

    def bitmap(self, x, y, w, h, bits, color):
        """画 1-bit 位图（MSB 先、行优先）。bit=1 处填 color，bit=0 留背景。"""
        stride = (w + 7) // 8
        for j in range(h):
            row = bits[j * stride:(j + 1) * stride]
            run = -1
            for i in range(w):
                byte = row[i >> 3]
                bit = (byte >> (7 - (i & 7))) & 1
                if bit and run < 0:
                    run = i
                if (not bit or i == w - 1) and run >= 0:
                    end = i + (1 if bit else 0)
                    self.hline(x + run, y + j, end - run, color)
                    run = -1


# ── 后端 1：圆形 TFT LCD（ST77916 · 微雪 1.85C-BOX）──────────
# 实际分辨率 360×360（官方 wiki 确认）；ST77916 走 QSPI
class ST77916Canvas(Canvas):
    """微雪 ESP32-S3-Touch-LCD-1.85C-BOX 内置驱动（360×360 圆形 TFT）"""

    def __init__(self, display, w=360, h=360):
        self.d = display
        self.W, self.H = w, h

    def fill(self, c):
        self.d.fill(c)

    def hline(self, x, y, w, c):
        self.d.hline(x, y, w, c)

    def vline(self, x, y, h, c):
        self.d.vline(x, y, h, c)

    def line(self, x0, y0, x1, y1, c):
        self.d.line(x0, y0, x1, y1, c)

    def fill_rect(self, x, y, w, h, c):
        self.d.fill_rect(x, y, w, h, c)

    def blit(self, buf, x, y, w, h):
        self.d.blit(buf, x, y, w, h)


# ── 兼容别名：旧代码引用 CO5300/GC9A01 时仍可工作 ──────────────
CO5300Canvas = ST77916Canvas
GC9A01Canvas = ST77916Canvas


# ── 后端 2：SSD1306 OLED（单色，0/1）──────────────────────
class SSD1306Canvas(Canvas):
    def __init__(self, display, w=128, h=64):
        self.d = display
        self.W, self.H = w, h

    def _c(self, c):
        return 1 if c else 0  # 单色：非零即亮

    def fill(self, c):
        self.d.fill(self._c(c))

    def hline(self, x, y, w, c):
        self.d.hline(x, y, w, self._c(c))

    def vline(self, x, y, h, c):
        self.d.vline(x, y, h, self._c(c))

    def line(self, x0, y0, x1, y1, c):
        self.d.line(x0, y0, x1, y1, c)

    def fill_rect(self, x, y, w, h, c):
        self.d.fill_rect(x, y, w, h, self._c(c))


# ── 表情绘制 ──────────────────────────────────────────────
def draw_emotion(canvas, name, tint_override=None):
    if canvas is None:
        # DISPLAY_TYPE=none：跳过屏幕，只在 REPL 打印当前表情名
        print(f"[表情] {name}")
        return
    s = spec(name)
    W, H = canvas.W, canvas.H
    cx, cy = W // 2, H // 2   # 圆心在物理中心（360×360 的中心点）
    r = min(W, H) // 2 - 6     # 用短边算半径，确保脸盘不溢出

    # 清屏 + 脸盘
    canvas.fill(0)
    face_color = tint_override if tint_override is not None else s["tint"]
    canvas.ring(cx, cy, r, face_color, t=4)

    feature = 0xFFFF if (face_color != 0xFFFF) else 0x0000
    # OLED 单色：脸盘亮、五官暗；圆形屏：脸盘是 tint，五官用对比色
    if face_color == 0xFFFF:
        fcolor = 0x0000
    else:
        fcolor = 0xFFFF
    eye_y = cy - int(r * 0.18)
    ex = int(r * 0.40)
    er = max(3, int(r * 0.13))

    # 眼睛
    if s["eyes"] == "open":
        canvas.disc(cx - ex, eye_y, er, fcolor)
        canvas.disc(cx + ex, eye_y, er, fcolor)
    elif s["eyes"] == "wide":
        canvas.disc(cx - ex, eye_y, int(er * 1.4), fcolor)
        canvas.disc(cx + ex, eye_y, int(er * 1.4), fcolor)
    elif s["eyes"] == "half":
        canvas.hline(cx - ex - er, eye_y, er * 2, fcolor)
        canvas.hline(cx + ex - er, eye_y, er * 2, fcolor)
    else:  # closed
        canvas.line(cx - ex - er, eye_y, cx - ex + er, eye_y, fcolor)
        canvas.line(cx + ex - er, eye_y, cx + ex + er, eye_y, fcolor)

    # 眉毛
    by = eye_y - er - 4
    if s["brows"] == "up":
        canvas.line(cx - ex - er, by + 3, cx - ex + er, by, fcolor)
        canvas.line(cx + ex - er, by, cx + ex + er, by + 3, fcolor)
    elif s["brows"] == "down":
        canvas.line(cx - ex - er, by, cx - ex + er, by + 3, fcolor)
        canvas.line(cx + ex - er, by + 3, cx + ex + er, by, fcolor)
    elif s["brows"] == "flat":
        canvas.hline(cx - ex - er, by, er * 2, fcolor)
        canvas.hline(cx + ex - er, by, er * 2, fcolor)

    # 嘴（弧线：M>0 微笑，M<0 撇嘴）
    M = s["mouth"]
    mw = int(r * 0.55)
    base_y = cy + int(r * 0.42)
    pts = []
    n = 16
    for i in range(n + 1):
        x = -mw + (2 * mw) * i // n
        y = base_y - int((M * x * x) / (mw * 2))
        pts.append((cx + x, y))
    canvas.polyline(pts, fcolor)

    # 睡/待机：画个小 z
    if s.get("z"):
        zx, zy = cx + int(r * 0.55), cy - int(r * 0.6)
        canvas.line(zx, zy, zx + 8, zy, fcolor)
        canvas.line(zx + 8, zy, zx, zy + 8, fcolor)
        canvas.line(zx, zy + 8, zx + 8, zy + 8, fcolor)


def make_canvas(display_type, display, w=128, h=64):
    if display_type == "round":
        return ST77916Canvas(display, w, h)
    return SSD1306Canvas(display, w, h)
