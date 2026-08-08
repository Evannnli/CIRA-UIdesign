# verify_wake.py — 唤醒链路真机验证 (v0.8.2)
# 目的: 点按屏幕 → 本地随机播"我在。/哎！" → 发 voice_turn 给桥接层 → 播模型应答音频。
# 验证硬件: ES8311 出声(MCLK+I2S+PA) + CST816 触摸中断 + 与模型侧音频链路。
# 推送到板子后运行:  mpremote connect /dev/cu.usbmodem101 run verify_wake.py
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

# WiFi 凭证（与 main.py 一致；正式运行时由 net_config.json 覆盖）
WIFI_SSID = "叮当的智能家居"
WIFI_PASS = "15295601676yw"


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
    print("=== CIRA 唤醒链路验证 v0.8.2 ===")
    cira_audio.warmup()              # 功放常开，唯一一次 pop
    print("[AUDIO] warmup 完成 (功放已上电)")

    cira_expander.init()              # 释放 TCA9554: CST816 RST(EXIO1)/LCD RST(EXIO2)
    touch = cira_touch.CST816(rst=cira_pins.TOUCH_RST, int_pin=cira_pins.TOUCH_INT)
    print("[TOUCH] chip_id=0x%02X awake=%s" % (touch.chip_id or 0, touch.awake))

    ws = None
    try:
        connect_wifi()
        ws = cira_ws.CIRABridgeClient()
        ws.connect()
        print("[WS] 桥接层已连接 (192.168.31.33:8788)")
    except Exception as e:
        print("[WS] 未连 (仅测本地唤醒):", e)

    print(">>> 点按屏幕唤醒；5 秒后自动演示一次；25 秒后自动退出 <<<")
    was = False
    n = 0
    auto_demo = False
    t0 = time.ticks_ms()
    while True:
        now = time.ticks_ms()
        # 无手点时，5 秒后自动演示一次（用于无交互验证出声）
        if (not auto_demo) and time.ticks_diff(now, t0) > 5000:
            auto_demo = True
            pressed = True
            print("[AUTO DEMO] 自动触发唤醒")
        else:
            pressed = touch.take_edge() or touch.is_touched()

        if pressed and not was:
            was = True
            n += 1
            fname = cira_wake.wake()
            print("[WAKE %d] 播放本地应答: %s" % (n, fname))
            if ws:
                try:
                    r = ws.voice_turn(transcript="你好，西拉")
                    a = r.get("audio")
                    if a:
                        pcm = b64decode(a)
                        cira_audio.play_wav(pcm)
                        print("[REPLY %d] emotion=%s 音频播放完毕 (len=%d)"
                              % (n, r.get("emotion"), len(pcm)))
                except Exception as e:
                    print("[ERR]", e)
        if not touch.is_touched():
            was = False
        time.sleep_ms(60)
        if time.ticks_diff(now, t0) > 25000:
            print("=== 验证结束，退出 ===")
            break


if __name__ == "__main__":
    main()
