# -*- coding: utf-8 -*-
"""
CIRA · LVGL 点亮探针（迁移阶段 0）
================================
目的：在本机刷好 lv_micropython（含 cira_st77916 模块）后跑这个脚本，确认两件事：
  1) LVGL 能 import 并跑起 timer（证明运行时 OK）；
  2) 360×360 圆屏能被 LVGL 点亮（通过 cira_lvgl_display.init_lvgl_display()
     接入真实 ST77916 flush）。

运行：mpremote connect /dev/cu.usbmodem101 run tools/lvgl_hello.py

注意：本探针直接复用 cira_lvgl_display.init_lvgl_display()（与最终运行时同一条路径），
比手写 flush 更稳。lv_micropython 跟踪 LVGL v9 API；若你刷的固件是 LVGL v8，
需同步改 cira_lvgl_display.py 的 display 创建段（见该文件底部注释）。
"""
import time

try:
    import lvgl as lv
except Exception as e:
    print("[LVGL] import 失败（固件未含 LVGL？）:", e)
    raise

try:
    from cira_lvgl_display import init_lvgl_display
except Exception as e:
    print("[LVGL] 无法导入 cira_lvgl_display（cira_st77916/cira_expander/cira_pins 是否都已推上板？）:", e)
    raise

lv.init()
print("[LVGL] init ok, version:", lv.version_major(), lv.version_minor(), lv.version_patch())

disp, scr = init_lvgl_display()
print("[LVGL] display 创建完成（若上面打印 ST77916 已接入真实 flush 即成功）")

# ── 最简 UI：背景 + 居中标签 ──
bg = lv.obj(scr)
bg.set_size(360, 360)
bg.center()

label = lv.label(scr)
label.set_text("CIRA · LVGL")
label.align(lv.ALIGN.CENTER, 0, 0)

print("[LVGL] UI 建好，跑 timer 循环 8s ...")
t0 = time.ticks_ms()
while True:
    lv.timer_handler()
    time.sleep_ms(10)
    if time.ticks_diff(time.ticks_ms(), t0) > 8000:
        break
print("[LVGL] spike 结束：若圆屏显示 'CIRA · LVGL' 则成功；若黑屏但无报错则 flush 路径未真点亮（排查 cira_st77916）。")
