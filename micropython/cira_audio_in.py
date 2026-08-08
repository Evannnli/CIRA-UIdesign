# cira_audio_in.py — ES7210 录音（I2S1 RX，与播放共用 I2S1，MCLK 由 cira mclk 提供）
# 不导入 frozen audio_in：它会拉 frozen mclk 在 GPIO2 再建一个 PWM，与 cira mclk 冲突
# （同一脚两个 PWM → 时钟异常）。本模块直接用 cira 的 mclk + cira_audio 静音 +
# frozen es7210 编解码器（仅 I2C 配置寄存器，不动 MCLK）。
#
# 返回 16-bit 单声道 16kHz WAV（与服务端 ASR 对齐）。失败/被打断返回 None。
import struct
import time
from machine import I2S, Pin
import cira_pins
import mclk
import cira_audio


def _wrap_wav(pcm, rate):
    header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(pcm))
    return header + pcm


def record_wav(seconds=3, rate=cira_pins.SAMPLE_RATE, abort_cb=None):
    """录一段 WAV。abort_cb() 返回 True 立即停录并返回 None。

    内存：seconds 秒 ≈ rate*2*秒 字节（3 秒≈96KB），板子 PSRAM 充足。
    """

    def _aborted():
        if abort_cb is None:
            return False
        try:
            return bool(abort_cb())
        except Exception:
            return False

    if _aborted():
        return None

    # MCLK 已在 cira_audio.warmup 开过；这里再 ensure 一次（幂等，不会重建 PWM）
    mclk.enable_mclk()

    # 录音前静默 DAC（避免共享 I2S1 的直流台阶被录进去 / 回声）
    try:
        cira_audio.silence_output()
        time.sleep_ms(5)
    except Exception:
        pass

    # ES7210 编解码器初始化（I2C，与 ES8311 同总线不同地址）；仅配置寄存器
    from es7210 import ES7210
    codec = ES7210(cira_pins.I2C_SCL, cira_pins.I2C_SDA)
    codec.init()

    i2s = I2S(
        cira_pins.ES8311_I2S_ID,
        sck=Pin(cira_pins.ES8311_BCK), ws=Pin(cira_pins.ES8311_WS),
        sd=Pin(cira_pins.ES8311_SDI),
        mode=I2S.RX, bits=16, format=I2S.MONO, rate=rate,
        ibuf=rate * 4,  # 2 秒缓冲（16bit 单声道）
    )

    # 丢弃录音启动瞬态（ES7210 开头 ~150ms 尖峰，会被 AGC 压垮真实语音）
    chunk = bytearray(4096)
    _discard = int(rate * 0.15) * 2
    _last = time.ticks_ms()
    while _discard > 0:
        n = i2s.readinto(chunk)
        if n:
            _discard -= n
            _last = time.ticks_ms()
        else:
            # 无数据超过 2s：ES7210/MCLK 链路异常，直接放弃，避免硬挂死
            if time.ticks_diff(time.ticks_ms(), _last) > 2000:
                i2s.deinit()
                return None
        if _aborted():
            i2s.deinit()
            return None

    n_bytes = int(rate * seconds) * 2
    pcm = bytearray(n_bytes)
    idx = 0
    _last = time.ticks_ms()
    while idx < n_bytes:
        n = i2s.readinto(chunk)
        if n:
            pcm[idx:idx + n] = chunk[:n]
            idx += n
            _last = time.ticks_ms()
        else:
            if time.ticks_diff(time.ticks_ms(), _last) > 2000:
                i2s.deinit()
                return None
        if _aborted():
            i2s.deinit()
            return None
    i2s.deinit()
    return _wrap_wav(pcm, rate)
