# mclk.py — 音频主时钟 MCLK 方波（PWM GPIO2, 4.096MHz）
# 为什么需要：ES8311/ES7210 内部 DAC/ADC 需主时钟才会工作；legacy I2S 无 mck= 参数，
# 故用 LEDC/PWM 在 GPIO2 产生方波当 MCLK（移植自板子 ref_mclk.py）。
from machine import Pin, PWM
import cira_pins

_pwm = None          # 必须保持全局引用，否则被 GC 回收后时钟会停


def enable_mclk(pin=None, freq=None):
    """开启 MCLK。重复调用安全，返回实际频率。"""
    global _pwm
    if pin is None:
        pin = cira_pins.ES8311_MCLK
    if freq is None:
        freq = cira_pins.SAMPLE_RATE * 256      # 16000*256 = 4.096MHz
    if _pwm is None:
        _pwm = PWM(Pin(pin))
    _pwm.freq(freq)
    _pwm.duty_u16(32768)                         # 50% 占空比
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
