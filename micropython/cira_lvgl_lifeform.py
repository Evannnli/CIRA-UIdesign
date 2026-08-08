# -*- coding: utf-8 -*-
"""
CIRA 光生命体 · LVGL 版（lv_micropython, v9 假设）
================================================
复用 cira_lifeform 的全部数学/配色/形态参数（Evan 已确认观感），
仅把「输出」从 st77916.blit 换成 LVGL 缓冲区：
  · 渲染进 self.buf（RGB565 360×360 bytearray，全屏居中）
  · 由调用方把 buf 接到 lv.canvas / lv.img（注入 self._commit 钩子）
  · LVGL 负责 60fps 平滑合成 + 圆屏裁剪，根治「雷达图闪烁 / 一帧一帧」

本模块【不 import lvgl】，保持数学纯净、可在 Mac 桩上单测渲染逻辑。
唯一的 LVGL 耦合在调用方（cira_main_lvgl）。

⚠ 沙盒无硬件，本文件未真机运行；数学移植自已验证的 cira_lifeform v0.8.7。
"""
import time

# CPython 兼容垫片：仅 Mac 桩测试用；设备上是真 MicroPython，下面的 except 不触发。
try:
    time.ticks_ms
except AttributeError:
    import time as _t
    time.ticks_ms = lambda: _t.monotonic_ns() // 1_000_000
    time.ticks_diff = lambda a, b: a - b
    time.sleep_ms = lambda ms: _t.sleep(ms / 1000)

from cira_lifeform import (
    C_CORE_WARM, C_DIM, C_FAINT, C_BG_DARK,
    EMOTION_COLOR, STATE_EMOTION, STATE_PROFILE,
    GOLDEN, TAU, LAYERS, _BLOB, _INC_SCALE, _ch, _lerp,
    SUB_W, SUB_H, SUB_LOCAL_Y,
)

try:
    import subtitle_font
except Exception:
    subtitle_font = None

W = H = 360
CX = CY = 180


class Lifeform:
    def __init__(self, scale=0.6):
        self.state = "idle"
        self.emotion = "calm"
        self.color = C_CORE_WARM
        self.audio_level = 0.3
        self.tts_progress = 0.5
        self.pulse_energy = 0.0
        self.sub_text = ""
        self.sub_dim = False
        self.paused = False
        self.sleeping = False
        self._pf = dict(STATE_PROFILE["idle"])
        self._t0 = time.ticks_ms()
        self._last_blit = 0
        self._interval = 70       # LVGL 合成快，渲染间隔可收紧；算力吃紧就调大
        self._dirty = True
        self._tint = [C_CORE_WARM, 0xFC47, 0xFCF6]
        self._tint_n = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]

        self.buf = bytearray(W * H * 2)
        self._commit = None       # 调用方注入：把 buf 推到 LVGL（canvas.invalidate）
        self._build_bg()
        self._build_particles(scale)
        self._trail = []

        self._frames = 0
        self._err = None
        self._update_tint()

    # ── 预生成静态层（与 cira_lifeform 同算法，全屏 360）──
    def _build_bg(self):
        cx = W / 2; cy = H / 2
        self._bg = bytearray(W * H * 2)
        for y in range(H):
            for x in range(W):
                dx = (x - cx) / (W / 2)
                dy = (y - cy) / (H / 2)
                d = (dx * dx + dy * dy) ** 0.5
                if d <= 1.0:
                    r = max(0, int(26 * (1 - d) ** 1.3))
                    g = max(0, int(13 * (1 - d) ** 1.3))
                    b = max(0, int(8 * (1 - d) ** 1.3))
                else:
                    r = g = b = 0
                if d > 0.68:
                    vg = max(0.0, (d - 0.68) / 0.32)
                    r = int(r * (1 - 0.62 * vg))
                    g = int(g * (1 - 0.62 * vg))
                    b = int(b * (1 - 0.62 * vg))
                v = ((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (b & 0x1F)
                o = (y * W + x) * 2
                self._bg[o] = v >> 8
                self._bg[o + 1] = v & 0xFF

    def _build_particles(self, scale):
        import random
        self.particles = []
        for (n, r0, r1, s0, s1, flow, spin, layer) in LAYERS:
            cnt = max(1, int(n * scale + 0.5))
            for i in range(cnt):
                yy = 1 - 2 * (i + 0.5) / cnt
                rr = (max(0, 1 - yy * yy)) ** 0.5
                th = GOLDEN * i
                j = 0.16
                ux = math_cos(th) * rr + (random.random() - 0.5) * j
                uy = yy + (random.random() - 0.5) * j
                uz = math_sin(th) * rr + (random.random() - 0.5) * j
                ln = (ux * ux + uy * uy + uz * uz) ** 0.5 or 1
                roll = random.random()
                tint = 0 if roll < 0.70 else (1 if roll < 0.88 else 2)
                self.particles.append({
                    "ux": ux / ln, "uy": uy / ln, "uz": uz / ln,
                    "r0": r0 + random.random() * (r1 - r0),
                    "size": s0 + random.random() * (s1 - s0),
                    "flowRate": flow * (0.7 + random.random() * 0.6),
                    "spin": spin * (0.75 + random.random() * 0.5),
                    "layer": layer, "tint": tint,
                    "seed": random.random() * 100,
                    "twRate": 0.35 + random.random() * 1.3,
                    "twPhase": random.random() * TAU,
                })

    # ── 公共 API（与 cira_lifeform 对齐）──
    def set_state(self, s):
        if s not in STATE_PROFILE:
            s = "idle"
        if s != self.state:
            self._dirty = True
        self.state = s
        self.set_emotion(STATE_EMOTION.get(s, "calm"))

    def set_emotion(self, e):
        if e in EMOTION_COLOR:
            if e != self.emotion:
                self._dirty = True
            self.emotion = e
            self.color = EMOTION_COLOR[e]
            self._update_tint()

    def _update_tint(self):
        cols = (self.color, 0xFC47, 0xFCF6)
        for i, c in enumerate(cols):
            r, g, b = _ch(c)
            self._tint[i] = c
            self._tint_n[i][0] = r / 31.0
            self._tint_n[i][1] = g / 63.0
            self._tint_n[i][2] = b / 31.0

    def set_audio_level(self, v):
        self.audio_level = max(0.0, min(1.0, v))

    def set_tts_progress(self, v):
        self.tts_progress = max(0.0, min(1.0, v))

    def set_subtitle(self, text, dim=False):
        text = text or ""
        if text != self.sub_text or dim != self.sub_dim:
            self._dirty = True
        self.sub_text = text
        self.sub_dim = dim

    def pulse(self):
        self.pulse_energy = 1.0
        self._dirty = True

    def force(self):
        self._dirty = True

    def clear_screen(self):
        self.buf[:] = b'\x00' * (W * H * 2)

    # ── 加色沉积（与 cira_lifeform 同）──
    def _add(self, buf, x, y, ir, ig, ib):
        x = int(x); y = int(y)
        if 0 <= x < W and 0 <= y < H:
            o = (y * W + x) * 2
            v = (buf[o] << 8) | buf[o + 1]
            r = (v >> 11) & 31; g = (v >> 5) & 63; b = v & 31
            r = r + ir; g = g + ig; b = b + ib
            if r > 31: r = 31
            if g > 63: g = 63
            if b > 31: b = 31
            nv = (r << 11) | (g << 5) | b
            buf[o] = nv >> 8
            buf[o + 1] = nv & 0xFF

    def _splat(self, buf, x, y, tint, bright):
        tn = self._tint_n[tint]
        ic = _INC_SCALE * bright
        ir = int(ic * tn[0]); ig = int(ic * tn[1]); ib = int(ic * tn[2])
        if ir <= 0 and ig <= 0 and ib <= 0:
            return
        for (dx, dy, w) in _BLOB:
            self._add(buf, x + dx, y + dy, int(ir * w), int(ig * w), int(ib * w))

    # ── 主循环（由 LVGL 主循环 / 后台线程调用）──
    def tick(self, now_ms=None):
        if self.paused or self.sleeping:
            return
        now = time.ticks_ms() if now_ms is None else now_ms
        dt = time.ticks_diff(now, self._last_blit) / 1000.0
        if dt < 0:
            dt = 0
        if not self._dirty and dt * 1000 < self._interval:
            return
        self._last_blit = now
        self._dirty = False
        if dt > 0.05:
            dt = 0.05
        tgt = STATE_PROFILE[self.state]
        km = 1 - math_exp(-dt * 2.6)
        for k in ("breath", "spread", "coreGlow", "swirl", "flow", "ripple", "gain", "sag"):
            self._pf[k] += (tgt[k] - self._pf[k]) * km
        self._pf["morph"] = tgt["morph"]
        self.pulse_energy *= math_exp(-dt * 2.0)
        if self.pulse_energy < 0.001:
            self.pulse_energy = 0.0
        t = time.ticks_diff(now, self._t0) / 1000.0
        try:
            self._render(t)
        except Exception as e:
            if self._err is None:
                self._err = e
                print("[LF] render error:", e)
            return
        if self._commit is not None:
            try:
                self._commit()
            except Exception as e:
                if self._err is None:
                    self._err = e
                    print("[LF] commit error:", e)
        self._frames += 1
        if self._frames % 20 == 1:
            print("[LF] frame %d state=%s emotion=%s" % (self._frames, self.state, self.emotion))

    # ── 合成（全屏 360，居中 cx=cy=180）──
    def _render(self, t):
        buf = self.buf
        buf[:] = self._bg
        pf = self._pf
        breath = (1 + math_sin(t * 0.72) * pf["breath"]
                  + math_sin(t * 1.63 + 1.3) * pf["breath"] * 0.35
                  + self.pulse_energy * 0.26)
        spread = pf["spread"] * breath * (1 + self.pulse_energy * 0.22)
        gain = pf["gain"] * (1 + self.pulse_energy * 0.35)
        audio = self.audio_level
        morph = pf["morph"]

        coreN = 2
        for i in range(coreN):
            ph = i * 1.7
            dx = math_sin(t * 0.5 + ph) * W * 0.026
            dy = math_cos(t * 0.44 + ph) * W * 0.026
            rl = W * (0.050 + i * 0.045) * breath * (1 + audio * 0.10)
            flick = 0.78 + 0.14 * math_sin(t * 1.1 + ph) + 0.10 * math_sin(t * 0.8 + ph * 2)
            al = pf["coreGlow"] * gain * (0.11 - i * 0.035) * flick
            if al > 0.004:
                self._splat(buf, CX + dx, CY + dy + pf["sag"] * 0.5, 0, al * 1.2)
        rl = W * (0.022 + 0.004 * math_sin(t * 1.9)) * breath
        jx = math_sin(t * 0.7) * W * 0.010
        jy = math_cos(t * 0.63) * W * 0.010
        self._splat(buf, CX + jx, CY + jy + pf["sag"] * 0.5, 0, pf["coreGlow"] * gain * 0.30)

        for (px, py, tint, b) in self._trail:
            self._splat(buf, px, py, tint, b * 0.42)

        swirl = t * pf["swirl"]
        cur = []
        for p in self.particles:
            ang = swirl * p["spin"] + p["seed"]
            cs = math_cos(ang); sn = math_sin(ang)
            x = p["ux"] * cs - p["uz"] * sn
            z = p["ux"] * sn + p["uz"] * cs
            y = p["uy"]
            nq = math_sin(t * p["flowRate"] * 0.6 + p["seed"]) * 0.5 + \
                 math_sin(t * p["flowRate"] * 0.27 + p["seed"] * 1.7) * 0.5
            rad = p["r0"] * spread * (1 + nq * 0.26 * pf["flow"])
            if morph == "scatter":
                rad *= 1 + audio * 0.28 + 0.08 * math_sin(t * 3.4 + p["seed"])
            elif morph == "vortex":
                rad *= 0.82 + 0.18 * math_sin(t * 1.1 + p["seed"] * 0.3)
            elif morph == "wave":
                rad *= 1 + 0.13 * math_sin(t * 4.2 + y * 5 + self.tts_progress * TAU)
            elif morph == "droop":
                rad *= 0.92
            elif morph == "burst":
                rad *= 1 + self.pulse_energy * 0.45
            persp = 1.0 / (1.0 - z * 0.36)
            px = CX + x * rad * W * persp
            py = CY + y * rad * W * persp + pf["sag"]
            depth = (z + 1) * 0.5
            tw = 0.55 + 0.45 * math_sin(t * p["twRate"] + p["twPhase"])
            a2 = (0.075 + depth * 0.40) * tw * gain
            if p["layer"] == 3:
                a2 *= 0.40
            elif p["layer"] == 2:
                a2 *= 0.60
            elif p["layer"] == 0:
                a2 *= 0.52
            if a2 <= 0.004:
                continue
            self._splat(buf, px, py, p["tint"], a2)
            cur.append((px, py, p["tint"], a2))
        self._trail = cur

        if pf["ripple"] > 0.02:
            for i in range(3):
                ph = (t * (0.42 + audio * 0.55) + i / 3.0) % 1.0
                rr = W * (0.11 + ph * 0.36)
                ra = (1 - ph) * (1 - ph) * 0.30 * pf["ripple"] * (0.35 + audio * 0.85)
                self._ring(buf, CX, CY, rr, self.color, 2, ra)

        self._render_sub(buf)

    def _ring(self, buf, cx, cy, r, c, th=2, alpha=1.0):
        if r <= 0:
            return
        cx = int(cx); cy = int(cy)
        ro2 = (r + th) * (r + th)
        ri2 = max(0, (r - th) * (r - th))
        x0 = max(0, int(cx - r - th)); x1 = min(W - 1, int(cx + r + th))
        y0 = max(0, int(cy - r - th)); y1 = min(H - 1, int(cy + r + th))
        tn = self._tint_n[0]
        ic = _INC_SCALE * alpha
        ir = int(ic * tn[0]); ig = int(ic * tn[1]); ib = int(ic * tn[2])
        for y in range(y0, y1 + 1):
            dy = y - cy; dy2 = dy * dy
            for x in range(x0, x1 + 1):
                dx = x - cx
                d2 = dx * dx + dy2
                if d2 <= ro2 and d2 >= ri2:
                    self._add(buf, x, y, ir, ig, ib)

    def _render_sub(self, buf):
        if subtitle_font is None:
            return
        text = self.sub_text
        if not text:
            return
        col = C_DIM if self.sub_dim else C_CORE_WARM
        cpl = W // subtitle_font.CELL
        line_h = 14
        lines = [text[i:i + cpl] for i in range(0, len(text), cpl)]
        if len(lines) > 3:
            lines = lines[:2] + [lines[2][:cpl - 1] + "…"]
        for li, line in enumerate(lines):
            y = SUB_LOCAL_Y + li * line_h
            n = len(line)
            startx = (W - n * subtitle_font.CELL) // 2
            for ci, ch in enumerate(line):
                idx = subtitle_font.CHARSET.find(ch)
                if idx < 0:
                    continue
                gx = startx + ci * subtitle_font.CELL
                g = subtitle_font.GLYPHS[idx * subtitle_font.BYTES_PER_GLYPH:
                                      (idx + 1) * subtitle_font.BYTES_PER_GLYPH]
                hi = (col >> 8) & 255; lo = col & 255
                for yy in range(subtitle_font.CELL):
                    for xx in range(subtitle_font.CELL):
                        bit = yy * subtitle_font.CELL + xx
                        if (g[bit >> 3] >> (7 - (bit & 7))) & 1:
                            px = gx + xx; py = y + yy
                            if 0 <= px < W and 0 <= py < H:
                                o = (py * W + px) * 2
                                buf[o] = hi; buf[o + 1] = lo


# ── 本地 math 别名（避免顶部 import math 与本文件命名冲突，保持可读）──
import math as _m
math_cos = _m.cos
math_sin = _m.sin
math_exp = _m.exp
