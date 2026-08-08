# cira_control_center.py — 长按进入的控制中心（圆形屏）
# 交互：左 1/3 屏点按 = 减小选中项；右 1/3 = 增大；中 1/3 = 切换选中项；
#       长按 1.2s = 退出并保留设置。
# 渲染：直接用 native disp.fill_rect / fill（快），中文用 subtitle_font 点阵；
#       不用 lifeform 缓冲，避免整屏慢 blit。调用方负责 lf.paused=True/False。
import time

try:
    import subtitle_font
except Exception:
    subtitle_font = None

import cira_pins
import cira_audio
import cira_display

_MODES = ["正常", "轻声", "故事"]

# 持久记忆（重启前保留）
_state = {
    "volume_db": cira_pins.VOLUME_DB,   # -95.5 ~ 0
    "nit": 255,                         # 背光亮度
    "mode": 0,                          # 0 正常 1 轻声 2 故事
}

C_TITLE = 0xFF17   # 暖白
C_SEL = 0xFD40     # 暖橙（选中高亮）
C_DIM = 0x9C0E     # 暗暖白（未选中）
C_BAR_BG = 0x4A49  # 暗灰槽
C_BAR = 0xFD40     # 暖橙填充


def _vol_pct():
    return max(0, min(100, int((_state["volume_db"] + 95.5) / 95.5 * 100)))


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
    for ch in text:
        _draw_glyph(disp, ch, cx, y, color)
        cx += subtitle_font.CELL if subtitle_font is not None else 12


def _frac(i):
    if i == 0:
        return _vol_pct() / 100.0
    if i == 1:
        return _state["nit"] / 255.0
    return (_state["mode"] + 1) / len(_MODES)


def _val_text(i):
    if i == 0:
        return "%d%%" % _vol_pct()
    if i == 1:
        return "%d" % _state["nit"]
    return _MODES[_state["mode"]]


def _redraw(disp, sel):
    disp.fill(0)
    _draw_text(disp, 120, 22, "控制中心", C_TITLE)
    items = ["音量", "亮度", "模式"]
    y = 86
    for i in range(3):
        col = C_SEL if i == sel else C_DIM
        _draw_text(disp, 56, y, items[i], col)
        _draw_text(disp, 196, y, _val_text(i), col)
        disp.fill_rect(56, y + 20, 248, 10, C_BAR_BG)
        fw = int(248 * _frac(i))
        if fw > 0:
            disp.fill_rect(56, y + 20, fw, 10, C_BAR)
        y += 74
    _draw_text(disp, 40, 322, "左/右调 · 中点切 · 长按退出", C_DIM)


def _adjust(i, d):
    if i == 0:
        _state["volume_db"] = max(-95.5, min(0.0, _state["volume_db"] + d * 5.0))
        try:
            cira_audio.get_codec().set_volume(_state["volume_db"])
        except Exception:
            pass
    elif i == 1:
        _state["nit"] = max(40, min(255, _state["nit"] + d * 25))
        cira_display.set_nit(_state["nit"])
    else:
        _state["mode"] = (_state["mode"] + d) % len(_MODES)


def run(canvas, touch, disp):
    """控制中心主循环。长按退出后返回。设置已实时应用。"""
    sel = 0
    cira_display.set_nit(_state["nit"])
    _redraw(disp, sel)

    pressed = False
    start = 0
    rel_det = 0
    press_x = None
    LONG_MS = 1200
    RELEASE_MS = 150

    while True:
        now = time.ticks_ms()
        finger = touch.touching() or touch.take_edge()
        if finger and not pressed:
            pressed = True
            start = now
            rel_det = 0
            try:
                px, _, _ = touch.read_point()
                press_x = px
            except Exception:
                press_x = None
        elif pressed and not finger and rel_det == 0:
            rel_det = now

        # 长按 → 退出
        if pressed and time.ticks_diff(now, start) >= LONG_MS:
            return True

        # 短按结算（消抖）
        if pressed and rel_det != 0 and time.ticks_diff(now, rel_det) >= RELEASE_MS:
            held = time.ticks_diff(now, start)
            pressed = False
            rel_det = 0
            if held < LONG_MS:
                if press_x is not None and press_x < 120:
                    _adjust(sel, -1)
                elif press_x is not None and press_x > 240:
                    _adjust(sel, +1)
                else:
                    sel = (sel + 1) % 3
                _redraw(disp, sel)
            press_x = None
        time.sleep_ms(40)
