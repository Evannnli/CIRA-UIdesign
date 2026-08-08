# cira_main.py — CIRA Device Runtime (MicroPython) 入口
# v0.8.5：真机交互补全（对应 Evan 的三点反馈）
#   1) 显示：冷启动先用纯 Python 安全版预热 PSRAM，再切回 viper 原生 blit（~50~160ms/帧），
#      星云顺滑呼吸、冷启动不再冻死；machine.WDT 兜底任何残留硬 fault。
#   2) 真对话：点按 → 本地唤醒应答 → 录孩子语音 → 发桥接层 voice_turn(audio) →
#      播模型应答（ASR→Core→TTS 全在模型侧）。不再发写死的 transcript。
#   3) 控制中心：长按 1.2s → 圆形屏控制中心（音量/亮度/模式），lf.paused 防 SPI 争用。
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
import cira_audio_in   # 录音（ES7210）

WIFI_SSID = "叮当的智能家居"
WIFI_PASS = "15295601676yw"

_wdt = None   # 看门狗（machine.WDT）：兜底任何残留硬 fault 自动复位，防变砖
ws = None     # 桥接层 WS 客户端（模块级全局）：后台线程连上后置入；do_conversation 读它
lf = None     # 光生命体实例（模块级全局）：ui_state / do_conversation / 动画线程都读它

_bf = None   # 预开的 boot.log 句柄（冷启动内存紧时也能写）


def _blog(msg):
    """冷启动诊断日志落盘（/boot.log），不依赖串口是否连着。"""
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
SLEEP_TIMEOUT_MS = 30000   # 无交互 30s 进入微暗睡眠（creature 继续呼吸，点按即唤醒）

# 单次唤醒冷却（防抖动点触把"哎！"和"我在。"都播出来，也防重复发模型）
_LAST_WAKE_MS = -10000
WAKE_COOLDOWN_MS = 2000

# 最近一次有交互的时间（睡眠倒计时基准；do_conversation 也会刷新）
_LAST_ACTIVE_MS = 0

# 背光：睡眠微暗呼吸（不全黑），唤醒恢复全亮
SLEEP_NIT = 40
WAKE_NIT = 255
_SLEEPING = False

# 状态 → 光生命体态（lifeform STATE_PROFILE 用 listen/think/speak/idle/wake）
_LF_STATE = {
    STATE_IDLE: "idle", STATE_LISTENING: "listen",
    STATE_THINKING: "think", STATE_SPEAKING: "speak",
}

# 长按阈值（进控制中心）
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
    """后台线程：连 WiFi + 桥接层 WS，连上后写入模块全局 ws。
    放后台是为了主交互循环（触摸 / 本地唤醒）立刻可用，不被网络阻塞——
    Evan 反馈「开机半天没反应、点按没后续」正是被 15s×2 的网络超时卡住。"""
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
    """把状态机态映射到光生命体 + 字幕 + 睡眠（微暗呼吸，不全黑）。
    模块级：do_conversation 与主循环都会调用（之前误写成 main 的嵌套函数，
    导致 do_conversation 一调 ui_state 就 NameError → 对话直接崩）。"""
    global _SLEEPING
    if lf is None:
        return
    if s == STATE_SLEEP:
        _SLEEPING = True
        cira_display.set_nit(SLEEP_NIT)
        lf.set_state("idle")
        return
    if _SLEEPING:               # 从微暗睡眠被唤醒：背光恢复全亮
        _SLEEPING = False
        cira_display.set_nit(WAKE_NIT)
    lf.set_state(_LF_STATE.get(s, "idle"))
    if sub is not None:
        lf.set_subtitle(sub)


def do_conversation():
    """一轮完整对话：本地唤醒应答 → 录孩子语音 → 发桥接层 → 播模型应答。

    返回 True = 中途被再次唤醒打断（暂未实现打断重开，预留）。
    """
    global _LAST_ACTIVE_MS
    # 唤醒（最高优先级打断）：本地随机播"我在。/哎！"，不进模型
    fname = cira_wake.wake()
    _blog("WAKE %s" % fname)
    ui_state(STATE_LISTENING, "我在听…")
    _LAST_ACTIVE_MS = time.ticks_ms()

    # 录音（ES7210，3s）
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
    _blog("REC bytes=%d" % len(wav))

    # base64（释放 wav 后再组 JSON，省内存）。ubase64 不可用则 ubinascii。
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

    # 思考中（屏幕即时反馈，避免孩子以为坏了）
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
            else:
                _blog("REPLY no-audio")
        except Exception as e:
            _blog("WS-ERR: %r" % e)
            ui_state(STATE_IDLE, "网络有点问题")
            time.sleep(1.0)
    else:
        _blog("WS none")
    ui_state(STATE_IDLE, "")
    return False


def main():
    global _LAST_WAKE_MS, _LAST_ACTIVE_MS, _bf, lf
    print("=== CIRA Device Runtime v0.8.5 ===")
    try:
        _bf = open("/boot.log", "w")
        _bf.write("BOOT %d\n" % time.ticks_ms())
        _bf.flush()
    except Exception:
        _bf = None
    _blog("warmup+expander")
    # 看门狗：viper 切回后若仍偶发硬 fault（或任何死循环），WDT 超时复位，
    # 不会永久冻死。动画线程每帧喂狗，正常交互绝不误触。
    # 超时取 30s：覆盖「WDT 上电 → 动画线程首次喂狗」之间的冷启动宽窗
    #（Lifeform 构建 + 显示初始化若偶发偏慢，也不会误触复位）。
    global _wdt
    try:
        import machine
        _wdt = machine.WDT(timeout=30000)
        _blog("WDT on")
    except Exception as e:
        _wdt = None
        _blog("WDT off %r" % e)
    cira_audio.warmup()                 # 功放常开，唯一一次 pop
    cira_expander.init()                # 释放 TCA9554: 触摸/LCD 复位

    # ── 显示 + 光生命体 ──────────────────────────────────
    lf = None
    disp = None
    try:
        _blog("init_display...")
        disp = cira_display.init_display()
        _blog("disp ok repr=%s" % repr(disp)[:40])
        canvas = cira_face.make_canvas("round", disp, cira_pins.LCD_W, cira_pins.LCD_H)
        _blog("canvas ok")
        try:
            lf = cira_lifeform.Lifeform(canvas, scale=0.6)   # 0.6≈216 粒子，冷启动稳
            _blog("lf built")
        except Exception as e:
            import sys
            _blog("LF BUILD FAIL: %s %r" % (type(e).__name__, e))
            sys.print_exception(e)
            lf = None
        if lf is not None:
            lf.clear_screen()
            _blog("lf clear")
            lf.set_state("idle")
            cira_display.set_nit(WAKE_NIT)   # 初始全亮
            _blog("nit set")
            lf._dirty = True
            lf.tick()
            _blog("LF ok frames=%d" % lf._frames)
            print("[DISP] 光生命体就绪 (canvas %dx%d)" % (canvas.W, canvas.H))
    except Exception as e:
        import sys
        print("[DISP] 初始化失败，进入无屏模式:", e)
        sys.print_exception(e)
        _blog("DISP FAIL: %r" % e)
        lf = None

    # 后台动画线程：独立于主循环驱动光生命体呼吸（录音/思考时不卡死）
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

    touch = cira_touch.CST816(rst=cira_pins.TOUCH_RST, int_pin=cira_pins.TOUCH_INT)
    print("[TOUCH] chip_id=0x%02X awake=%s" % (touch.chip_id or 0, touch.awake))

    # 网络（WiFi + 桥接层 WS）放后台线程：主交互循环立即启动，
    # 即使桥接层暂未就绪，本地唤醒 / 触摸也不被阻塞。
    _thread.start_new_thread(_net_connect, ())

    # ui_state 已提升为模块级函数（do_conversation 也要调用，见下方定义）
    _LAST_ACTIVE_MS = time.ticks_ms()
    ui_state(STATE_IDLE, "")
    print(">>> 点按=对话；长按1.2s=控制中心；Ctrl+C 退出 <<<")

    # ── 主循环：长短按状态机（待机/对话/控制中心/睡眠）──
    pressed = False
    consumed = False
    start = 0
    rel_det = 0
    press_x = None
    state = STATE_IDLE

    while True:
        now = time.ticks_ms()
        if _wdt is not None:
            _wdt.feed()

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

        # 长按 → 控制中心（不等松手，当场触发）
        if pressed and not consumed and time.ticks_diff(now, start) >= LONG_MS:
            consumed = True
            _blog("LONG -> control center")
            ui_state(STATE_IDLE, "控制中心")
            if lf is not None:
                lf.paused = True
            try:
                import cira_control_center
                cira_control_center.run(canvas, touch, disp)
            except Exception as e:
                import sys
                sys.print_exception(e)
                _blog("CC ERR: %r" % e)
            if lf is not None:
                lf.paused = False
                lf.clear_screen()
                lf.set_state("idle")
                lf.set_subtitle("")
            pressed = False
            rel_det = 0
            press_x = None
            _LAST_ACTIVE_MS = now
            state = STATE_IDLE
            continue

        # 短按结算（消抖：持续松手满 RELEASE_MS）
        if pressed and rel_det != 0 and time.ticks_diff(now, rel_det) >= RELEASE_MS:
            held = time.ticks_diff(now, start)
            pressed = False
            if not consumed and held < LONG_MS:
                if time.ticks_diff(now, _LAST_WAKE_MS) >= WAKE_COOLDOWN_MS:
                    _LAST_WAKE_MS = now
                    do_conversation()
                # else: 冷却中忽略这次点触
            consumed = False
            rel_det = 0
            press_x = None
            _LAST_ACTIVE_MS = now
            continue

        # 睡眠超时
        if state != STATE_SLEEP and time.ticks_diff(now, _LAST_ACTIVE_MS) > SLEEP_TIMEOUT_MS:
            state = STATE_SLEEP
            ui_state(STATE_SLEEP)
            _blog("SLEEP")

        if state == STATE_SLEEP:
            time.sleep_ms(100)
            continue

        time.sleep_ms(60)


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
