# verify_display.py — v0.8.3 显示 bring-up 真机验证（非侵入，不改 boot main）
# 自动演示光生命体态切换 + 熄屏/亮屏，打印帧数与异常，约 26s 后退出便于抓日志。
import time
import _thread

import cira_pins
import cira_expander
import cira_display
import cira_face
import cira_lifeform

print("=== verify_display v0.8.3 ===")
disp = cira_display.init_display()
canvas = cira_face.make_canvas("round", disp, cira_pins.LCD_W, cira_pins.LCD_H)
lf = cira_lifeform.Lifeform(canvas, scale=0.7)
lf.clear_screen()
lf.set_state("idle")
print("[DISP] canvas %dx%d particles=%d" % (canvas.W, canvas.H, len(lf.particles)))

t0 = time.ticks_ms()


def _anim():
    while time.ticks_diff(time.ticks_ms(), t0) < 28000:
        try:
            lf.tick()
        except Exception as e:
            print("[anim err]", e)
        time.sleep_ms(40)


_thread.start_new_thread(_anim, ())

time.sleep_ms(3000)
print("[DEMO] wake"); lf.set_state("wake"); lf.pulse()
time.sleep_ms(1500)
print("[DEMO] listen"); lf.set_state("listen"); lf.set_subtitle("我在听…")
time.sleep_ms(2000)
print("[DEMO] think"); lf.set_state("think")
time.sleep_ms(2000)
print("[DEMO] speak/happy"); lf.set_state("speak"); lf.set_emotion("happy"); lf.set_subtitle("今天天气真好呀！")
time.sleep_ms(3000)
print("[DEMO] speak/comfort"); lf.set_emotion("comfort"); lf.set_subtitle("没关系的，抱抱～")
time.sleep_ms(3000)
print("[DEMO] idle"); lf.set_state("idle"); lf.set_subtitle("")
time.sleep_ms(2000)
print("[DEMO] sleep (screen off)"); lf.sleeping = True; cira_display.screen_off()
time.sleep_ms(2000)
print("[DEMO] wake from sleep (screen on)"); lf.sleeping = False; cira_display.screen_on(); lf.set_state("wake")
time.sleep_ms(2000)
print("=== verify_display OK frames=%d err=%s ===" % (lf._frames, lf._err))
