# cira_main.py — CIRA Device Runtime (MicroPython) 入口
# v0.8.2 唤醒链路真机验证通过。
# 交互: 点按屏幕 → 本地随机播"我在。/哎！"(硬件本地, 不进模型, 可打断当前播放)
#        → 发 voice_turn 给桥接层 → 播模型应答音频(ES8311 I2S)。
# 不覆盖 Xiaozhi main.py; 运行:  mpremote connect /dev/cu.usbmodem101 run cira_main.py
import time
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

WIFI_SSID = "叮当的智能家居"
WIFI_PASS = "15295601676yw"

STATE_IDLE, STATE_LISTENING, STATE_THINKING, STATE_SPEAKING, STATE_SLEEP = \
    "idle", "listening", "thinking", "speaking", "sleep"
SLEEP_TIMEOUT_MS = 10000   # 无交互 10s 熄屏（耳朵仍醒着，点按即唤醒）


def connect_wifi():
    w = network.WLAN(network.STA_IF)
    w.active(True)
    if not w.isconnected():
        print("WiFi 连接", WIFI_SSID, "...")
        w.connect(WIFI_SSID, WIFI_PASS)
        for _ in range(30):
            if w.isconnected():
                break
            time.sleep(1)
    print("WiFi OK:", w.ifconfig()[0] if w.isconnected() else "FAIL")
    return w


def main():
    print("=== CIRA Device Runtime v0.8.2 ===")
    cira_audio.warmup()                 # 功放常开，唯一一次 pop
    cira_expander.init()                # 释放 TCA9554: 触摸/LCD 复位
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

    state = STATE_IDLE
    last = time.ticks_ms()
    was = False
    print(">>> 点按屏幕唤醒；Ctrl+C 退出 <<<")

    while True:
        now = time.ticks_ms()
        pressed = touch.take_edge() or touch.is_touched()

        if pressed and not was:
            was = True
            # 唤醒（最高优先级打断）: 本地随机播"我在。/哎！"，不进模型
            fname = cira_wake.wake()
            print("[WAKE] 本地应答:", fname)
            state = STATE_LISTENING
            last = now
            if ws:
                try:
                    r = ws.voice_turn(transcript="你好，西拉")
                    a = r.get("audio")
                    if a:
                        cira_audio.play_wav(b64decode(a))
                        print("[REPLY] emotion=%s 播放完毕" % r.get("emotion"))
                    state = STATE_IDLE
                except Exception as e:
                    print("[ERR]", e)
                    state = STATE_IDLE

        if not touch.is_touched():
            was = False

        # 熄屏超时
        if state != STATE_SLEEP and time.ticks_diff(now, last) > SLEEP_TIMEOUT_MS:
            state = STATE_SLEEP
            print("[SLEEP] 熄屏（点按唤醒）")

        if state == STATE_SLEEP:
            time.sleep_ms(100)
            continue

        time.sleep_ms(60)


if __name__ == "__main__":
    main()
