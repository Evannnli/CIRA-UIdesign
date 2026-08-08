# cira_i2c.py — 共享 I2C0 总线（ES8311 / CST816 / RTC / TCA9554 共用 GPIO10/11）
# 移植自板子 tca9554.py 的总线恢复经验：软复位后总线易卡死（SDA 被某设备拉低），
# 必须先补 9 个 SCL 脉冲自愈，否则 I2C 读写时通时不通。
from machine import I2C, Pin
import time
import cira_pins

_i2c = None


def _bus_recover(scl, sda):
    """释放被某设备拉低的 SDA：手动在 SCL 上补 9 个时钟脉冲（I2C 总线恢复）。"""
    sda_p = Pin(sda, Pin.OUT, value=1)
    scl_p = Pin(scl, Pin.OUT, value=1)
    time.sleep_ms(2)
    for _ in range(9):
        scl_p.value(0); time.sleep_us(5)
        scl_p.value(1); time.sleep_us(5)
    sda_p.value(0); time.sleep_us(5)
    sda_p.value(1); time.sleep_us(5)


def get_i2c():
    """返回（懒初始化）共享 I2C0 实例。重复调用返回同一对象。

    ⚠️ 原厂固件所有 I2C 设备均用 I2C(0)（GPIO10/11, 100kHz）。CST816 仅能在此总线上
    稳定应答——前提是先 _bus_recover 解除卡死。
    """
    global _i2c
    if _i2c is None:
        _bus_recover(cira_pins.I2C_SCL, cira_pins.I2C_SDA)
        _i2c = I2C(0, scl=Pin(cira_pins.I2C_SCL),
                   sda=Pin(cira_pins.I2C_SDA), freq=100000)
    return _i2c


def recover():
    """总线锁死自愈：补 9 个 SCL 脉冲 + 重建 I2C 实例。返回新实例。

    ESP32 I2C 与部分设备（CST816/ES8311）偶发传输完不释放 SDA，导致后续事务
    ENODEV。原厂 tca9554._bus_recover 即此意。在驱动的读写重试里调用。
    """
    global _i2c
    _bus_recover(cira_pins.I2C_SCL, cira_pins.I2C_SDA)
    _i2c = I2C(0, scl=Pin(cira_pins.I2C_SCL),
               sda=Pin(cira_pins.I2C_SDA), freq=100000)
    return _i2c
