# -*- coding: utf-8 -*-
"""
语音播放（ES8311 内置扬声器 / MAX98357A 外接功放）← 16-bit PCM WAV
=================================================================
服务端下发的 audio 是 16k 16bit 单声道 WAV（audio_format=wav）。
剥掉 44 字节 WAV 头，把裸 PCM 直接喂给 I2S TX，喇叭就出声了——
**不需要任何 MP3 解码**，这正是用 WAV 的原因。

── 防音爆（pop）设计：功放常开 + DAC 静音门控 ──────────────────
【麦克风实测结论，2026-08-07】音爆的唯一来源是**功放使能脚 PA_CTRL 从低到高**：
    基线 peak=26 → PA 拉高约 200ms 后 peak=9552（367 倍），两次复现
而且这是硬件级的，软件压不住 —— A/B 实听验证四种手段全部无效：
    ✗ I2S 先跑零 500ms 再开功放      ✗ PWM 软启动（渐升使能脚）
    ✗ DAC 保持不静音、持续输出数字零  ✗ 缩短/拉长各种等待
但同一次实听验证了关键事实：**功放常开时，反复切换录音/播放 I2S 完全安静**。

所以策略是：**功放只在开机 warmup() 时打开一次，运行期间永不关闭**，
出不出声完全靠 ES8311 的 DAC 静音位控制。爆音从「每轮一次」降到「开机一次」。

对外 API：
    warmup()          开机调用一次：开 I2S 跑零 → 开功放（唯一一次 pop）→ DAC 静音
    play_begin(rate)  一轮开始：开 I2S + 解除 DAC 静音（不碰功放）
    play_chunk(wav)   每句调用：只写 PCM
    play_end()        一轮结束：补零 → DAC 静音 → 关 I2S（不碰功放）
    silence_output()  录音等要重配 I2S 前调用：确保 DAC 静音（不碰功放）

⚠️【铁律】play_*/silence_output 一律不得操作 PA_CTRL。任何一处把功放关掉，
下次开启就是一声爆响。功放的开关只存在于 warmup() 里。

play_wav() 保留为单句兼容接口 = begin + chunk + end。
"""

from machine import I2S, Pin
import time
import config

# ── 播放会话状态（整轮共用一个 I2S + 一次功放开关）──
_i2s = None       # 当前 I2S TX 实例（None = 会话未开）
_i2s_rate = None  # 当前会话的采样率
_pa = None        # 功放使能脚

_ZERO = b"\x00\x00" * 256   # 512B 静音块，复用避免反复分配


def _zeros(i2s, n_blocks):
    """向 I2S 写 n_blocks 个静音块（每块 256 采样）。"""
    for _ in range(n_blocks):
        i2s.write(_ZERO)


def warmup():
    """开机调用一次：把功放打开并保持常开（整个运行期间不再关闭）。

    这里是**全程唯一一次**功放上电，也就是唯一一次爆音。做完之后 DAC 保持静音，
    喇叭安静；之后所有出声/静音都靠 DAC 静音位切换，不再动功放。

    顺序：I2S 跑零把线路稳定 → 开功放 → 等 pop 过去 → 关 I2S（功放留着）。
    """
    global _pa
    from mclk import enable_mclk
    enable_mclk()
    if config.SPEAKER_PATH != "es8311":
        return
    codec = get_codec()
    codec.set_volume(config.VOLUME_DB)
    codec.mute(True)
    t = None
    try:
        t = I2S(
            config.ES8311_I2S_ID,
            sck=Pin(config.ES8311_BCK), ws=Pin(config.ES8311_WS),
            sd=Pin(config.ES8311_SDO),
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=config.SAMPLE_RATE,
            ibuf=8192,
        )
        _zeros(t, 20)                   # ~320ms 静音，让 DAC 输出稳定
    except Exception as e:
        print("（warmup I2S 失败）:", e)
    _pa = Pin(config.ES8311_PA_CTRL, Pin.OUT)
    _pa.value(1)                        # ← 全程唯一一次功放上电（会响一声）
    time.sleep_ms(400)                  # 等 pop 完全过去
    if t is not None:
        try:
            _zeros(t, 4)
            t.deinit()                  # 功放保持开着，实测切 I2S 不会爆
        except Exception:
            pass


def play_begin(rate=None):
    """开启一轮播放会话：初始化 I2S + 解除 DAC 静音（幂等）。

    ⚠️ 不碰功放 —— 功放在 warmup() 里已常开，这里再开关就会爆。
    同一轮内重复调用不会重开；采样率变化时会自动重建会话。
    """
    global _i2s, _i2s_rate      # 注意：不含 _pa —— 播放路径不得操作功放
    rate = rate or config.SAMPLE_RATE
    if _i2s is not None:
        if _i2s_rate == rate:
            return                      # 会话已开且采样率一致 → 直接复用
        play_end()                      # 采样率变了，只能重开

    # MCLK 先开：codec 的 DAC 需要主时钟。与录音共用 GPIO2 的 4.096MHz PWM，幂等。
    from mclk import enable_mclk
    enable_mclk()

    if config.SPEAKER_PATH == "es8311":
        # 持久 codec 实例（启动已 init 一次）。【绝不要】每次播放都 init()——
        # 反复 init 会 toggling 一堆寄存器造成爆音。
        codec = get_codec()
        codec.set_volume(config.VOLUME_DB)
        codec.mute(True)                # 开启过程保持 DAC 静音

        _i2s = I2S(
            config.ES8311_I2S_ID,
            sck=Pin(config.ES8311_BCK), ws=Pin(config.ES8311_WS),
            sd=Pin(config.ES8311_SDO),
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=rate,
            ibuf=8192,
        )
        _i2s_rate = rate
        # 先跑零让 BCLK/WS/SDOUT 时序稳定、DAC 输出稳在 0V，再在零电平处解除静音
        _zeros(_i2s, 4)
        codec.mute(False)
    else:
        # 外接 MAX98357A 或其他 I2S 功放芯片
        _i2s = I2S(
            config.AMP_I2S_ID,
            sck=Pin(config.AMP_SCK), ws=Pin(config.AMP_WS), sd=Pin(config.AMP_DIN),
            mode=I2S.TX, bits=16, format=I2S.MONO, rate=rate,
            ibuf=8192,
        )
        _i2s_rate = rate
        _zeros(_i2s, 4)


def _wav_rate_and_data(wav, rate=None):
    """从 WAV 头取真实采样率并剥头，返回 (rate, pcm)。裸 PCM 则用默认采样率。"""
    rate = rate or config.SAMPLE_RATE
    if wav[:4] == b"RIFF" and len(wav) >= 28:
        # 优先用 WAV 头的采样率，避免「24k 被当 16k 播 → 慢 1.5 倍、低八度发闷」
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

    会话未开时自动 play_begin（采样率取自 WAV 头）。

    abort_cb：可选回调，每写 4096 字节（≈128ms @16k）问一次"要不要停"。
    返回 True = 整句播完；False = 被打断。
    用于「孩子不想听这条回答，再次唤醒 → 必须马上闭嘴」：
    命中时立刻把 DAC 静音，连 I2S 内部缓冲里的残音也发不出来（≈瞬时静音），
    但【不碰功放】—— 关功放必爆音，这是硬件级铁律。
    """
    if not wav:
        return True
    rate, data = _wav_rate_and_data(wav)
    if len(data) < 4:
        return True
    play_begin(rate)                    # 幂等：已开就复用
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
    # 句尾补一小段零：① 让尾音播完 ② 下一句还在下载时 I2S 若 underrun，
    # 底层重复的是这段【零】而不是上一句残留的语音片段（否则会听到"卡带"）。
    _zeros(i2s, 4)
    return True


def play_end():
    """结束一轮播放：补零 → DAC 静音 → 关 I2S。幂等。

    ⚠️ 【绝不关功放】。实测功放常开时关 I2S 完全安静；而一旦关掉功放，
    下次开启必然爆一声（peak 达基线 367 倍）。
    """
    global _i2s, _i2s_rate
    if _i2s is None:
        return
    i2s = _i2s
    _i2s = None          # 先置空：即便下面出异常，会话状态也不会卡住
    _i2s_rate = None
    try:
        _zeros(i2s, 4)                  # 尾音播完
        try:
            if _codec is not None:
                _codec.mute(True)       # 静音（功放留着，靠 DAC 位静音）
        except Exception:
            pass
        time.sleep_ms(10)
    finally:
        try:
            i2s.deinit()                # 关总线（DAC 已静音 → 台阶听不到）
        except Exception:
            pass


def play_wav(wav, rate=config.SAMPLE_RATE):
    """单句播放兼容接口（内部 = begin + chunk + end）。

    多句连播请改用 play_chunk + play_end，否则每句都会开关一次功放（爆音）。
    """
    if not wav:
        return
    try:
        play_chunk(wav)
    finally:
        play_end()


# ── 持久 codec 实例：供设置页调节音量（不随每次播放重建）──
_codec = None


def get_codec():
    """懒初始化并缓存 ES8311 实例（设置页调 set_volume 也用它）。

    ⚠️ 这里【绝不要操作 PA_CTRL】——既不开也不关。功放的开关只发生在 warmup()
    里那一次；此函数会被设置页等多处调用，若在这里关功放，下次播放开功放就是
    一声爆响。
    """
    global _codec
    if _codec is None:
        from mclk import enable_mclk
        enable_mclk()
        from es8311 import ES8311
        _codec = ES8311(config.ES8311_I2C_SCL, config.ES8311_I2C_SDA)
        _codec.init()
        _codec.set_volume(config.VOLUME_DB)
        _codec.mute(True)                 # 默认静音，出声只发生在播放会话里
    return _codec


def silence_output():
    """把输出通路静默：结束播放会话 + DAC 静音。

    在任何会重配 I2S1 的操作之前调用（尤其是【录音】——录放共用 I2S1）。
    实测功放常开时切换 TX/RX 完全安静，所以这里**不关功放**，只保证 DAC 静音。
    幂等，随便调。
    """
    try:
        play_end()          # 若播放会话还开着，先干净收尾（内部已含 DAC 静音）
    except Exception:
        pass
    try:
        if _codec is not None:
            _codec.mute(True)
    except Exception:
        pass
