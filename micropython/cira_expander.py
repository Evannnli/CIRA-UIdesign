# cira_expander.py — TCA9554 I2C GPIO 扩展芯片驱动（I2C 0x20）
# 板子 CST816 触摸 RST 走 TCA9554 的 EXIO（也可能走 GPIO1，两者都做最稳），
# LCD 的 RST 走 EXIO2。TCA9554 上电默认所有扩展脚为"输入"（等效被拉在复位态），
# 所以必须开机把全部 EXIO 设成"输出+高电平"来释放复位。
# 移植自板子 tca9554.py（含重试与影子寄存器），改用共享 I2C。
from machine import Pin
import time
import cira_i2c

TCA_ADDR = 0x20
REG_IN, REG_OUT, REG_POL, REG_CFG = 0x00, 0x01, 0x02, 0x03


class TCA9554:
    def __init__(self):
        self.i2c = cira_i2c.get_i2c()
        self._out = 0xFF   # 影子寄存器，默认全高

    def _wr(self, reg, data, tries=5):
        """带重试的 I2C 写，规避软复位后总线瞬态 ETIMEDOUT。"""
        if not isinstance(data, (bytes, bytearray)):
            data = bytes([data])
        last = None
        for _ in range(tries):
            try:
                self.i2c.writeto_mem(TCA_ADDR, reg, data)
                return True
            except OSError as e:
                last = e
                time.sleep_ms(10)
        raise last

    def init(self, out=0xFF):
        """配置全部为输出，先释放所有复位，再对 LCD/Touch 复位线发低有效脉冲。

        原厂固件流程：TCA9554 EXIO0/EXIO1 脉冲（注释"复位 LCD 与 TouchPad"），
        且 QSPI_PIN_NUM_LCD_RST=GPIO_NUM_NC（无 GPIO 复位）。本板 HW V2 文档记 LCD RST 在 EXIO2。
        为覆盖所有版本，对 EXIO0/EXIO1/EXIO2 三路都发 低10ms→高50ms 脉冲。
        """
        self._wr(REG_CFG, b'\x00')     # 0x00 = 全部输出
        self._out = 0xFF
        self._wr(REG_OUT, bytes([self._out]))   # 先全部拉高（释放）
        # 复位脉冲（低有效）：EXIO0/EXIO1（原厂）与 EXIO2（HW V2 文档）都脉冲，覆盖所有版本
        mask = (1 << 0) | (1 << 1) | (1 << 2)   # EXIO0, EXIO1, EXIO2 (0-indexed)
        self._out = 0xFF & ~mask
        self._wr(REG_OUT, bytes([self._out]))   # 这三路拉低
        time.sleep_ms(10)
        self._out = 0xFF
        self._wr(REG_OUT, bytes([self._out]))   # 全部释放
        time.sleep_ms(50)

    def set_pin(self, pin, level):
        """pin: 1..8（对应 EXIO_PIN1..PIN8）；level: 0/1。不影响其它脚。"""
        bit = 1 << (pin - 1)
        if level:
            self._out |= bit
        else:
            self._out &= ~bit
        self._wr(REG_OUT, bytes([self._out]))

    def reset_lcd(self):
        """LCD RST 在 EXIO2（pin2），低有效。脉冲：低 10ms → 高 50ms。"""
        self.set_pin(2, 0)
        time.sleep_ms(10)
        self.set_pin(2, 1)
        time.sleep_ms(50)


def init():
    """开机初始化：所有扩展脚设输出并拉高（释放 LCD / CST816 复位）。返回 TCA 实例。"""
    t = TCA9554()
    t.init(0xFF)
    return t
