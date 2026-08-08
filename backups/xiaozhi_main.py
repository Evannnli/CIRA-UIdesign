# -*- coding: utf-8 -*-
"""
CIRA Paideia Prototype · ESP32-S3 主程序（MicroPython）
====================================================
四态状态机（对齐 PRD §7 设备状态系统）：
    IDLE 待机（在场脸，点按屏幕唤醒对话 / 长按进入设置）
    LISTENING 聆听（录音中，表情=好奇"我在听"）
    THINKING 思考（等待 LLM 生成，表情=思考）
    SPEAKING 讲话（播放 vivi2.0，表情=回应情绪）
    + SETTINGS 设置浮层（非主态：触摸滑杆调音量，长按退出）

唤醒方式（决策1）：点按屏幕。音量（决策2）：设置页内触摸滑杆直接调 ES8311。
语音走轮询架构（voice_job.one_turn），规避 ESP32 长连接被掐断的问题。

烧录：把本目录 .py 传进板子（含 st77916/tca9554/cst816/es8311/es7210/wifi_provision 等），
运行 main.py 即可。开机长按 BOOT(=GPIO0) 5 秒可强制重配网。
"""

import time
import machine
import network
from machine import Pin
import config
import emotions
import audio_in
import audio_out
import wifi_provision
import lifeform
import _thread
from face import make_canvas


# ── 光生命体渲染实例（全局；后台线程驱动 tick 动画）────────
# DISPLAY_TYPE=none（纯测试模式无屏）时用 _NullLF 占位，调用方无需判空。
class _NullLF:
    paused = False
    sleeping = False

    def set_state(self, *a, **k): pass
    def set_emotion(self, *a, **k): pass
    def set_audio_level(self, *a, **k): pass
    def set_tts_progress(self, *a, **k): pass
    def set_subtitle(self, *a, **k): pass
    def set_brightness(self, *a, **k): pass
    def pulse(self, *a, **k): pass
    def force(self, *a, **k): pass
    def clear_screen(self, *a, **k): pass
    def tick(self, *a, **k): pass


lf = None   # 在 main() 中实例化

# 语音唤醒可用性开关：录音硬件出问题时运行期置 False，退化为只认点按。
# 用单元素列表是为了能在函数里就地改，不用到处写 global。
_wake_voice_ok = [True]

# 连续失败计数。⚠️ 一次异常就关掉语音唤醒是错的：路由器抖一下、服务端慢一拍，
# 孩子就得重启玩具才能再喊它。所以要连续失败到这个次数才认定"录音硬件真坏了"，
# 中间任何一次成功都清零。
_wake_fail = [0]
WAKE_FAIL_LIMIT = 5

# ── 麦克风 / 唤醒监听的线程协调 ─────────────────────────────
# 旧设计让主线程自己跑 1.5s 唤醒录音，把触摸采样饿死 → 长按/点按/语音唤醒
# 全都时灵时不灵。现在唤醒监听搬到后台线程（_wake_listener），主线程只管触摸。
#   _busy[0]        = 主线程正在对话（占着麦克风录音），监听器必须让出
#   _wake_pending[0]= 监听器听到唤醒词，主线程下一轮认领并开对话
#   _mic            = 麦克风互斥锁：同一时刻只能一方录音，避免 I2S 双重初始化
_busy = [False]
_wake_pending = [False]
try:
    _mic = _thread.allocate_lock()
except Exception:
    _mic = None

# 状态常量
S_IDLE, S_LISTEN, S_THINK, S_SPEAK, S_SETTINGS = "idle", "listen", "think", "speak", "settings"


# ── 背光 / 休眠 ───────────────────────────────────────────
# 省电大头是背光，不是 CPU。所以「休眠」= 关背光 + 停渲染，
# 但麦克风保持醒着，孩子喊一声就能叫起来。
_disp = None
_screen_lit = True


def screen_off():
    global _screen_lit
    if _disp is not None and _screen_lit:
        try:
            _disp.off()
        except Exception:
            pass
    _screen_lit = False


def screen_on():
    global _screen_lit
    if _disp is not None and not _screen_lit:
        try:
            _disp.on()
        except Exception:
            pass
    _screen_lit = True


def build_canvas():
    global _disp
    if config.DISPLAY_TYPE == "none":
        print("（DISPLAY_TYPE=none，跳过屏幕，仅测 WiFi/音频）")
        return None
    if config.DISPLAY_TYPE == "round":
        import st77916
        disp = st77916.ST77916(
            config.LCD_W, config.LCD_H,
            cs=config.LCD_CS, pclk=config.LCD_PCLK,
            d0=config.LCD_D0, d1=config.LCD_D1, d2=config.LCD_D2, d3=config.LCD_D3,
            rst=config.LCD_RST, bl=config.LCD_BL,
            madctl=getattr(config, "LCD_MADCTL", 0x00),
            invert=getattr(config, "LCD_INVERT", False),
        )
        _disp = disp                     # 留给 screen_on/off 控背光
        return make_canvas("round", disp, config.LCD_W, config.LCD_H)
    else:
        from machine import I2C
        import ssd1306
        i2c = I2C(0, scl=Pin(config.OLED_SCL), sda=Pin(config.OLED_SDA))
        disp = ssd1306.SSD1306_I2C(config.OLED_W, config.OLED_H, i2c)
        return make_canvas("oled", disp, config.OLED_W, config.OLED_H)


def init_touch():
    """初始化 CST816 触摸；失败返回 None（退化为按键唤醒）。"""
    try:
        import cst816
        t = cst816.CST816(config.TOUCH_SCL, config.TOUCH_SDA,
                          config.TOUCH_RST, config.TOUCH_INT)
        cid = "0x%02X" % t.chip_id if t.chip_id is not None else "?"
        if t.awake:
            print("  ✓ 触摸驱动 CST816 就绪（ChipID=%s，已关自动休眠 → 长按可靠）" % cid)
        else:
            print("  ⚠ 触摸 CST816 就绪但【自动休眠没关掉】(ChipID=%s)，"
                  "长按可能失灵" % cid)
        return t
    except Exception as e:
        print("  （触摸初始化失败，退化为按键唤醒）：", e)
        return None


def wake_listen_enabled():
    """语音唤醒是否可用（配置开 + 没被运行期异常关掉）。"""
    return _wake_voice_ok[0] and getattr(config, "WAKE_VOICE", True)


def _touch_abort(touch):
    """给唤醒监听用的「有人伸手了就别听了」钩子。

    只读 INT 中断标志（纯内存，不走 I2C、不打扰录音时序），而且**不清标志** ——
    监听返回后外层还要靠 take_edge() 认这次点按。没有 INT 的退化场景才退回轮询。
    """
    if touch is None:
        return None
    if getattr(touch, "int", None) is not None:
        return touch.pending_edge
    return touch.touching


def _on_speech_cue(lvl):
    """后台监听器用：本地判定"有人说话"（还没送 ASR）→ 先点亮聆听态给即时反馈。

    整条唤醒要 ≈4.5 秒（录音 + ASR）才出声，这期间屏幕若毫无反应孩子会以为坏了。
    纯视觉层、零开销（不 force，交给后台渲染线程下一帧带出）。
    熄屏休眠时不点亮：黑着才省电，也免得一有响动就自己亮。
    """
    if not getattr(lf, "sleeping", False):
        lf.set_state("listen")


def _wake_listener():
    """后台线程：常驻监听"你好 CIRA"，听到就把 _wake_pending 置位。

    与主线程（触摸 / 对话）并行，互不阻塞 —— 这才是"麦克风常开"该有的样子。
    麦克风用 _mic 锁协调：主线程要录音时把 _busy 置 True，本线程的录音会在
    一个 chunk 内（~128ms）中止让出，绝不和它抢 I2S。
    """
    import wake
    while True:
        if not _wake_voice_ok[0] or _busy[0]:
            time.sleep_ms(150)
            continue
        # 抢麦克风锁（非阻塞）：主线程正用就先让，避免双重初始化 I2S
        if _mic is not None and not _mic.acquire(0):
            time.sleep_ms(30)
            continue
        try:
            hit, text, lvl = wake.listen_for_wake(
                abort_cb=(None if _mic is None else (lambda: _busy[0])),
                on_speech=_on_speech_cue,
            )
        except Exception as e:
            _wake_fail[0] += 1
            print("  （唤醒监听第 %d 次失败：%s）" % (_wake_fail[0], e))
            if _wake_fail[0] >= WAKE_FAIL_LIMIT:
                print("  连续 %d 次失败，判定录音链路不可用 → 本次开机改为只认点按。"
                      % WAKE_FAIL_LIMIT)
                _wake_voice_ok[0] = False
            if _mic is not None:
                _mic.release()
            time.sleep_ms(150)
            continue
        if _mic is not None:
            _mic.release()
        _wake_fail[0] = 0          # 听通一轮就清零，偶发抖动不该累积成"坏了"
        if hit:
            print("[唤醒] 后台命中：%r → 通知主线程" % text)
            _wake_pending[0] = True
        time.sleep_ms(40)         # 两小段之间留口气，让主线程能抢到锁


def do_turn(canvas, touch):
    """一次完整对话：聆听 → 听完了 → 思考 → 讲话 → 回到待机。

    返回 True 表示【中途被再次唤醒打断】，外层要立刻重开一轮。

    两种打断途径：
      · **语音**：录音阶段麦克风本来就开着，所以录完先看这段话里有没有唤醒词
        ——"就算正在听我说话，喊一声 CIRA 也要重新开始"。这一步复用同一段
        录音的识别结果，不额外录、不额外花钱。
      · **点按**：播放阶段录放共用 I2S1，物理上没法边说边听，用点按打断。
    """
    aborted = [False]

    def _abort():
        # 一旦 latch 就不再去消费触摸边沿，避免把边沿吃掉导致外层收不到
        if aborted[0]:
            return True
        if touch is not None and touch.take_edge():
            aborted[0] = True
            return True
        return False

    print("\n[状态] 我在听…（录音约 %.0f 秒）" % config.RECORD_SECONDS)
    lf.set_state("listen")
    lf.set_subtitle("我在听…")
    # 占住麦克风锁，和后台唤醒监听器互斥（它会在 ~128ms 内让出）
    if _mic is not None:
        _mic.acquire()
    try:
        wav = audio_in.record_wav()
    finally:
        if _mic is not None:
            _mic.release()
    if not wav:
        print("[状态] 没录到声音，回到待机")
        lf.set_subtitle("没听清，请再试一次")
        lf.pulse()
        time.sleep(1.2)
        return False
    print("[状态] 听完了，送去识别…")
    lf.pulse()
    time.sleep(0.4)

    import base64
    import voice_job
    b64 = base64.b64encode(wav).decode("ascii")

    def on_state(st, txt=None):
        if st == "thinking":
            print("[状态] 思考中…")
            lf.set_state("think")
            lf.set_subtitle("思考中…")
        elif st == "speaking":
            print("[回复] %s" % txt)
            lf.set_state("speak")
            lf.set_subtitle(txt)

    # 录音那 4 秒里攒下的触摸边沿要丢掉，否则一进播放就被误判成"打断"
    if touch is not None:
        touch.clear_edge()

    def _on_heard(text):
        """ASR 刚出文本、LLM 还没启动 —— 在这里认唤醒词最划算。"""
        import wake
        return wake.is_wake_word(text)

    heard, n, emotion = voice_job.one_turn(b64, on_state=on_state,
                                           should_abort=_abort, on_heard=_on_heard)
    if aborted[0]:
        print("[状态] 被再次唤醒打断，准备重新聆听")
        return True
    if n == -1:
        # 刚才那句话本身就是在叫 CIRA → 重新应答并重新收音
        print("[状态] 说的是唤醒词，重新应答")
        return True
    if n == 0:
        print("[状态] 没听清（识别为空或无回复），再试一次")
        lf.set_subtitle("没听清，请再试一次")
        lf.pulse()
        time.sleep(1.0)
        return False
    print("[识别] %s" % heard)
    print("[状态] 已播放 %d 句，回到待机" % n)
    time.sleep(0.3)
    return False


def do_wake_ack(how="tap"):
    """被唤醒的第一反应：先出声应答，再听。【优先级高于一切】。

    wake.play_ack() 内部第一件事就是掐断正在播的回答，所以孩子在
    CIRA 讲到一半时再叫它，它会立刻闭嘴 → "哎！" → 重新开始听。
    这一段【完全不碰大模型】，是纯本地/缓存音频，所以快。
    """
    import wake
    lf.sleeping = False
    lf.set_state("wake")
    lf.set_subtitle("")
    lf.force()
    time.sleep_ms(200)      # 让后台线程先画一帧，避免亮屏瞬间闪出休眠前的残影
    screen_on()
    ok = wake.play_ack()
    if ok:
        lf.set_subtitle(wake.ack_text())
    print("[唤醒] 方式=%s 应答=%s" % (how, wake.ack_text() if ok else "（无音频）"))


def conversation(canvas, touch, how="tap"):
    """唤醒应答 → 一轮对话；被打断就再应答一次、重新听。

    整个对话期间把 _busy 置 True，让后台唤醒监听器让出麦克风，
    否则两边会抢 I2S（录放共用一个 I2S1）。
    """
    _busy[0] = True
    _wake_pending[0] = False
    try:
        while True:
            do_wake_ack(how)
            how = "voice"          # 后续几轮都是"又叫了我一声"
            if not do_turn(canvas, touch):
                break
    finally:
        _busy[0] = False
        _wake_pending[0] = False


def open_control_center(canvas, touch):
    """长按进入控制中心（真硬件：Wi-Fi/蓝牙/音量/亮度/模式）。

    进去前必须 lf.paused=True：光生命体的后台动画线程一直在 blit 整窗，
    不停它会和控制中心抢 SPI，画面会撕成两半。
    """
    global _screen_lit
    lf.paused = True
    try:
        import control_center
        r = control_center.run(canvas, touch, disp=_disp)
    except Exception as e:
        print("[控制中心] 打不开：", e)
        r = None
        try:                            # 降级到老的纯音量滑杆，保证长按永远有东西可用
            import settings
            settings.run(canvas, touch)
        except Exception as e2:
            print("[控制中心] 降级设置页也失败：", e2)
    finally:
        lf.paused = False
        lf.clear_screen()
        lf.set_state("idle")
        lf.set_subtitle("")

    if r:
        # 亮度可能在控制中心里被调过（PWM 真调光），同步回 main 的亮/灭状态
        _screen_lit = True
        try:
            config.VOLUME_DB = -60.0 if r["volume"] <= 0 else (-40.0 + 40.0 * r["volume"] / 100.0)
        except Exception:
            pass
        print("[控制中心] 退出：音量=%s 亮度=%snit 模式=%s" % (r["volume"], r["nit"], r["mode"]))
    return r


def sleep_loop(touch, button):
    """休眠：屏幕黑着，耳朵醒着（后台监听器常驻监听）。返回唤醒方式 "tap" / "voice"。

    本循环只做轻量的触摸轮询 + 认领后台监听器置位的 _wake_pending，
    不自己录音 —— 麦克风全交给 _wake_listener 后台线程，免得和主线程抢。
    """
    print("[休眠] 熄屏省电中…（点屏幕或喊「你好 CIRA」唤醒）")
    screen_off()
    lf.sleeping = True
    if touch is not None:
        touch.clear_edge()

    while True:
        if touch is not None and (touch.take_edge() or touch.touching()):
            return "tap"
        if button is not None and button.value() == 0:
            while button.value() == 0:
                time.sleep(0.02)
            return "tap"
        # 语音唤醒由后台监听器置位，这里只认领
        if _wake_pending[0]:
            _wake_pending[0] = False
            return "voice"
        time.sleep_ms(30)


def idle_loop(canvas, touch, button):
    """待机态：短按唤醒对话 / 长按 1.2s 进控制中心 / 空闲熄屏 / 常开语音唤醒。

    主线程这里【只做触摸 + 认领语音唤醒】，绝不自己录音 —— 录音全在
    _wake_listener 后台线程，所以它不会被 1.5s 录音霸占，触摸采样始终跟手。

    长短按判定（手机同款成熟状态机）：
      · 落指记时；按满 1.2s **当场**触发长按并标记 consumed（松手不再补短按）。
      · 松手结算前做【消抖】：必须「持续松手」满 RELEASE_MS 才认，期间手指
        一旦回来就取消计时。这样 touching() 偶发抖动（I2C 瞬时读失败）不会把
        一次长按误判成短按 —— 这正是之前「长按退化成收听」的根因。
    """
    pressed = False          # 当前是否处于按下状态
    consumed = False         # 本次按下是否已被长按消费掉
    press_start_ms = 0
    last_touch_ms = 0        # 最近一次确认「手指还在」的时刻
    last_active_ms = time.ticks_ms()   # 最近一次「有交互」→ 熄屏倒计时基准
    release_detect_ms = 0     # 第一次探测到松手的时刻（消抖计时起点）

    RELEASE_MS = 150         # 持续松手满这么久才结算（消抖，防长按退化）
    LONG_MS = 1200           # 长按阈值 → 进控制中心
    SLEEP_MS = getattr(config, "IDLE_SLEEP_MS", 10000)

    def finish():
        """一轮交互结束后的收尾：清中断标志 + 回到待机画面。"""
        nonlocal last_active_ms, pressed, consumed, release_detect_ms
        pressed = False
        consumed = False
        release_detect_ms = 0
        last_active_ms = time.ticks_ms()
        if touch is not None:
            touch.clear_edge()
        lf.set_state("idle")
        lf.set_subtitle("")
        lf.force()

    if touch is not None:
        touch.clear_edge()

    while True:
        now_ms = time.ticks_ms()

        # ── 采样手指状态（关自动休眠后 touching() 可信；INT 边沿补极短触碰）──
        finger = False
        if touch is not None:
            finger = touch.touching()
            if not finger and touch.take_edge():
                finger = True

        if finger:
            last_touch_ms = now_ms
            last_active_ms = now_ms
            release_detect_ms = 0
            if not pressed:
                pressed = True
                consumed = False
                press_start_ms = now_ms
                print("[touch] DOWN")
        elif pressed and release_detect_ms == 0:
            release_detect_ms = now_ms   # 首次探测到松手，开始消抖计时

        # ── 按下中：够 1.2s 立刻进控制中心（不等松手）──────
        if pressed and not consumed:
            held = time.ticks_diff(now_ms, press_start_ms)
            if held >= LONG_MS:
                consumed = True          # 松手时不再结算短按
                print("[touch] LONG → 控制中心")
                lf.set_subtitle("控制中心")
                lf.force()
                open_control_center(canvas, touch)
                finish()
                continue

        # ── 松手结算（必须经消抖：持续松手满 RELEASE_MS）─────
        if pressed and release_detect_ms != 0:
            if time.ticks_diff(now_ms, release_detect_ms) >= RELEASE_MS:
                held = time.ticks_diff(last_touch_ms, press_start_ms)
                pressed = False
                if not consumed and held < LONG_MS:
                    print("[touch] TAP → 对话")
                    conversation(canvas, touch)   # 短按 → 唤醒应答 + 一轮对话
                    finish()
                    continue
                consumed = False
                release_detect_ms = 0

        # 退化按键唤醒（无触摸硬件时可用 BOOT 键）
        if not pressed and button is not None and button.value() == 0:
            t_btn = time.ticks_ms()
            while button.value() == 0:
                time.sleep(0.02)
            if time.ticks_diff(time.ticks_ms(), t_btn) >= LONG_MS:
                open_control_center(canvas, touch)
            else:
                conversation(canvas, touch)
            finish()
            continue

        # ── 语音唤醒（后台监听器置位，这里认领）────────────
        if not pressed and _wake_pending[0]:
            _wake_pending[0] = False
            print("[wake] 命中 → 语音对话")
            conversation(canvas, touch, how="voice")
            finish()
            continue

        # ── 空闲够久 → 熄屏休眠（耳朵不睡）────────────────
        if (not pressed) and time.ticks_diff(now_ms, last_active_ms) >= SLEEP_MS:
            how = sleep_loop(touch, button)
            conversation(canvas, touch, how=how)
            finish()
            continue

        # 渲染由后台 tick 线程驱动，这里只做短延时让出 CPU
        time.sleep_ms(20)


def main():
    print("=== CIRA Paideia Prototype ===")

    # 开机长按 BOOT(=GPIO0) 5 秒 → 强制进入配网
    try:
        boot = Pin(0, Pin.IN, Pin.PULL_UP)
        if boot.value() == 0:
            print("检测到 BOOT 长按，保持 5 秒进入重新配网…")
            t = time.time()
            while boot.value() == 0 and time.time() - t < 5:
                time.sleep(0.1)
            if boot.value() == 0:
                with open("force_setup", "w") as f:
                    f.write("1")
                print("写入 force_setup，重启进入配网…")
                machine.reset()
    except Exception:
        pass

    # 自举联网
    cfg = wifi_provision.ensure_network()
    if cfg.get("server_url"):
        config.SERVER_URL = cfg["server_url"]
    if not network.WLAN(network.STA_IF).isconnected():
        print("（未联网：语音闭环需联网；连上 Wi-Fi 后即可使用。）")

    canvas = build_canvas()
    touch = init_touch()

    # 初始化音频 codec 并应用默认音量（决策2：触摸滑杆调的就是它）
    # warmup() 是【全程唯一一次】打开功放的地方——功放上电必然「啪」一声（硬件级，
    # 麦克风实测 peak 达基线 367 倍，软件压不住）。开机响这一次之后功放常开，
    # 运行期间靠 DAC 静音位控制出声，对话中不再有任何爆音。
    try:
        audio_out.warmup()
        audio_out.get_codec().set_volume(getattr(config, "VOLUME_DB", -10.0))
        audio_out.silence_output()
    except Exception as e:
        print("（音频 codec 初始化失败）：", e)

    try:
        button = Pin(config.BUTTON_PIN, Pin.IN, Pin.PULL_UP)
    except Exception:
        button = None

    # 自检：打一下 /api/status
    try:
        import urequests
        st = urequests.get(config.SERVER_URL.rstrip("/") + "/api/status")
        print("服务端状态：", st.json())
        st.close()
    except Exception as e:
        print("（连不上 /api/status，检查 SERVER_URL 和服务端）：", e)

    # 光生命体实例 + 开机清屏
    global lf
    lf = lifeform.Lifeform(canvas) if canvas is not None else _NullLF()
    try:
        lf.clear_screen()
        lf.set_state("idle")
    except Exception:
        pass

    # 后台动画线程：独立于主线程驱动 lifeform.tick()，
    # 这样录音/思考等阻塞阶段画面仍持续呼吸（不卡死）。
    def _anim():
        while True:
            try:
                lf.tick()
            except Exception:
                pass
            time.sleep_ms(40)
    if canvas is not None:
        _thread.start_new_thread(_anim, ())

    # 后台唤醒监听器：常驻听"你好 CIRA"，与主线程（触摸/对话）并行互不阻塞。
    # 主线程专注触摸响应，麦克风用 _mic 锁和它互斥。唤醒关了就不起。
    if wake_listen_enabled():
        try:
            _thread.start_new_thread(_wake_listener, ())
            print("（后台唤醒监听器已启动）")
        except Exception as e:
            print("（唤醒监听器启动失败，退化为只认点按）：", e)

    # 唤醒应答音频（vivi2.0）：板载优先，缺了就联网拉一次并缓存到 flash。
    # 这一步失败不影响使用，只是唤醒时不出声。
    try:
        import wake
        n_ack = wake.ensure_acks()
        print("唤醒应答就绪：%d/%d 条" % (n_ack, len(wake.ACK_SPECS)))
    except Exception as e:
        print("（唤醒应答准备失败，唤醒将静默）：", e)

    print("就绪。短按屏幕开始对话；长按 1.2 秒进控制中心（无触摸时可用 BOOT 键）。")
    if wake_listen_enabled():
        print("麦克风常开：待机/熄屏时随时喊「你好 CIRA」都能叫醒它；"
              "说话过程中喊它也会立刻重新开始听。")
    else:
        print("语音唤醒已关闭（config.WAKE_VOICE=False），只能点按唤醒。")
    print("空闲 %.0f 秒自动熄屏。" % (getattr(config, "IDLE_SLEEP_MS", 10000) / 1000.0))
    while True:
        idle_loop(canvas, touch, button)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import machine, time
        print("启动异常，2s 后自动复位重试：", e)
        time.sleep(2)
        machine.reset()
