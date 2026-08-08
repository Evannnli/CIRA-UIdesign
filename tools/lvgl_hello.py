# -*- coding: utf-8 -*-
"""
CIRA · LVGL 点亮探针（迁移阶段 0）
================================
目的：在本机刷好 lv_micropython 后跑这个脚本，确认两件事：
  1) LVGL 能在板子上 import 并跑起 timer（证明运行时 OK）；
  2) 360×360 圆屏能被 LVGL 点亮（先试 ST77916 真实 flush，失败则 dummy 仅验证 LVGL 在跑）。

注意：lv_micropython 跟踪 LVGL v9 API。若你刷的固件是 LVGL v8（disp_drv_register 风格），
下面 display 创建那段需要改成 v8 写法（见文件底部注释）。本探针未在本沙盒运行，需按本机版本微调。

运行：mpremote connect /dev/cu.usbmodem101 run tools/lvgl_hello.py
"""
import time

try:
    import lvgl as lv
except Exception as e:
    print("[LVGL] import 失败（固件未含 LVGL？）:", e)
    raise

lv.init()
print("[LVGL] init ok, version:", lv.version_major(), lv.version_minor(), lv.version_patch())

W, H = 360, 360

# ── flush_cb：LVGL 把一块矩形区域的 RGB565 推到面板 ──
def _flush_dummy(disp, area, color_p):
    # 无 ST77916 时的兜底：仅证明 flush 路径被调用，不真点亮屏
    lv.display_flush_ready(disp)

_flush = _flush_dummy
_st77916 = None
try:
    import st77916
    _st7799 = st77916
    print("[LVGL] st77916 可用 → 使用真实 flush")

    def _flush_st(disp, area, color_p):
        x0, y0 = area.x1, area.y1
        x1, y1 = area.x2, area.y2
        w = x1 - x0 + 1
        h = y1 - y0 + 1
        size = w * h * 2
        try:
            buf = bytes(color_p, size)          # 复制 LVGL 渲染缓冲（RGB565）
            st77916.blit(buf, x0, y0, w, h)
        except Exception as ex:
            print("[LVGL] st77916.blit 异常:", ex)
        lv.display_flush_ready(disp)

    _flush = _flush_st
except Exception as e:
    print("[LVGL] 无 st77916 frozen 模块 → dummy flush（仅验证 LVGL 运行）:", e)

# ── 注册显示（LVGL v9 API）──
draw_buf = lv.draw_buf_create(W, max(1, H // 4), lv.COLOR_FORMAT_RGB565, 0)
disp = lv.display_create(W, H)
disp.set_flush_cb(_flush)
disp.set_draw_buf(draw_buf)
try:
    disp.set_color_format(lv.COLOR_FORMAT_RGB565)
except Exception:
    pass

# ── 最简 UI：背景 + 居中标签 ──
scr = lv.screen_active()
bg = lv.obj(scr)
bg.set_size(W, H)
bg.center()

label = lv.label(scr)
label.set_text("CIRA · LVGL")
label.align(lv.ALIGN.CENTER, 0, 0)

print("[LVGL] UI 建好，跑 timer 循环 8s ...")
t0 = time.ticks_ms()
flushed = 0
while True:
    lv.timer_handler()
    time.sleep_ms(10)
    if time.ticks_diff(time.ticks_ms(), t0) > 8000:
        break
print("[LVGL] spike 结束：若圆屏显示 'CIRA · LVGL' 则成功；若黑屏但无报错则 flush 路径未真点亮（需改 ST77916 flush）。")

"""
── 若你的 lv_micropython 是 LVGL v8（disp_drv_register 风格），把上面 display 段换成：──
import lvgl as lv
lv.init()
disp_drv = lv.disp_drv_t()
disp_drv.init()
disp_drv.hor_res = W
disp_drv.ver_res = H
disp_drv.flush_cb = _flush
disp_drv.register()
"""
