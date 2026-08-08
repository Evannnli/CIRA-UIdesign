# -*- coding: utf-8 -*-
"""
CIRA 光生命体渲染器 · 星云版（MicroPython · 360×360 圆形 TFT）
=============================================================
移植自 Evannnli/CIRA-UIdesign 的 Nebula 引擎（HANDOFF.md §5 / lifeform.js），
按本板「软模拟 QSPI」刷新限制做了硬件可行化：

  · 原型 = ~1400 锐利星点加色混合 60fps canvas；本板整屏重绘 1.5~3s，不可照搬。
  · 本实现：在 PSRAM 维护一个【中央窗口帧缓冲】(220×256)，RAM 里合成（极快），
    每帧只做【一次 blit】刷到屏（bulk blit 约 0.5~0.9s）。
  · 星云 = 数千颗锐利小星点，靠「密核→稀边」密度梯度堆叠出朦胧感（不用大柔光斑），
    对齐 HANDOFF §5.1/§5.2。星点精灵改为「加色沉积核」（中心亮、四邻极淡），单颗是点不是糊。
  · 4 层 3D 球面粒子（Fibonacci）+ 透视 + 旋流 + 噪声形变（用 per-particle 相位 sin 近似，
    避免 FBM 的 6 个 trig/粒子，省算力）。状态形态参数 STATE_PROFILE 与 HANDOFF §5.5 对齐。
  · 颜色色散：70% 主色 / 18% 暖橙 / 12% 软粉（HANDOFF §5.2）。
  · 中心雾核减弱（2 层极淡底辉 + 极小亮核），亮度主要由密集核心尘堆叠形成。
  · 字幕合成进同一帧缓冲顶部（免黑底矩形盖住光晕）。

性能：默认约 360 颗粒子（NEBULA_SCALE 可调，板子慢就调小）。后台线程按 ~4~5fps 调
tick() 把状态画出来，规避录音/思考阻塞导致动画卡死。

铁律：本模块只碰「显示」，不动音频/模型/语音链路/配网（Evan 2026-08-07 已定）。

画布接口：只用到 canvas.blit(buf,x,y,w,h) 与 canvas.fill(c)。本板 frozen
st77916.ST77916 两者都有，cira_face.ST77916Canvas 也都有，直接传即可。
"""

import math
import time

try:
    import subtitle_font
except Exception:
    subtitle_font = None   # 字幕字体缺失时跳过字幕渲染（不影响光生命体本体）

from cira_emotions import C_CORE, C_WARM, C_PINK, C_PURPLE

# ── 配色（RGB565，全暖色系，禁绿）──────────────────────────
C_CORE_WARM = 0xFF17   # #FFE3BC 暖白（核心光，避屏幕色温推绿）
C_DIM       = 0xDE15   # #D8C0A8 暖白弱化（worried / 离线点缀）
C_FAINT     = 0x9C0E   # #9A8270 很暗暖白（sleepy）
C_BG_DARK   = 0x1861   # 中央窗口底色（极暗暖，接近黑）

EMOTION_COLOR = {
    "calm":     C_CORE_WARM,
    "curious":  C_WARM,
    "happy":    C_WARM,
    "thinking": C_PURPLE,
    "comfort":  C_PINK,
    "worried":  C_DIM,
    "sleepy":   C_FAINT,
}
STATE_EMOTION = {
    "idle": "calm", "listen": "curious", "think": "thinking",
    "speak": "happy", "offline": "worried", "settings": "calm",
    "wake": "calm",
}

# 状态形态参数（对齐 HANDOFF §5.5 STATE_PROFILE）
STATE_PROFILE = {
    "idle":     {"breath": .040, "spread": 1.00, "coreGlow": .55, "swirl": .055, "flow": .42, "ripple": 0,   "morph": "sphere",  "gain": 1.00, "sag": 0},
    "listen":   {"breath": .060, "spread": 1.20, "coreGlow": .72, "swirl": .160, "flow": .78, "ripple": 1,   "morph": "scatter", "gain": 1.12, "sag": 0},
    "think":    {"breath": .028, "spread": 0.88, "coreGlow": .88, "swirl": .620, "flow": .98, "ripple": 0,   "morph": "vortex",  "gain": 1.05, "sag": 0},
    "speak":    {"breath": .070, "spread": 1.06, "coreGlow": .76, "swirl": .100, "flow": .66, "ripple": .45, "morph": "wave",    "gain": 1.10, "sag": 0},
    "offline":  {"breath": .030, "spread": 0.78, "coreGlow": .20, "swirl": .018, "flow": .20, "ripple": 0,   "morph": "droop",   "gain": 0.38, "sag": 22},
    "wake":     {"breath": .100, "spread": 1.34, "coreGlow": .98, "swirl": .340, "flow": 1.15, "ripple": 0,   "morph": "burst",   "gain": 1.30, "sag": 0},
}

GOLDEN = math.pi * (3 - math.sqrt(5))
TAU = math.pi * 2

# 4 层粒子（HANDOFF §5.1，数量按 NEBULA_SCALE 缩放）
#  n, rMin, rMax, sMin, sMax, flow, spin, layer
LAYERS = (
    (120, 0.030, 0.130, 0.45, 1.15, 1.35, 1.55, 0),  # 核心尘（最密）
    (140, 0.130, 0.270, 0.40, 1.00, 0.85, 1.00, 1),  # 主体星云
    (70,  0.270, 0.420, 0.34, 0.85, 0.45, 0.55, 2),  # 游离星尘
    (30,  0.420, 0.500, 0.30, 0.70, 0.30, 0.35, 3),  # 外场散星
)

SUB_W, SUB_H = 208, 46
CORE_W, CORE_H = 220, 256
CORE_X0, CORE_Y0 = 70, 44
SUB_LOCAL_Y = 2

# 加色沉积核：柔光圆斑（径向衰减），单颗是软圆点而非硬十字/方块。
# 原型 lifeform.js 用 radialGradient 软斑精灵；板子用预生成软核列表做加色 stamp，
# 上千颗软圆点疏密堆叠 → 连续星云感（不再是生硬的"红点/圆"）。
# 半径 3 ≈ 21 个非零像素，单颗成本可控；想更朦胧把 R 调到 4~5（更慢）。
def _make_blob(R):
    blob = []
    for dy in range(-R, R + 1):
        for dx in range(-R, R + 1):
            d = math.sqrt(dx * dx + dy * dy)
            if d <= R:
                w = 1.0 - d / R
                if w > 0.08:
                    blob.append((dx, dy, w))
    return blob
_BLOB = _make_blob(3)
_INC_SCALE = 14.0   # 单颗加色强度（柔斑后需调大才看得见；偏白再调小）


def _ch(c):
    return ((c >> 11) & 31, (c >> 5) & 63, c & 31)


def _lerp(a, b, t):
    ar = (a >> 11) & 31; ag = (a >> 5) & 63; ab = a & 31
    br = (b >> 11) & 31; bg = (b >> 5) & 63; bb = b & 31
    r = int(ar + (br - ar) * t)
    g = int(ag + (bg - ag) * t)
    bl = int(ab + (bb - ab) * t)
    return (r << 11) | (g << 5) | bl


class Lifeform:
    def __init__(self, canvas, scale=1.0):
        self.canvas = canvas
        self.state = "idle"
        self.emotion = "calm"
        self.color = C_CORE_WARM
        self.audio_level = 0.3
        self.tts_progress = 0.5
        self.pulse_energy = 0.0
        self.sub_text = ""
        self.sub_dim = False
        self.paused = False
        self.sleeping = False          # 熄屏睡眠时置 True，后台线程跳过渲染
        self.bright = 1.0              # 亮度遮罩（1=通透；<1 时整屏压暗）
        self._pf = dict(STATE_PROFILE["idle"])
        self._t0 = time.ticks_ms()
        self._last_blit = 0
        self._interval = 220
        self._dirty = True
        self._tint = [C_CORE_WARM, C_WARM, C_PINK]   # 当前三色（随状态色更新）
        self._tint_n = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]

        self.buf = bytearray(CORE_W * CORE_H * 2)
        self._build_bg()
        self._build_particles(scale)
        self._trail = []               # 上一帧投影位置（廉价运动拖尾）

        # ── 验证诊断（v0.8.3 真机 bring-up 用）──
        self._frames = 0
        self._err = None

    # ── 预生成静态层 ─────────────────────────────────────────
    def _build_bg(self):
        W, H = CORE_W, CORE_H
        cx = W / 2; cy = H / 2
        self._bg = bytearray(W * H * 2)
        # 极暗暖底径向渐变（中心 #1A0D08 → 边缘 #000000）+ 暗角
        for y in range(H):
            for x in range(W):
                dx = (x - cx) / (W / 2)
                dy = (y - cy) / (H / 2)
                d = math.sqrt(dx * dx + dy * dy)
                # 0(中心)→1(边缘)
                if d <= 1.0:
                    # 暖底：r 随距离从 26→0，g 从 13→0，b 从 8→0
                    r = max(0, int(26 * (1 - d) ** 1.3))
                    g = max(0, int(13 * (1 - d) ** 1.3))
                    b = max(0, int(8 * (1 - d) ** 1.3))
                else:
                    r = g = b = 0
                # 暗角（d>0.68 渐黑）
                if d > 0.68:
                    vg = max(0.0, (d - 0.68) / 0.32)   # 0→1
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
                rr = math.sqrt(max(0, 1 - yy * yy))
                th = GOLDEN * i
                # Fibonacci 球面 + ±0.16 抖动
                j = 0.16
                ux = math.cos(th) * rr + (random.random() - 0.5) * j
                uy = yy + (random.random() - 0.5) * j
                uz = math.sin(th) * rr + (random.random() - 0.5) * j
                ln = math.sqrt(ux * ux + uy * uy + uz * uz) or 1
                roll = random.random()
                tint = 0 if roll < 0.70 else (1 if roll < 0.88 else 2)
                self.particles.append({
                    "ux": ux / ln, "uy": uy / ln, "uz": uz / ln,
                    "r0": r0 + random.random() * (r1 - r0),
                    "size": s0 + random.random() * (s1 - s0),
                    "flowRate": flow * (0.7 + random.random() * 0.6),
                    "spin": spin * (0.75 + random.random() * 0.5),
                    "layer": layer,
                    "tint": tint,
                    "seed": random.random() * 100,
                    "twRate": 0.35 + random.random() * 1.3,
                    "twPhase": random.random() * TAU,
                })

    # ── 公共 API（对齐 lifeform.js）────────────────────────
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
        # tint0=主色(状态色) tint1=暖橙 tint2=软粉；预存归一化 0..1 通道
        cols = (self.color, C_WARM, C_PINK)
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

    # ⚠️ 亮度只走一条通道：ST77916 背光 PWM（st77916.set_nit）。
    #    这里的软件遮罩【默认关闭】，别打开，除非硬件 PWM 起不来。
    SOFT_DIM = False

    def set_brightness(self, nit):
        """（已退休）软件亮度遮罩。真实亮度请调 st77916.set_nit()。"""
        if not self.SOFT_DIM:
            self.bright = 1.0
            return
        nit = max(1, min(400, nit))
        if nit >= 200:
            self.bright = 1.0
        else:
            self.bright = 1.0 - (200 - nit) / 200 * 0.8

    def pulse(self):
        self.pulse_energy = 1.0
        self._dirty = True

    def force(self):
        self._dirty = True

    def clear_screen(self):
        if self.canvas is None:
            return
        self.canvas.fill(0)

    # ── 加色沉积 ────────────────────────────────────────────
    def _add(self, buf, W, H, x, y, ir, ig, ib):
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

    def _splat(self, buf, W, H, x, y, tint, bright):
        tn = self._tint_n[tint]
        ic = _INC_SCALE * bright
        ir = int(ic * tn[0]); ig = int(ic * tn[1]); ib = int(ic * tn[2])
        if ir <= 0 and ig <= 0 and ib <= 0:
            return
        for (dx, dy, w) in _BLOB:
            self._add(buf, W, H, x + dx, y + dy, int(ir * w), int(ig * w), int(ib * w))

    # ── 主循环：后台线程调用 ───────────────────────────────
    def tick(self, now_ms=None):
        if self.canvas is None or self.paused or self.sleeping:
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
        km = 1 - math.exp(-dt * 2.6)
        for k in ("breath", "spread", "coreGlow", "swirl", "flow", "ripple", "gain", "sag"):
            self._pf[k] += (tgt[k] - self._pf[k]) * km
        self._pf["morph"] = tgt["morph"]
        self.pulse_energy *= math.exp(-dt * 2.0)
        if self.pulse_energy < 0.001:
            self.pulse_energy = 0.0
        t = time.ticks_diff(now, self._t0) / 1000.0
        try:
            self._render(t)
        except Exception as e:
            # 渲染异常不直接崩后台线程：记录首错，打印到串行日志供真机排查
            if self._err is None:
                self._err = e
                print("[LF] render error:", e)
            return
        if self.bright < 1.0:
            self._apply_brightness()
        try:
            self.canvas.blit(self.buf, CORE_X0, CORE_Y0, CORE_W, CORE_H)
        except Exception as e:
            if self._err is None:
                self._err = e
                print("[LF] blit error:", e)
            return
        self._frames += 1
        if self._frames % 20 == 1:
            print("[LF] frame %d state=%s emotion=%s" % (self._frames, self.state, self.emotion))

    def _apply_brightness(self):
        buf = self.buf
        f = self.bright
        # 整屏压暗（cheap：逐像素乘因子）；bright=1 时调用方已跳过
        for i in range(0, len(buf), 2):
            v = (buf[i] << 8) | buf[i + 1]
            r = int(((v >> 11) & 31) * f)
            g = int(((v >> 5) & 63) * f)
            b = int((v & 31) * f)
            nv = (r << 11) | (g << 5) | b
            buf[i] = nv >> 8
            buf[i + 1] = nv & 0xFF

    # ── 合成中央窗口 ───────────────────────────────────────
    def _render(self, t):
        buf = self.buf; W = CORE_W; H = CORE_H; cx = W // 2; cy = H // 2
        buf[:] = self._bg

        pf = self._pf
        breath = (1 + math.sin(t * 0.72) * pf["breath"]
                  + math.sin(t * 1.63 + 1.3) * pf["breath"] * 0.35
                  + self.pulse_energy * 0.26)
        spread = pf["spread"] * breath * (1 + self.pulse_energy * 0.22)
        gain = pf["gain"] * (1 + self.pulse_energy * 0.35)
        audio = self.audio_level
        morph = pf["morph"]

        # 中心雾核（减弱：2 层极淡底辉 + 极小亮核）
        coreN = 2
        for i in range(coreN):
            ph = i * 1.7
            dx = math.sin(t * 0.5 + ph) * W * 0.026
            dy = math.cos(t * 0.44 + ph) * W * 0.026
            rl = W * (0.050 + i * 0.045) * breath * (1 + audio * 0.10)
            flick = 0.78 + 0.14 * math.sin(t * 1.1 + ph) + 0.10 * math.sin(t * 0.8 + ph * 2)
            al = pf["coreGlow"] * gain * (0.11 - i * 0.035) * flick
            if al > 0.004:
                self._splat(buf, W, H, cx + dx, cy + dy + pf["sag"] * 0.5, 0, al * 1.2)
        # 最内亮核
        rl = W * (0.022 + 0.004 * math.sin(t * 1.9)) * breath
        jx = math.sin(t * 0.7) * W * 0.010
        jy = math.cos(t * 0.63) * W * 0.010
        self._splat(buf, W, H, cx + jx, cy + jy + pf["sag"] * 0.5, 0,
                    pf["coreGlow"] * gain * 0.30)

        # 拖尾：上一帧位置淡画
        for (px, py, tint, b) in self._trail:
            self._splat(buf, W, H, px, py, tint, b * 0.42)

        # 粒子场
        swirl = t * pf["swirl"]
        cur = []
        for p in self.particles:
            ang = swirl * p["spin"] + p["seed"]
            cs = math.cos(ang); sn = math.sin(ang)
            x = p["ux"] * cs - p["uz"] * sn
            z = p["ux"] * sn + p["uz"] * cs
            y = p["uy"]
            # 每粒子相位 sin 近似噪声形变（省 FBM 的 6 trig）
            nq = math.sin(t * p["flowRate"] * 0.6 + p["seed"]) * 0.5 + \
                 math.sin(t * p["flowRate"] * 0.27 + p["seed"] * 1.7) * 0.5
            rad = p["r0"] * spread * (1 + nq * 0.26 * pf["flow"])
            extra = 0.0
            if morph == "scatter":
                rad *= 1 + audio * 0.28 + 0.08 * math.sin(t * 3.4 + p["seed"])
            elif morph == "vortex":
                rad *= 0.82 + 0.18 * math.sin(t * 1.1 + p["seed"] * 0.3)
                extra = (1.0 - p["r0"] * 2.2) * t * 0.0   # 旋流已由 swirl 体现
            elif morph == "wave":
                rad *= 1 + 0.13 * math.sin(t * 4.2 + y * 5 + self.tts_progress * TAU)
            elif morph == "droop":
                rad *= 0.92
            elif morph == "burst":
                rad *= 1 + self.pulse_energy * 0.45
            persp = 1.0 / (1.0 - z * 0.36)
            px = cx + x * rad * W * persp
            py = cy + y * rad * W * persp + pf["sag"]
            depth = (z + 1) * 0.5
            tw = 0.55 + 0.45 * math.sin(t * p["twRate"] + p["twPhase"])
            a2 = (0.075 + depth * 0.40) * tw * gain
            if p["layer"] == 3:
                a2 *= 0.40
            elif p["layer"] == 2:
                a2 *= 0.60
            elif p["layer"] == 0:
                a2 *= 0.52
            if a2 <= 0.004:
                continue
            self._splat(buf, W, H, px, py, p["tint"], a2)
            cur.append((px, py, p["tint"], a2))
        self._trail = cur

        # 声波环（聆听）
        if pf["ripple"] > 0.02:
            for i in range(3):
                ph = (t * (0.42 + audio * 0.55) + i / 3.0) % 1.0
                rr = W * (0.11 + ph * 0.36)
                ra = (1 - ph) * (1 - ph) * 0.30 * pf["ripple"] * (0.35 + audio * 0.85)
                self._ring(buf, W, H, cx, cy, rr, self.color, 2, ra)

        self._render_sub(buf, W, H)

    def _ring(self, buf, W, H, cx, cy, r, c, th=2, alpha=1.0):
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
                    self._add(buf, W, H, x, y, ir, ig, ib)

    # ── 合成字幕（顶部，居中；超 3 行截断省略）─────────────
    def _render_sub(self, buf, W, H):
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
