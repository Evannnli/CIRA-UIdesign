# cira_touch.py — CST816 电容触摸驱动（ESP32-S3 · MicroPython）
# 移植自板子 ref_cst816.py（微雪 1.85C-BOX，I2C 0x15，INT=GPIO4），改用共享 I2C。
# 实测 ChipID=0xB5 → CST816T。关键：写 0xFE(DisAutoSleep)=1 关自动休眠后 I2C 才稳定。
from machine import Pin
import time
import cira_i2c

CST816_ADDR = 0x15
REG_GESTURE = 0x01
REG_TOUCH_NUM = 0x02
REG_XH = 0x03
REG_CHIP_ID = 0xA7
REG_MOTION_MASK = 0xEC
REG_IRQ_CTL = 0xFA
REG_DIS_AUTOSLEEP = 0xFE

GESTURE_NONE = 0x00
GESTURE_TAP = 0x05
GESTURE_LONG = 0x0B

IRQ_EN_TOUCH = 0x40      # 手指在屏上期间周期性给中断
IRQ_EN_CHANGE = 0x20     # 坐标变化时给中断

MAX_XY = 360      # 屏幕 360×360，超出即脏数据
MAX_POINTS = 5    # CST816 最多 1 点，放宽到 5 以防固件差异


class CST816:
    def __init__(self, rst=None, int_pin=None):
        self.i2c = cira_i2c.get_i2c()
        self.rst = Pin(rst, Pin.OUT) if rst is not None else None
        self._flag = 0
        self.int = None
        self.chip_id = None
        self.awake = False        # 自动休眠是否已成功关闭
        self._last = {"touched": False, "x": 0, "y": 0, "gesture": 0,
                      "points": 0, "ok": False}
        self.init()
        # INT 中断：空闲高电平，触摸时拉低。用 IRQ 抓（脉冲短，轮询会漏）。
        if int_pin is not None:
            try:
                self.int = Pin(int_pin, Pin.IN, Pin.PULL_UP)
                self.int.irq(trigger=Pin.IRQ_FALLING, handler=self._on_int)
            except Exception:
                self.int = None

    # IRQ 处理器：只置一个小整数标志，不做 I2C、不分配内存
    def _on_int(self, pin):
        self._flag = 1

    def _rd_retry(self, reg, n=1, tries=8):
        for _ in range(tries):
            try:
                self.i2c.writeto(CST816_ADDR, bytes([reg]))
                return self.i2c.readfrom(CST816_ADDR, n)
            except Exception:
                self.i2c = cira_i2c.recover()   # 总线锁死自愈后重试
                time.sleep_ms(2)
        return None

    def _wr_retry(self, reg, val, tries=8):
        for _ in range(tries):
            try:
                self.i2c.writeto(CST816_ADDR, bytes([reg, val]))
                return True
            except Exception:
                self.i2c = cira_i2c.recover()   # 总线锁死自愈后重试
                time.sleep_ms(2)
        return False

    def init(self):
        """硬复位 + 立刻写配置。必须趁芯片刚醒时配，晚了它又睡回去。"""
        if self.rst:
            try:
                self.rst.value(0)
                time.sleep_ms(20)
                self.rst.value(1)
                time.sleep_ms(50)
            except Exception:
                pass
        self.configure()

    def configure(self):
        """写关键寄存器。返回 True = 自动休眠已关闭（I2C 从此稳定）。"""
        cid = self._rd_retry(REG_CHIP_ID)
        self.chip_id = cid[0] if cid else None

        ok = self._wr_retry(REG_DIS_AUTOSLEEP, 0x01)
        self._wr_retry(REG_IRQ_CTL, IRQ_EN_TOUCH | IRQ_EN_CHANGE)
        self._wr_retry(REG_MOTION_MASK, 0x00)

        back = self._rd_retry(REG_DIS_AUTOSLEEP)
        self.awake = bool(ok and back is not None and back[0] == 0x01)
        return self.awake

    def take_edge(self):
        """取走并清零「发生过触摸中断」标志。True = 期间有真实触摸事件。"""
        if self._flag:
            self._flag = 0
            return True
        return False

    def pending_edge(self):
        return self._flag != 0

    def int_low(self):
        if self.int is None:
            return False
        try:
            return self.int.value() == 0
        except Exception:
            return False

    def clear_edge(self):
        self._flag = 0

    def _rd(self, reg, n):
        try:
            self.i2c.writeto(CST816_ADDR, bytes([reg]))
            return self.i2c.readfrom(CST816_ADDR, n)
        except Exception:
            return None

    def scan(self):
        """读当前触摸状态。返回 {"touched","x","y","gesture","points","ok"}。"""
        pts_b = self._rd(REG_TOUCH_NUM, 1)
        xy = self._rd(REG_XH, 4)
        if pts_b is None or xy is None:
            return {"touched": False, "x": self._last["x"], "y": self._last["y"],
                    "gesture": 0, "points": 0, "ok": False}

        points = pts_b[0]
        x = ((xy[0] & 0x0F) << 8) | xy[1]
        y = ((xy[2] & 0x0F) << 8) | xy[3]

        if points > MAX_POINTS or x > MAX_XY or y > MAX_XY:
            return {"touched": False, "x": self._last["x"], "y": self._last["y"],
                    "gesture": 0, "points": 0, "ok": False}

        g = self._rd(REG_GESTURE, 1)
        gesture = g[0] if g else 0
        self._last = {"touched": points > 0, "x": x, "y": y,
                      "gesture": gesture, "points": points, "ok": True}
        return self._last

    def touching(self):
        """当前手指是否在屏上。关掉自动休眠后这是可信的。"""
        s = self.scan()
        if s["ok"]:
            return s["points"] > 0
        return self._last["touched"] and self.int_low()

    def is_touched(self):
        s = self.scan()
        return s["ok"] and s["points"] > 0

    def read_point(self):
        s = self.scan()
        return s["x"], s["y"], (s["points"] if s["ok"] else 0)

    def gesture(self):
        return self.scan()["gesture"]

    def is_tapped(self):
        return self.is_touched()
