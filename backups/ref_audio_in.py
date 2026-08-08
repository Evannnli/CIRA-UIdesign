# -*- coding: utf-8 -*-
"""
麦克风录音（INMP441 / 任意 I2S 数字麦）→ 16-bit PCM WAV
======================================================
用 machine.I2S 的 RX 模式读麦克风，攒成一段 WAV 返回。
默认 16000Hz 单声道 16-bit，正好对上服务端 ASR。

内存提醒：RECORD_SECONDS 秒 ≈ 16000*2*秒 字节（4 秒≈128KB）。
ESP32-S3 够用；若经常性内存不足，把 config.RECORD_SECONDS 调到 3。
"""

import struct
import time
from machine import I2S, Pin
import config


def record_wav(seconds=config.RECORD_SECONDS, rate=config.SAMPLE_RATE, abort_cb=None):
    """录一段 WAV。

    abort_cb()：可选，返回 True 就立刻停止录音并返回 None。
      唤醒监听是常驻的（待机时一段接一段地录），如果这个过程不可打断，
      孩子伸手点屏幕最坏要等满整个窗口（实测 2.0 秒）才有反应。
      三个检查点，越早越好：
        1) 进函数第一件事（手已经在屏上 → 0ms 就让路，一分钱开销都不花）
        2) 丢弃启动瞬态的循环里（此时 codec/I2S 已开，约 290ms）
        3) 正式采集每读满一个 chunk（≈128ms）
      实测最坏响应从 2032ms 压到 ~300ms。
    """
    def _aborted():
        if abort_cb is None:
            return False
        try:
            return bool(abort_cb())
        except Exception:
            return False

    # 手已经在屏上了就别启动录音链路 —— 开 MCLK / 初始化 codec / 建 I2S
    # 这一串固定开销就要 ~290ms，能省则省。
    if _aborted():
        return None

    # 微雪 1.85C-BOX V2：双麦经 ES7210（I2S RX）输入
    #
    # ⚠️ MCLK 必须先开、且要在整个录音期间持续输出，否则 ES7210 的 ADC 不工作，
    #    数据线上读出来全是 0（已实测验证）。MicroPython legacy I2S 不输出 MCLK，
    #    所以用 PWM 在 GPIO2 上造一个 4.096MHz 方波。
    from mclk import enable_mclk
    enable_mclk()

    # ── 切换 I2S 到 RX（录音）前先静默 DAC ──
    # 录音与播放【共用 I2S1】(BCK=48 / WS=38)。切到 RX 时 ES8311 的 DAC 侧可能留直流台阶，
    # 先把 DAC 静音（silence_output 内部只 mute，不再碰功放——功放开机常开，见 audio_out.warmup）。
    # 这样即使有台阶也听不见，且不会触发功放上电 pop（pop 的唯一来源是 PA 使能本身，已靠常开规避）。
    try:
        import audio_out
        audio_out.silence_output()
        time.sleep_ms(5)
    except Exception:
        pass

    from es7210 import ES7210
    codec = ES7210(config.ES7210_I2C_SCL, config.ES7210_I2C_SDA)
    codec.init()

    i2s = I2S(
        config.ES7210_I2S_ID,
        sck=Pin(config.ES7210_BCK), ws=Pin(config.ES7210_WS), sd=Pin(config.ES7210_SD),
        mode=I2S.RX, bits=16, format=I2S.MONO, rate=rate,
        ibuf=rate * 4,  # 2 秒缓冲（16bit 单声道）
    )

    # ── 丢弃录音启动瞬态（关键，2026-08-07 实测）──
    # I2S RX 刚初始化时 ES7210 会输出一段削顶尖峰（单点峰值≈32767、RMS 却很低）。
    # 若不丢弃，服务端 AGC 按全局峰值算增益会被它压到 0.5× 以下，真实语音被压垮
    # → ASR 返回空 → 设备反复「没听清」。实测尖峰集中在开头 ~150ms，先吃掉这段再正式采集。
    chunk = bytearray(4096)
    _discard = int(rate * 0.15) * 2   # 150ms × 2 字节/样本
    while _discard > 0:
        n = i2s.readinto(chunk)
        if n:
            _discard -= n
        if _aborted():
            i2s.deinit()
            return None

    # int()：唤醒监听会传 1.5 这类小数秒，float 长度会让 bytearray() 直接报错
    n_bytes = int(rate * seconds) * 2
    pcm = bytearray(n_bytes)
    idx = 0
    while idx < n_bytes:
        n = i2s.readinto(chunk)
        if n:
            pcm[idx:idx + n] = chunk[:n]
            idx += n
        if _aborted():
            i2s.deinit()
            return None
    i2s.deinit()
    return _wrap_wav(pcm, rate)


def _wrap_wav(pcm, rate):
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm
