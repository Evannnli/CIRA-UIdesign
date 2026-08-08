# -*- coding: utf-8 -*-
"""
CIRA Device Runtime · LVGL 版入口（lv_micropython, v9 假设）
=========================================================
与 cira_main.py（v0.8.7 MicroPython）并存：刷 lv_micropython 后，
把本文件 cp 为 main.py 即切到 LVGL 渲染；原 cira_main.py 仍可作回退。

差异（相对 cira_main.py）：
  · 显示：cira_lvgl_display.init_lvgl_display() 替代 cira_display.init_display()
  · 星云：cira_lvgl_lifeform.Lifeform 渲染进 LVGL canvas（平滑合成）
  · 控制中心：cira_lvgl_control_center.ControlCenter（LVGL canvas 表面）
  · 主循环：每帧 lv.timer_handler() 驱动 LVGL 刷新/动画
音频 / WS / 触摸 / 唤醒链路复用原模块，不变。

⚠ 沙盒无硬件/无 lvgl，本文件未运行；运行需 lv_micropython 固件 + 阶段0探针通过。
"""
import time
import _thread
import network

try:
    import ujson
except ImportError:
    import json as ujson
try:
    from ubase64 import b64decode
except ImportError:
    from binascii import a2b_base64 as b64decode

import lvgl as lv
import cira_pins
import cira_audio
import cira_expander
import cira_touch
import cira_wake
import cira_ws
import cira_audio_in
import cira_lvgl_display
import cira_lvgl_lifeform
import cira_lvgl_control_center

WIFI_SSID = "叮当的智能家居"
WIFI_PASS = "15295601676yw"

_wdt = None
ws = None
lf = None
_bf = None


def _blog(msg):
    global _bf
    try:
        if _bf is None:
            _bf = open("/boot.log", "a")
        _bf.write(msg + "\n")
        _bf.flush()
    except Exception:
        pass


STATE_IDLE, STATE_LISTENING, STATE_THINKING, STATE_SPEAKING, STATE_SLEEP = \
    "idle", "listening", "thinking", "speaking", "sleep"
SLEEP_TIMEOUT_MS = 30000
_LAST_WAKE_MS = -10000
WAKE_COOLDOWN_MS = 2000
_LAST_ACTIVE_MS = 0
SLEEP_NIT = 40
WAKE_NIT = 255
_SLEEPING = False
_LF_STATE = {
    STATE_IDLE: "idle", STATE_LISTENING: "listen",
    STATE_THINKING: "think", STATE_SPEAKING: "speak",
}
LONG_MS = 1200
RELEASE_MS = 150


def connect_wifi():
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if not w.isconnected():
        print("WiFi 连接", WIFI_SSID, "...")
        w.connect(WIFI_SSID, WIFI_PASS)
        for _ in range(15):
            if w.isconnected():
                break
            time.sleep(1)
    print("WiFi OK:", w.ifconfig()[0] if w.isconnected() else "FAIL")
    return w


def _net_connect():
    global ws
    try:
        connect_wifi()
    except Exception as e:
        print("[NET] WiFi 失败:", e)
        _blog("WIFI fail: %r" % e)
    for _i in range(3):
        try:
            c = cira_ws.CIRABridgeClient()
            c.connect()
            ws = c
            print("[WS] 桥接层已连接")
            _blog("WS ok")
            return
        except Exception as e:
            print("[WS] 连接重试 %d: %r" % (_i, e))
            _blog("WS retry %d: %r" % (_i, e))
            time.sleep(5)
    _blog("WS fail: 桥接层不可达（仅本地唤醒可用）")


def ui_state(s, sub=None):
    global _SLEEPING
    if lf is None:
        return
    if s == STATE_SLEEP:
        _SLEEPING = True
        cira_lvgl_display.set_nit(SLEEP_NIT)
        lf.set_state("idle")
        return
    if _SLEEPING:
        _SLEEPING = False
        cira_lvgl_display.set_nit(WAKE_NIT)
    lf.set_state(_LF_STATE.get(s, "idle"))
    if sub is not None:
        lf.set_subtitle(sub)


def do_conversation():
    global _LAST_ACTIVE_MS
    fname = cira_wake.wake()
    _blog("WAKE %s" % fname)
    ui_state(STATE_LISTENING, "我在听…")
    _LAST_ACTIVE_MS = time.ticks_ms()

    wav = None
    try:
        wav = cira_audio_in.record_wav(seconds=3)
    except Exception as e:
        _blog("REC ERR: %r" % e)
        wav = None
    if not wav:
        ui_state(STATE_IDLE, "没听清，请再试")
        time.sleep(1.0)
        return False

    try:
        from ubinascii import b2a_base64
    except ImportError:
        from binascii import b2a_base64
    b64 = b2a_base64(wav).rstrip(b"\n").decode("ascii")
    wav = None
    try:
        import gc
        gc.collect()
    except Exception:
        pass

    ui_state(STATE_THINKING, "在想…")
    if ws:
        try:
            r = ws.voice_turn(audio_b64=b64, fmt="wav", tts=True)
            heard = (r.get("heard") or "")
            reply = (r.get("reply") or "")
            emo = r.get("emotion")
            _blog("WS ok heard=%s" % heard[:24])
            ui_state(STATE_SPEAKING, reply)
            if lf is not None and emo:
                lf.set_emotion(emo)
            a = r.get("audio")
            if a:
                cira_audio.play_wav(b64decode(a))
                _blog("REPLY emo=%s" % emo)
        except Exception as e:
            _blog("WS-ERR: %r" % e)
            ui_state(STATE_IDLE, "网络有点问题")
            time.sleep(1.0)
    else:
        _blog("WS none")
    ui_state(STATE_IDLE, "")
    return False


def main():
    global _LAST_WAKE_MS, _LAST_ACTIVE_MS, _bf, lf, _wdt
    print("=== CIRA Device Runtime (LVGL) ===")
    try:
        _bf = open("/boot.log", "w")
        _bf.write("BOOT %d\n" % time.ticks_ms())
        _bf.flush()
    except Exception:
        _bf = None

    try:
        import machine
        _wdt = machine.WDT(timeout=30000)
        _blog("WDT on")
    except Exception as e:
        _wdt = None
        _blog("WDT off %r" % e)

    cira_audio.warmup()
    cira_expander.init()

    # ── LVGL 显示 ──
    disp, scr = cira_lvgl_display.init_lvgl_display()
    _blog("lvgl disp ok")

    # ── 星云 canvas ──
    lf = None
    try:
        lf = cira_lvgl_lifeform.Lifeform(scale=0.6)
        lf_canvas = lv.canvas(scr)
        lf_canvas.set_buffer(lf.buf, 360, 360, lv.COLOR_FORMAT_RGB565)
        lf_canvas.set_size(360, 360)
        lf_canvas.set_pos(0, 0)
        lf._commit = lambda: lf_canvas.invalidate()
        lf.set_state("idle")
        cira_lvgl_display.set_nit(WAKE_NIT)
        lf._dirty = True
        lf.tick()
        _blog("LF ok frames=%d" % lf._frames)
        print("[DISP] 光生命体就绪 (LVGL canvas 360x360)")
    except Exception as e:
        import sys
        sys.print_exception(e)
        _blog("LF FAIL: %r" % e)
        lf = None

    # ── 控制中心 ──
    cc = None
    touch = cira_touch.CST816(rst=cira_pins.TOUCH_RST, int_pin=cira_pins.TOUCH_INT)
    print("[TOUCH] chip_id=0x%02X awake=%s" % (touch.chip_id or 0, touch.awake))
    if lf is not None:
        try:
            cc = cira_lvgl_control_center.ControlCenter(scr, touch)
        except Exception as e:
            import sys
            sys.print_exception(e)
            _blog("CC init fail: %r" % e)
            cc = None

    # 后台动画线程：驱动星云渲染（LVGL timer 在主循环 flush）
    if lf is not None:
        def _anim():
            _n = 0
            while True:
                try:
                    if _wdt is not None:
                        _wdt.feed()
                    lf.tick()
                    _n += 1
                    if _n % 50 == 0:
                        _blog("anim frames=%d" % lf._frames)
                except Exception as e:
                    _blog("LF tick err: %r" % e)
                time.sleep_ms(40)
        _thread.start_new_thread(_anim, ())

    _thread.start_new_thread(_net_connect, ())

    _LAST_ACTIVE_MS = time.ticks_ms()
    ui_state(STATE_IDLE, "")
    print(">>> LVGL: 点按=对话；长按1.2s=控制中心；Ctrl+C 退出 <<<")

    pressed = False
    consumed = False
    start = 0
    rel_det = 0
    press_x = None
    state = STATE_IDLE
    cc_open = False

    while True:
        now = time.ticks_ms()
        if _wdt is not None:
            _wdt.feed()
        lv.timer_handler()           # LVGL 刷新/动画（关键）

        # 控制中心开启时：把输入喂给 CC，退出则恢复星云
        if cc_open and cc is not None:
            if cc.feed(now):
                cc.close()
                cc_open = False
                if lf is not None:
                    lf.set_state("idle")
                    lf.set_subtitle("")
                _LAST_ACTIVE_MS = now
                state = STATE_IDLE
            time.sleep_ms(30)
            continue

        finger = touch.touching() or touch.take_edge()
        if finger:
            _LAST_ACTIVE_MS = now
            if not pressed:
                pressed = True
                consumed = False
                start = now
                rel_det = 0
                try:
                    px, _, _ = touch.read_point()
                    press_x = px
                except Exception:
                    press_x = None
        elif pressed and rel_det == 0:
            rel_det = now

        if pressed and not consumed and time.ticks_diff(now, start) >= LONG_MS:
            consumed = True
            _blog("LONG -> control center (LVGL)")
            ui_state(STATE_IDLE, "控制中心")
            if cc is not None:
                cc.open(done_cb=None)
                cc_open = True
            pressed = False
            rel_det = 0
            press_x = None
            _LAST_ACTIVE_MS = now
            state = STATE_IDLE
            continue

        if pressed and rel_det != 0 and time.ticks_diff(now, rel_det) >= RELEASE_MS:
            held = time.ticks_diff(now, start)
            pressed = False
            if not consumed and held < LONG_MS:
                if time.ticks_diff(now, _LAST_WAKE_MS) >= WAKE_COOLDOWN_MS:
                    _LAST_WAKE_MS = now
                    do_conversation()
            consumed = False
            rel_det = 0
            press_x = None
            _LAST_ACTIVE_MS = now
            continue

        if state != STATE_SLEEP and time.ticks_diff(now, _LAST_ACTIVE_MS) > SLEEP_TIMEOUT_MS:
            state = STATE_SLEEP
            ui_state(STATE_SLEEP)
            _blog("SLEEP")

        if state == STATE_SLEEP:
            time.sleep_ms(100)
            continue

        time.sleep_ms(40)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys, machine, time as _t
        sys.print_exception(e)
        try:
            with open("/boot.log", "a") as f:
                f.write("MAIN CRASH: %s %r\n" % (type(e).__name__, e))
        except Exception:
            pass
        _t.sleep(2)
        machine.reset()
