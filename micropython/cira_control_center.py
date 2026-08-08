# cira_control_center.py — 长按进入的控制中心（圆形屏 360×360）
# 交互对齐 HTML 原型（index.html · settings-panel）：
#   · 进 = 主屏长按 1.2s（由 cira_main 触发，run() 开场先等手指松开，杜绝进/出长按串台）
#   · 退 = 「完成」按钮（短按），与原型一致，永不和进入手势冲突
#   · 结构 = HOME 菜单（Wi-Fi/蓝牙/音量/亮度/模式）→ 点行进子视图 → ‹ 返回 → HOME → 完成
# 渲染：native disp.fill_rect / fill（快，不走 lifeform 缓冲）；中文用 subtitle_font 点阵；
#       调用方负责 lf.paused=True/False（cira_main 已做）。
import time

try:
    import subtitle_font
except Exception:
    subtitle_font = None

import cira_pins
import cira_audio
import cira_display

# ── 配色（暖色系，对齐原型 --c-warm / --c-text）────────────
C_BG      = 0x0000   # 控制中心底色（覆盖星云的暗层）
C_TITLE   = 0xFF17   # 暖白（标题 / 大数值）
C_DIM     = 0x9C0E   # 暗暖白（未选中标签 / 值）
C_SEL     = 0xFD40   # 暖橙（选中高亮 / 滑块填充）
C_SEL_DIM = 0x6B20   # 暖橙暗底（选中行高亮背景）
C_BAR_BG  = 0x4A49   # 暗灰槽
C_BAR     = 0xFD40   # 暖橙填充（= C_SEL）
C_CHEV    = 0x7BEF   # Chevron › 暗色

MODES = ["正常", "轻声", "故事"]

# 持久记忆（重启前保留）
_state = {
    "volume_db": cira_pins.VOLUME_DB,   # -95.5 ~ 0
    "nit": 255,                         # 背光亮度
    "mode": 0,                          # 0 正常 1 轻声 2 故事
}

LONG_MS = 1200
RELEASE_MS = 150

# HOME 菜单行（对齐原型 settings 五项 + 完成按钮）
# sub: 进入的子视图标识；icon: 行首小图标色；val: 实时取值函数
ROWS = [
    {"sub": "wifi", "label": "Wi-Fi", "icon": 0x9CF3, "val": lambda: _wifi_status()},
    {"sub": "bt",   "label": "蓝牙",  "icon": 0x9CF3, "val": lambda: "关闭"},
    {"sub": "vol",  "label": "音量",  "icon": 0xFD40, "val": lambda: "%d%%" % _vol_pct()},
    {"sub": "bri",  "label": "亮度",  "icon": 0xFD40, "val": lambda: "%d" % _state["nit"]},
    {"sub": "mode", "label": "模式",  "icon": 0xFD40, "val": lambda: MODES[_state["mode"]]},
]
DONE_SUB = "done"

# 布局
TITLE_Y   = 34
ROW_TOP   = 60
ROW_H     = 46
DONE_Y    = 306
DONE_H    = 30
CX        = 180


# ── 实时取值 ────────────────────────────────────────────────
def _vol_pct():
    return max(0, min(100, int((_state["volume_db"] + 95.5) / 95.5 * 100)))


def _wifi_status():
    try:
        import network
        w = network.WLAN(network.STA_IF)
        if w.isconnected():
            s = w.config("ssid") or "Wi-Fi"
            return s if len(s) <= 10 else s[:9] + "…"
        return "未连接"
    except Exception:
        return "—"


# ── 字体 / 图元 ────────────────────────────────────────────
def _cell():
    return subtitle_font.CELL if subtitle_font is not None else 12


def _draw_glyph(disp, ch, x, y, color):
    if subtitle_font is None:
        return
    idx = subtitle_font.CHARSET.find(ch)
    if idx < 0:
        return
    C = subtitle_font.CELL
    g = subtitle_font.GLYPHS[idx * subtitle_font.BYTES_PER_GLYPH:
                             (idx + 1) * subtitle_font.BYTES_PER_GLYPH]
    for yy in range(C):
        for xx in range(C):
            bit = yy * C + xx
            if (g[bit >> 3] >> (7 - (bit & 7))) & 1:
                disp.fill_rect(x + xx, y + yy, 1, 1, color)


def _draw_text(disp, x, y, text, color):
    cx = x
    C = _cell()
    for ch in text:
        _draw_glyph(disp, ch, cx, y, color)
        cx += C


def _draw_text_c(disp, y, text, color):
    """居中文本（按 12px 字宽估宽）。"""
    C = _cell()
    w = len(text) * C
    _draw_text(disp, CX - w // 2, y, text, color)


def _draw_glyph2x(disp, ch, x, y, color):
    """2x 放大字形（大数值）。"""
    if subtitle_font is None:
        return
    idx = subtitle_font.CHARSET.find(ch)
    if idx < 0:
        return
    C = subtitle_font.CELL
    g = subtitle_font.GLYPHS[idx * subtitle_font.BYTES_PER_GLYPH:
                             (idx + 1) * subtitle_font.BYTES_PER_GLYPH]
    for yy in range(C):
        for xx in range(C):
            bit = yy * C + xx
            if (g[bit >> 3] >> (7 - (bit & 7))) & 1:
                disp.fill_rect(x + xx * 2, y + yy * 2, 2, 2, color)


def _draw_text2x_c(disp, y, text, color):
    C = _cell()
    w = len(text) * C * 2
    cx = CX - w // 2
    for ch in text:
        _draw_glyph2x(disp, ch, cx, y, color)
        cx += C * 2


def _disc(disp, ccx, ccy, r, color):
    """实心圆（行首图标 / 滑块拇指）。"""
    for dy in range(-r, r + 1):
        yy = ccy + dy
        if abs(yy - 180) > 178:
            continue
        half = int((r * r - dy * dy) ** 0.5)
        disp.fill_rect(ccx - half, yy, half * 2 + 1, 1, color)


def _bar(disp, x, y, w, h, frac):
    disp.fill_rect(x, y, w, h, C_BAR_BG)
    fw = int(w * max(0.0, min(1.0, frac)))
    if fw > 0:
        disp.fill_rect(x, y, fw, h, C_BAR)
    _disc(disp, x + fw, y + h // 2, h // 2 + 1, C_TITLE)


def _clear_rect(disp, x, y, w, h):
    """用底色覆盖一块矩形（局部擦除，避免整屏 fill）。"""
    disp.fill_rect(x, y, w, h, C_BG)


def _redraw_sub_dynamic(disp, view):
    """子视图拖动时只刷新动态部分（大数值 + 滑块），避免整屏重绘卡顿。

    路线 B v0.8.8：原来每次调节都整屏 `_redraw`（先 fill 全屏 + 重画所有文字），
    拖动时整屏闪。现只擦除并重画「大数值区」与「滑块区」——标题(‹ 返回+子标题)
    与底部提示都在擦除区域之外，得以保留，拖动从「整屏闪」变成「局部刷」。
    """
    # 大数值区（覆盖最宽 4 字 ×2 倍 ≈ 96px，留余量到 220 宽）
    _clear_rect(disp, CX - 110, 128, 220, 64)
    _draw_text2x_c(disp, 150, _sub_big(view), C_TITLE)
    # 滑块区（含拇指圆余量；非滑块子视图此块本就是底色，清了也无残留）
    _clear_rect(disp, 48, 202, 268, 28)
    if view in ("vol", "bri", "mode"):
        _bar(disp, 50, 210, 260, 10, _frac(view))


# ── 数值 / 调节 ────────────────────────────────────────────
def _frac(sub):
    if sub == "vol":
        return _vol_pct() / 100.0
    if sub == "bri":
        return _state["nit"] / 255.0
    if sub == "mode":
        return (_state["mode"] + 1) / len(MODES)
    return 0.0


def _adjust(sub, d):
    if sub == "vol":
        _state["volume_db"] = max(-95.5, min(0.0, _state["volume_db"] + d * 5.0))
        try:
            cira_audio.get_codec().set_volume(_state["volume_db"])
        except Exception:
            pass
    elif sub == "bri":
        _state["nit"] = max(40, min(255, _state["nit"] + d * 20))
        cira_display.set_nit(_state["nit"])
    elif sub == "mode":
        _state["mode"] = (_state["mode"] + d) % len(MODES)


# ── 绘制 ──────────────────────────────────────────────────
def _redraw(disp, view, sel):
    disp.fill(C_BG)
    if view == "home":
        _draw_text_c(disp, TITLE_Y - 6, "设置", C_TITLE)
        for i, row in enumerate(ROWS):
            y0 = ROW_TOP + i * ROW_H
            cy = y0 + ROW_H // 2
            if i == sel:
                disp.fill_rect(36, y0 + 4, 288, ROW_H - 8, C_SEL_DIM)
            icon_c = C_SEL if i == sel else row["icon"]
            _disc(disp, 54, cy, 9, icon_c)
            lab_c = C_SEL if i == sel else C_TITLE
            _draw_text(disp, 74, cy - 6, row["label"], lab_c)
            val = row["val"]()
            vc = C_SEL if i == sel else C_DIM
            C = _cell()
            _draw_text(disp, 300 - len(val) * C, cy - 6, val, vc)
            _draw_glyph(disp, "›", 308, cy - 6, C_CHEV)
        # 完成按钮（原型 primary pill）
        db_c = C_SEL if sel == len(ROWS) else C_DIM
        disp.fill_rect(110, DONE_Y, 140, DONE_H, C_SEL if sel == len(ROWS) else C_BAR_BG)
        _draw_text_c(disp, DONE_Y + 9, "完成", C_BG if sel == len(ROWS) else C_DIM)
    else:
        # 子视图
        _draw_glyph(disp, "‹", 26, TITLE_Y - 6, C_TITLE)   # 返回
        _draw_text_c(disp, TITLE_Y - 6, _sub_title(view), C_TITLE)
        if view in ("vol", "bri", "mode"):
            _draw_text2x_c(disp, 150, _sub_big(view), C_TITLE)
            _bar(disp, 50, 210, 260, 10, _frac(view))
            _draw_text_c(disp, 250, "左 / 右 调节 · 中点 返回", C_DIM)
        else:
            _draw_text2x_c(disp, 150, _sub_big(view), C_TITLE)
            _draw_text_c(disp, 250, "暂仅显示状态 · 中点 返回", C_DIM)


def _sub_title(sub):
    for r in ROWS:
        if r["sub"] == sub:
            return r["label"]
    return "设置"


def _sub_big(sub):
    if sub == "vol":
        return "%d%%" % _vol_pct()
    if sub == "bri":
        return "%d" % _state["nit"]
    if sub == "mode":
        return MODES[_state["mode"]]
    if sub == "wifi":
        return _wifi_status()
    if sub == "bt":
        return "关闭"
    return ""


# ── 输入状态机 ────────────────────────────────────────────
def _wait_release(touch, timeout_ms=2500):
    """等手指完全松开（消除进入长按的残余按压），再清边沿。"""
    t0 = time.ticks_ms()
    while touch.touching():
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            break
        time.sleep_ms(30)
    touch.clear_edge()


def _get_event(touch):
    """返回 ('tap', x, y) / ('long',) / None（轮询无事件）。"""
    pressed = False
    start = 0
    px = py = None
    rel_det = 0
    while True:
        now = time.ticks_ms()
        finger = touch.touching() or touch.take_edge()
        if finger and not pressed:
            pressed = True
            start = now
            rel_det = 0
            try:
                px, py, _ = touch.read_point()
            except Exception:
                px = py = None
        elif pressed and not finger and rel_det == 0:
            rel_det = now
        if pressed and time.ticks_diff(now, start) >= LONG_MS:
            _wait_release(touch)
            return ("long",)
        if pressed and rel_det != 0 and time.ticks_diff(now, rel_det) >= RELEASE_MS:
            held = time.ticks_diff(now, start)
            pressed = False
            rel_det = 0
            if held < LONG_MS and px is not None:
                return ("tap", px, py)
        time.sleep_ms(40)


def _row_at(y):
    for i in range(len(ROWS)):
        if ROW_TOP + i * ROW_H <= y < ROW_TOP + (i + 1) * ROW_H:
            return i
    return None


def _in_done(y):
    return DONE_Y <= y <= DONE_Y + DONE_H


def run(canvas, touch, disp):
    """控制中心主循环。长按进（由 cira_main 触发）、完成按钮退。设置实时应用。"""
    sel = 0
    view = "home"
    cira_display.set_nit(_state["nit"])
    _redraw(disp, view, sel)
    _wait_release(touch)   # 关键：吃掉进入时的长按残余，避免一进场就被判"退出"

    while True:
        ev = _get_event(touch)
        if ev is None:
            continue
        if ev[0] == "long":
            if view == "home":
                return          # 完成（长按退出，等价原型"完成"按钮）
            view = "home"
            sel = 0
            _redraw(disp, view, sel)
            _wait_release(touch)
            continue
        _, x, y = ev
        if view == "home":
            if _in_done(y):
                return
            r = _row_at(y)
            if r is not None:
                view = ROWS[r]["sub"]
                sel = r
                _redraw(disp, view, sel)
                _wait_release(touch)
                continue
            # 空白处：用 x 区移动选择（左=上，右=下）
            if x < 120:
                sel = (sel - 1) % (len(ROWS) + 1)
            elif x > 240:
                sel = (sel + 1) % (len(ROWS) + 1)
            _redraw(disp, view, sel)
        else:
            if x < 120:
                _adjust(view, -1)
                _redraw_sub_dynamic(disp, view)
            elif x > 240:
                _adjust(view, +1)
                _redraw_sub_dynamic(disp, view)
            else:
                view = "home"
                _redraw(disp, view, sel)
                _wait_release(touch)
