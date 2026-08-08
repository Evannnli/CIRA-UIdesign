# cira_main.py — CIRA Device Runtime (MicroPython) 入口
# v0.8.3 显示 bring-up：ST77916 圆形 TFT + 光生命体星云（frozen st77916 驱动）。
# 交互: 点按屏幕 → 本地随机播"我在。/哎！"(硬件本地, 不进模型, 可打断当前播放)
#        → 发 voice_turn 给桥接层 → 播模型应答音频(ES8311 I2S) + 光生命体变表情。
# 可作为板子主固件：先备份原厂 main.py（fs cp :main.py :main_xiaozhi.py），
# 再把本文件 cp 为 main.py（fs cp :cira_main.py :main.py），reset 即生效；回退反之。
# 调试时也可临时运行: mpremote connect /dev/cu.usbmodem101 run cira_main.py
import time
import _thread
import network

try:
    import ujson  # MicroPython
except ImportError:
    import json as ujson
try:
    from ubase64 import b64decode
except ImportError:
    from binascii import a2b_base64 as b64decode

import cira_pins
import cira_audio
import cira_expander
import cira_touch
import cira_wake
import cira_ws
import cira_display
import cira_face
import cira_lifeform

WIFI_SSID = "叮当的智能家居"
WIFI_PASS = "15295601676yw"

STATE_IDLE, STATE_LISTENING, STATE_THINKING, STATE_SPEAKING, STATE_SLEEP = \
    "idle", "listening", "thinking", "speaking", "sleep"
SLEEP_TIMEOUT_MS = 10000   # 无交互 10s 熄屏（耳朵仍醒着，点按即唤醒）

# 单次唤醒冷却（防抖动点触把"哎！"和"我在。"都播出来，也防重复发模型）
_LAST_WAKE_MS = -10000
WAKE_COOLDOWN_MS = 2000

# 状态 → 光生命体态（lifeform STATE_PROFILE 用 listen/think/speak/idle/wake）
_LF_STATE = {
    STATE_IDLE: "idle", STATE_LISTENING: "listen",
    STATE_THINKING: "think", STATE_SPEAKING: "speak",
}


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


def main():
    print("=== CIRA Device Runtime v0.8.3 ===")
    cira_audio.warmup()                 # 功放常开，唯一一次 pop
    cira_expander.init()                # 释放 TCA9554: 触摸/LCD 复位

    # ── 显示 + 光生命体 ──────────────────────────────────
    lf = None
    try:
        disp = cira_display.init_display()
        canvas = cira_face.make_canvas("round", disp, cira_pins.LCD_W, cira_pins.LCD_H)
        lf = cira_lifeform.Lifeform(canvas, scale=0.7)   # 0.7≈250 粒子，板子慢就调小
        lf.clear_screen()
        lf.set_state("idle")
        print("[DISP] 光生命体就绪 (canvas %dx%d)" % (canvas.W, canvas.H))
    except Exception as e:
        import sys
        print("[DISP] 初始化失败，进入无屏模式:", e)
        sys.print_exception(e)
        lf = None

    # 后台动画线程：独立于主循环驱动光生命体呼吸（录音/思考时不卡死）
    if lf is not None:
        def _anim():
            while True:
                try:
                    lf.tick()
                except Exception:
                    pass
                time.sleep_ms(40)
        _thread.start_new_thread(_anim, ())

    touch = cira_touch.CST816(rst=cira_pins.TOUCH_RST, int_pin=cira_pins.TOUCH_INT)
    print("[TOUCH] chip_id=0x%02X awake=%s" % (touch.chip_id or 0, touch.awake))

    ws = None
    try:
        connect_wifi()
        ws = cira_ws.CIRABridgeClient()
        ws.connect()
        print("[WS] 桥接层已连接")
    except Exception as e:
        print("[WS] 未连 (仅本地唤醒可用):", e)

    def ui_state(s, sub=None):
        """把状态机态映射到光生命体 + 字幕 + 熄屏。"""
        if lf is None:
            return
        if s == STATE_SLEEP:
            lf.sleeping = True
            cira_display.screen_off()
            return
        if lf.sleeping:           # 从睡眠被唤醒：先亮屏
            lf.sleeping = False
            cira_display.screen_on()
        lf.set_state(_LF_STATE.get(s, "idle"))
        if sub is not None:
            lf.set_subtitle(sub)

    state = STATE_IDLE
    ui_state(STATE_IDLE, "")
    last = time.ticks_ms()
    was = False
    print(">>> 点按屏幕唤醒；Ctrl+C 退出 <<<")

    while True:
        now = time.ticks_ms()
        pressed = touch.take_edge() or touch.is_touched()

        if pressed and not was:
            was = True
            # 唤醒（最高优先级打断）: 本地随机播"我在。/哎！"，不进模型
            # 整个唤醒动作（应答+发模型）加 2s 冷却，防抖动点触重复触发
            if time.ticks_diff(now, _LAST_WAKE_MS) >= WAKE_COOLDOWN_MS:
                _LAST_WAKE_MS = now
                fname = cira_wake.wake()
                print("[WAKE] 本地应答:", fname)
                ui_state(STATE_LISTENING, "我在听…")
                last = now
                if ws:
                    try:
                        r = ws.voice_turn(transcript="你好，西拉")
                        a = r.get("audio")
                        emo = r.get("emotion")
                        ui_state(STATE_SPEAKING, r.get("reply") or "")
                        if lf is not None and emo:
                            lf.set_emotion(emo)
                        if a:
                            cira_audio.play_wav(b64decode(a))
                            print("[REPLY] emotion=%s 播放完毕" % emo)
                        ui_state(STATE_IDLE, "")
                        state = STATE_IDLE
                    except Exception as e:
                        print("[ERR]", e)
                        ui_state(STATE_IDLE, "")
                        state = STATE_IDLE
            else:
                # 冷却中：忽略这次抖动点触（避免"哎"+"我在"都播）
                pass

        if not touch.is_touched():
            was = False

        # 熄屏超时
        if state != STATE_SLEEP and time.ticks_diff(now, last) > SLEEP_TIMEOUT_MS:
            state = STATE_SLEEP
            ui_state(STATE_SLEEP)
            print("[SLEEP] 熄屏（点按唤醒）")

        if state == STATE_SLEEP:
            time.sleep_ms(100)
            continue

        time.sleep_ms(60)


if __name__ == "__main__":
    main()
