# cira_audio.py — ES8311 播放会话管理（移植自板子 ref_audio_out.py）
# 服务端下发 audio = 16k 16bit 单声道 WAV（audio_format=wav）。
# 剥掉 44 字节 WAV 头，把裸 PCM 直接喂 I2S TX，喇叭出声——不需要 MP3 解码。
#
# 防音爆铁律：功放只在 warmup() 开一次（全程常开），出不出声靠 ES8311 DAC 静音位切换。
from machine import I2S, Pin
import time
import cira_pins
import cira_codec
import mclk

# ── 播放会话状态（整轮共用一个 I2S + 一次功放开关）──
_i2s = None       # 当前 I2S TX 实例（None = 会话未开）
_i2s_rate = None  # 当前会话的采样率
_pa = None        # 功放使能脚
_ZERO = b"\x00\x00" * 256   # 512B 静音块，复用避免反复分配
_codec = None     # 持久 codec 实例


def _zeros(i2s, n_blocks):
    """向 I2S 写 n_blocks 个静音块（每块 256 采样）。"""
    for _ in range(n_blocks):
        i2s.write(_ZERO)


def get_codec():
    """懒初始化并缓存 ES8311 实例（设置页调 set_volume 也用它）。绝不动 PA_CTRL。"""
    global _codec
    if _codec is None:
        mclk.enable_mclk()
        _codec = cira_codec.ES8311()
        _codec.init()
        _codec.set_volume(cira_pins.VOLUME_DB)
        _codec.mute(True)                 # 默认静音，出声只发生在播放会话里
    return _codec


def warmup():
    """开机调用一次：把功放打开并保持常开（整个运行期间不再关闭）。

    这里是全程唯一一次功放上电，也就是唯一一次爆音。做完之后 DAC 保持静音，
    喇叭安静；之后所有出声/静音都靠 DAC 静音位切换，不再动功放。
    """
    global _pa
    mclk.enable_mclk()
    codec = get_codec()
    codec.set_volume(cira_pins.VOLUME_DB)
    codec.mute(True)
    t = None
    try:
        t = I2S(
            cira_pins.ES8311_I2S_ID,
            sck=Pin(cira_pins.ES8311_BCK), ws=Pin(cira_pins.ES8311_WS),
            sd=Pin(cira_pins.ES8311_SDO),
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=cira_pins.SAMPLE_RATE,
            ibuf=8192,
        )
        _zeros(t, 20)                   # ~320ms 静音，让 DAC 输出稳定
    except Exception as e:
        print("（warmup I2S 失败）:", e)
    _pa = Pin(cira_pins.ES8311_PA_CTRL, Pin.OUT)
    _pa.value(1)                        # ← 全程唯一一次功放上电（会响一声）
    time.sleep_ms(400)                  # 等 pop 完全过去
    if t is not None:
        try:
            _zeros(t, 4)
            t.deinit()                  # 功放保持开着，实测切 I2S 不会爆
        except Exception:
            pass


def play_begin(rate=None):
    """开启一轮播放会话：初始化 I2S + 解除 DAC 静音（幂等）。不碰功放。"""
    global _i2s, _i2s_rate
    rate = rate or cira_pins.SAMPLE_RATE
    if _i2s is not None:
        if _i2s_rate == rate:
            return                      # 会话已开且采样率一致 → 直接复用
        play_end()                      # 采样率变了，只能重开

    mclk.enable_mclk()
    codec = get_codec()
    codec.set_volume(cira_pins.VOLUME_DB)
    codec.mute(True)                    # 开启过程保持 DAC 静音

    _i2s = I2S(
        cira_pins.ES8311_I2S_ID,
        sck=Pin(cira_pins.ES8311_BCK), ws=Pin(cira_pins.ES8311_WS),
        sd=Pin(cira_pins.ES8311_SDO),
        mode=I2S.TX, bits=16, format=I2S.MONO, rate=rate,
        ibuf=8192,
    )
    _i2s_rate = rate
    _zeros(_i2s, 4)
    codec.mute(False)


def _wav_rate_and_data(wav, rate=None):
    """从 WAV 头取真实采样率并剥头，返回 (rate, pcm)。裸 PCM 则用默认采样率。"""
    rate = rate or cira_pins.SAMPLE_RATE
    if wav[:4] == b"RIFF" and len(wav) >= 28:
        try:
            rate = int.from_bytes(wav[24:28], "little")
        except Exception:
            pass
        data = wav[44:]
    else:
        data = wav
    if len(data) % 2:                   # I2S 写入要求偶数长度
        data = data[:-1]
    return rate, data


def play_chunk(wav, abort_cb=None):
    """播放一句（会话内）：只写 PCM，不开关功放/I2S → 句与句之间无爆音。

    abort_cb：每写 4096 字节问一次"要不要停"。返回 True=播完；False=被打断。
    用于"孩子再次唤醒 → 必须马上闭嘴"：命中时立刻 DAC 静音（≈瞬时静音）。
    """
    if not wav:
        return True
    rate, data = _wav_rate_and_data(wav)
    if len(data) < 4:
        return True
    play_begin(rate)
    i2s = _i2s
    if i2s is None:
        return True
    chunk = 4096
    for i in range(0, len(data), chunk):
        if abort_cb is not None:
            try:
                if abort_cb():
                    try:
                        if _codec is not None:
                            _codec.mute(True)
                    except Exception:
                        pass
                    return False
            except Exception:
                pass
        i2s.write(data[i:i + chunk])
    _zeros(i2s, 4)
    return True


def play_end():
    """结束一轮播放：补零 → DAC 静音 → 关 I2S。幂等。绝不关功放。"""
    global _i2s, _i2s_rate
    if _i2s is None:
        return
    i2s = _i2s
    _i2s = None          # 先置空：即便下面出异常，会话状态也不卡住
    _i2s_rate = None
    try:
        _zeros(i2s, 4)
        try:
            if _codec is not None:
                _codec.mute(True)
        except Exception:
            pass
        time.sleep_ms(10)
    finally:
        try:
            i2s.deinit()
        except Exception:
            pass


def play_wav(wav, rate=cira_pins.SAMPLE_RATE):
    """单句播放兼容接口（内部 = begin + chunk + end）。"""
    if not wav:
        return
    try:
        play_chunk(wav)
    finally:
        play_end()


def silence_output():
    """把输出通路静默：结束播放会话 + DAC 静音。不关功放。幂等。"""
    try:
        play_end()
    except Exception:
        pass
    try:
        if _codec is not None:
            _codec.mute(True)
    except Exception:
        pass
