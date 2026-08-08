# -*- coding: utf-8 -*-
"""
CIRA · LVGL 显示驱动（lv_micropython, v9 API 假设）
================================================
ST77916 圆屏(360×360) ↔ LVGL flush_cb。本模块是 LVGL 迁移的「地基」：
  · lv.init() + 释放 TCA9554（LCD 复位走 EXIO2）
  · 优先用 frozen `st77916` 真实 flush（方案 A）；
    否则降级 dummy flush（仅验证 LVGL 在跑，方案 B 待补纯 Python SPI flush）。
  · 暴露 set_nit / screen_on / screen_off，供上层调背光。

⚠ 本文件与 tools/lvgl_hello.py 探针同款 API（display_create / draw_buf_create /
   set_flush_cb）。探针先过，本模块才可信。若你的 lv_micropython 是 LVGL v8
（disp_drv_register 风格），需把本模块 display 段按 v8 改写（见底部注释）。

⚠ 沙盒无 ESP-IDF/烧录链，本文件未在真机运行；只经 API 静态核对。
"""
import time
import lvgl as lv
import cira_expander
import cira_pins as P

W, H = P.LCD_W, P.LCD_H  # 360, 360

_disp = None
_st = None


def _flush_dummy(disp, area, color_p):
    """无 ST77916 时的兜底：仅证明 flush 路径被调用，不真点亮屏。"""
    lv.display_flush_ready(disp)


def _make_st77916_flush(st):
    """方案 A：flush_cb 把 LVGL 渲染缓冲(RGB565)整块 blit 到 ST77916。"""
    def _flush(disp, area, color_p):
        x0, y0 = area.x1, area.y1
        x1, y1 = area.x2, area.y2
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        size = w * h * 2
        try:
            buf = bytes(color_p, size)          # color_p 是内存地址(int)
            st.blit(buf, x0, y0, w, h)
        except Exception as ex:
            print("[LVGL] st77916.blit 异常:", ex)
        lv.display_flush_ready(disp)
    return _flush


def init_lvgl_display():
    """初始化 LVGL + ST77916，返回 (disp, screen_act)。失败降级 dummy。"""
    global _disp, _st
    lv.init()
    print("[LVGL] init ok, version:", lv.version_major(), lv.version_minor(), lv.version_patch())

    # 1) 释放 TCA9554：含 LCD 复位 EXIO2（与 cira_display.init_display 同逻辑）
    cira_expander.init()

    flush = _flush_dummy
    try:
        import st77916
        _st = st77916.ST77916(
            P.LCD_W, P.LCD_H,
            cs=P.LCD_CS, pclk=P.LCD_PCLK,
            d0=P.LCD_D0, d1=P.LCD_D1, d2=P.LCD_D2, d3=P.LCD_D3,
            rst=P.LCD_RST, bl=P.LCD_BL,
            madctl=P.LCD_MADCTL, invert=P.LCD_INVERT,
        )
        try:
            _st.on()
        except Exception:
            pass
        try:
            _st.fill(0)
        except Exception:
            pass
        flush = _make_st77916_flush(_st)
        print("[LVGL] ST77916 已接入真实 flush（方案 A）")
    except Exception as e:
        _st = None
        print("[LVGL] 无 ST77916 frozen 模块 → dummy flush（仅验证 LVGL 运行，需走方案 B）:", e)

    # 2) 注册显示（LVGL v9 API）
    draw_buf = lv.draw_buf_create(W, max(1, H // 4), lv.COLOR_FORMAT_RGB565, 0)
    disp = lv.display_create(W, H)
    disp.set_flush_cb(flush)
    disp.set_draw_buf(draw_buf)
    try:
        disp.set_color_format(lv.COLOR_FORMAT_RGB565)
    except Exception:
        pass
    _disp = disp

    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_black(), 0)
    return disp, scr


def set_nit(nit):
    """背光亮度（nit）。走 ST77916 PWM 真调光，别走软件遮罩。"""
    global _st
    if _st is not None:
        try:
            _st.set_nit(nit)
        except Exception:
            pass


def screen_on():
    global _st
    if _st is not None:
        try:
            _st.on()
        except Exception:
            pass


def screen_off():
    global _st
    if _st is not None:
        try:
            _st.off()
        except Exception:
            pass


"""
── 若你的 lv_micropython 是 LVGL v8（disp_drv_register 风格），把 init_lvgl_display
   里 display 段换成：──
    disp_drv = lv.disp_drv_t()
    disp_drv.init()
    disp_drv.hor_res = W
    disp_drv.ver_res = H
    disp_drv.flush_cb = flush
    disp_drv.register()
    # 圆屏黑底：scr = lv.obj(); scr.set_style_bg_color(lv.color_black(), 0)
"""
