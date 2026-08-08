# main.py — CIRA Device Runtime (MicroPython) 入口
# 阶段目标: 先在真机打通 "WiFi → 桥接层 → 状态机" 链路 (REPL 可见),
#          显示/触摸/音频驱动在端口释放后于真机迭代补齐。
#
# 推送到板子 (Thonny 释放端口后):
#   mpremote connect /dev/cu.usbmodem101 cp main.py :main.py
#   mpremote connect /dev/cu.usbmodem101 cp cira_ws.py :cira_ws.py
#   mpremote connect /dev/cu.usbmodem101 reset
# 或一键运行:
#   mpremote connect /dev/cu.usbmodem101 run main.py

import time
import network

try:
    import ujson  # MicroPython
except ImportError:
    import json as ujson

from cira_ws import CIRABridgeClient

# ── WiFi 配置 (用户填: 板子要连到运行桥接层的主机同一网段) ──
WIFI_SSID = "YOUR_SSID"
WIFI_PASS = "YOUR_PASS"

# 状态机
STATE_IDLE, STATE_LISTENING, STATE_THINKING, STATE_SPEAKING, STATE_SLEEP = "idle", "listening", "thinking", "speaking", "sleep"
SLEEP_TIMEOUT_MS = 10000  # v0.6: 无交互 10s 熄屏


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
    if w.isconnected():
        print("WiFi OK:", w.ifconfig()[0])
    else:
        raise RuntimeError("WiFi 连接失败")
    return w


def main():
    connect_wifi()
    client = CIRABridgeClient()  # 默认连 192.168.31.33:8788 (本机 mock / 模型侧)
    client.connect()
    print("[DR] 桥接层已连接, 进入 IDLE")

    state = STATE_IDLE
    last_interact = time.ticks_ms()

    # 阶段1: 验证链路 (REPL 打印). 显示驱动就绪后替换为星云渲染+音频.
    while True:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_interact) > SLEEP_TIMEOUT_MS and state != STATE_SLEEP:
            state = STATE_SLEEP
            print("[DR] → SLEEP (熄屏)")

        if state == STATE_SLEEP:
            time.sleep(1)
            continue

        # 模拟一次"孩子说了一句" → 走 voice_turn (ASR由桥接层mock)
        # 真机阶段: 由触摸唤醒 / 语音唤醒词触发, 且先播本地"我在。/哎！"
        try:
            r = client.voice_turn(transcript="你好，西拉")
        except Exception as e:
            print("[DR] 桥接层异常:", e)
            time.sleep(3)
            continue

        state = STATE_THINKING
        print("[THINKING] 收到应答 emotion=", r.get("emotion"))
        state = STATE_SPEAKING
        print("[SPEAKING] reply=", r.get("reply"),
              "| audio_b64_len=", len(r.get("audio") or ""),
              "| durationMs=", r.get("durationMs"))
        # 真机阶段: 此处解码 audio(base64)→I2S 播放 + 星云随 emotion 变化
        last_interact = time.ticks_ms()
        state = STATE_IDLE
        time.sleep(3)  # 模拟一轮间隔


if __name__ == "__main__":
    main()
