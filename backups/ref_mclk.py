# -*- coding: utf-8 -*-
"""
音频主时钟 MCLK 输出（PWM 方案）
================================
为什么需要：ES7210 / ES8311 这类 codec 的内部 ADC/DAC 需要一个主时钟（MCLK，
通常 256*fs ≈ 4.096MHz @16kHz）才会真正开始工作。即使 codec 跑在从机模式
（BCLK/LRCK 由 ESP32 提供），没有 MCLK 时 ES7210 的数据线上就是恒定 0。

为什么用 PWM：本固件（ESP32_GENERIC_S3 v1.28.0）的 machine.I2S 是 legacy API，
构造函数不接受 mck= 关键字，无法让 I2S 外设输出 MCLK。改用 LEDC/PWM 在 GPIO2
上产生方波当 MCLK。

实测结论（1.85C-BOX V2）：
  - 不开 MCLK  → ES7210 读出全 0（16/32bit、mono/stereo 四种组合都是 0）
  - 开 4.096MHz → 立刻读到连续平滑的音频波形
  - 2.048MHz 也能出数据（ES7210 从机模式会自动检测 MCLK/LRCK 比率）

PWM 分频器无法精确得到 4.096MHz，实测约 4.0895MHz（偏差 0.16%）。ES7210 处于
从机模式，采样率由 LRCK 决定，MCLK 只作内部工作时钟，这点偏差不影响音高。
"""

from machine import Pin, PWM
import config

_pwm = None          # 必须保持全局引用，否则被 GC 回收后时钟会停


def enable_mclk(pin=None, freq=None):
    """开启 MCLK。重复调用安全，返回实际频率。"""
    global _pwm
    if pin is None:
        pin = config.ES8311_MCLK
    if freq is None:
        freq = config.SAMPLE_RATE * 256      # 16000*256 = 4.096MHz
    if _pwm is None:
        _pwm = PWM(Pin(pin))
    _pwm.freq(freq)
    _pwm.duty_u16(32768)                     # 50% 占空比
    return _pwm.freq()


def disable_mclk():
    """关闭 MCLK（一般不需要；省电场景可用）。"""
    global _pwm
    if _pwm is not None:
        try:
            _pwm.deinit()
        except Exception:
            pass
        _pwm = None


# 兼容旧调用名
mclk_on = enable_mclk
