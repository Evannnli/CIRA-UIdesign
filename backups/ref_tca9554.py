# -*- coding: utf-8 -*-
"""
TCA9554PWR I2C GPIO 扩展芯片驱动（ESP32-S3 · MicroPython）
============================================================
微雪 1.85C-BOX 上：
  · 屏幕 RST 复位脚经此芯片 EXIO2（pin2）控制
  · 背光、触摸 RST 等也可能走这里
I2C 地址 0x20，与 ES8311/ES7210/RTC/触摸共用总线（GPIO10/11，I2C(0)）。

寄存器：
  0x00 INPUT  读电平
  0x01 OUTPUT 写输出电平
  0x02 POLARITY 极性反转（默认 0）
  0x03 CONFIG  0=输出 1=输入（默认 0xFF 全输入）

官方 Arduino 里：TCA9554PWR_Init(0x00) 把全部设成输出；
  ST7701_Reset() = Set_EXIO(EXIO_PIN2, Low) 10ms → High 50ms（即 LCD RST，低有效）。
"""
from machine import I2C, Pin


class TCA9554:
    ADDR = 0x20
    REG_IN, REG_OUT, REG_POL, REG_CFG = 0x00, 0x01, 0x02, 0x03

    def __init__(self, scl=10, sda=11, freq=100_000, i2c_id=0):
        self._bus_recover(scl, sda)
        self.i2c = I2C(i2c_id, scl=Pin(scl), sda=Pin(sda), freq=freq)
        self._out = 0xFF  # 影子寄存器，默认全高

    @staticmethod
    def _bus_recover(scl, sda):
        """释放被某设备拉低的 SDA：手动在 SCL 上补 9 个时钟脉冲（I2C 总线恢复）。
        软复位多次后总线易卡死，此步可免硬拔插自愈。"""
        import time
        sda_p = Pin(sda, Pin.OUT, value=1)
        scl_p = Pin(scl, Pin.OUT, value=1)
        time.sleep_ms(2)
        for _ in range(9):
            scl_p.value(0); time.sleep_us(5)
            scl_p.value(1); time.sleep_us(5)
        sda_p.value(0); time.sleep_us(5)
        sda_p.value(1); time.sleep_us(5)

    def _wr(self, reg, data, tries=5):
        """带重试的 I2C 写，规避软复位后总线瞬态 ETIMEDOUT（ESP32 I2C 常见）。"""
        import time
        if not isinstance(data, (bytes, bytearray)):
            data = bytes([data])
        last = None
        for _ in range(tries):
            try:
                self.i2c.writeto_mem(self.ADDR, reg, data)
                return True
            except OSError as e:
                last = e
                time.sleep_ms(10)
        raise last

    def init(self, out=0xFF):
        """配置全部为输出，并写入输出电平（默认 0xFF 全高）。"""
        self._wr(self.REG_CFG, b'\x00')  # 0x00 = 全部输出
        self._out = out & 0xFF
        self._wr(self.REG_OUT, bytes([self._out]))

    def set_pin(self, pin, level):
        """pin: 1..8（对应 EXIO_PIN1..PIN8）；level: 0/1。不影响其它脚。"""
        bit = 1 << (pin - 1)
        if level:
            self._out |= bit
        else:
            self._out &= ~bit
        self._wr(self.REG_OUT, bytes([self._out]))

    def reset_lcd(self):
        """LCD RST 在 EXIO2（pin2），低有效。脉冲：低 10ms → 高 50ms。"""
        self.set_pin(2, 0)
        import time
        time.sleep_ms(10)
        self.set_pin(2, 1)
        time.sleep_ms(50)
