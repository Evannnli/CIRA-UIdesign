# -*- coding: utf-8 -*-
"""
CIRA · 路线 A 开机画面（LVGL 固件）
=================================
刷 lv_micropython 后，把本文件 cp 为板子的 :main.py 即开机自启：
    mpremote connect /dev/cu.usbmodem101 fs cp cira_splash.py :main.py
    mpremote connect /dev/cu.usbmodem101 reset
显示持久 "CIRA" 启动画面 + 旋转环，证明设备已就绪、不再黑屏。

仅依赖已在板上验证过的模块：cira_lvgl_display（→ lvgl / cira_pins /
cira_expander / st77916），不碰音频/WS/触摸，故极低概率崩板。

后续把真实 CIRA UI 迁到 cira_main_lvgl.py 验通、且其依赖全推上板后，
可把 :main.py 换成 cira_main_lvgl.py（本 splash 作回退）。
"""
import time


def _c(hexv):
    """把 0xRRGGBB 转 lv.color；lv.color_hex 不存在时退回 color_make。"""
    import lvgl as lv
    try:
        return lv.color_hex(hexv)
    except Exception:
        try:
            r = (hexv >> 16) & 0xFF
            g = (hexv >> 8) & 0xFF
            b = hexv & 0xFF
            return lv.color_make(r, g, b)
        except Exception:
            return None


def build():
    """搭好启动画面，返回 (disp, scr, ring)。不进循环，供探针测试。"""
    import lvgl as lv
    from cira_lvgl_display import init_lvgl_display

    disp, scr = init_lvgl_display()

    title = lv.label(scr)
    title.set_text("CIRA")
    c = _c(0xFFFFFF)
    if c is not None:
        title.set_style_text_color(c, 0)
    title.center()

    sub = lv.label(scr)
    sub.set_text("路线 A · LVGL 已就绪")
    c2 = _c(0x88CCFF)
    if c2 is not None:
        sub.set_style_text_color(c2, 0)
    try:
        sub.align(lv.ALIGN.CENTER, 0, 38)
    except Exception:
        pass

    ring = lv.arc(scr)
    try:
        ring.set_size(64, 64)
        ring.align(lv.ALIGN.CENTER, 0, 86)
        ring.set_range(0, 360)
        ring.set_angles(0, 270)
        try:
            ring.set_bg_angles(0, 360)
        except Exception:
            pass
        ring.remove_flag(lv.obj.FLAG.CLICKABLE)
    except Exception:
        pass

    return disp, scr, ring


def main():
    disp, scr, ring = build()
    ang = 0
    while True:
        ang = (ang + 8) % 360
        try:
            ring.set_rotation(ang)
        except Exception:
            pass
        lv.tick_inc(16)
        lv.timer_handler()
        time.sleep_ms(16)


# 开机自启：直接跑 main()，不要依赖 __name__ 判断。
# 部分 MicroPython 构建在开机跑 main.py 时 __name__ 并非 "__main__"，
# 会导致 splash 不启动、屏一直黑。这里无条件启动渲染循环。
try:
    main()
except Exception as e:
    import sys
    # 只打印，不 machine.reset()：避免崩板时黑屏无限重启循环（保持 REPL 可连）
    sys.print_exception(e)
    raise
