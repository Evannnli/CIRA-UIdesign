# -*- coding: utf-8 -*-
"""
CST816 电容触摸驱动（ESP32-S3 · MicroPython）
============================================
微雪 1.85C-BOX 板载 CST816（I2C 7-bit 地址 0x15，SCL=GPIO10 / SDA=GPIO11，INT=GPIO4）。
实测 ChipID=0xB5 → CST816**T**（0xB4=816S / 0xB6=816D）。

⚠️⚠️ 2026-08-07 重大修正：推翻「I2C 不可信、只能靠 INT」的旧结论 ⚠️⚠️
------------------------------------------------------------------
旧驱动不写任何配置寄存器，于是芯片一直处于**自动休眠**状态：
    · 静置 3 秒轮询 → I2C 失败率 56~78%（休眠中根本不 ACK）
    · 偶尔读通还会吐 points=64 / 坐标(3,173) 这类垃圾值
    · 手指按住不动时不再产生新中断，INT 也不保持低电平
        → 长按期间「确认手指还在」的手段全部失效
        → 350ms 后被判成松手，held≈0 → **长按每次都退化成短按**
          （现象：想进控制中心，结果直接进了"我在听"）

真正的根因是「没关自动休眠」，不是芯片不可靠。实测对照：
    写 0xFE(DisAutoSleep)=0x01 之后 →
        单次读 148 次全成功，**I2C 失败率 0%**，静置期间脏数据 0 帧。

所以本驱动：
  1) 复位后立刻带重试地写配置（休眠时头几个 I2C 事务会被丢弃，重试即唤醒）：
        0xFE DisAutoSleep = 1   关自动休眠 ← 决定性的一条
        0xFA IrqCtl       = 0x60 (EnTouch|EnChange) 手指在屏上就持续给中断
        0xEC MotionMask   = 0    不要手势中断，避免和长按判定打架
  2) `touching()` 直接轮询 points —— 现在它是可信的，这是判定长按的主依据。
  3) INT 边沿仍然保留（`take_edge()`），用于休眠态零功耗唤醒和快速响应，
     但**不再是唯一依据**，两者互为补充。
  4) 保留脏数据校验（points 1..5、坐标 0..360）作为兜底。

寄存器映射：
    0x01 手势ID  0x02 触点数  0x03/0x04 X高/低  0x05/0x06 Y高/低（各取低 12 位）
    0xA7 ChipID  0xEC MotionMask  0xFA IrqCtl  0xFE DisAutoSleep
"""

from machine import I2C, Pin
import time

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
MAX_POINTS = 5    # CST816 最多 1 点，放宽到 5 以防固件差异；64 这类必然是脏数据


class CST816:
    def __init__(self, scl, sda, rst=None, int_pin=None):
        self.i2c = I2C(0, scl=Pin(scl), sda=Pin(sda), freq=400000)
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

    # ── 带重试的 I2C（休眠中头几个事务会被丢弃，重试即唤醒）──────
    def _rd_retry(self, reg, n=1, tries=6):
        for _ in range(tries):
            try:
                self.i2c.writeto(CST816_ADDR, bytes([reg]))
                return self.i2c.readfrom(CST816_ADDR, n)
            except Exception:
                time.sleep_ms(2)
        return None

    def _wr_retry(self, reg, val, tries=6):
        for _ in range(tries):
            try:
                self.i2c.writeto(CST816_ADDR, bytes([reg, val]))
                return True
            except Exception:
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

        # 回读确认：只有确实写进去了才敢信任 I2C 轮询
        back = self._rd_retry(REG_DIS_AUTOSLEEP)
        self.awake = bool(ok and back is not None and back[0] == 0x01)
        return self.awake

    # ── 中断标志 ──────────────────────────────────────────────
    def take_edge(self):
        """取走并清零「发生过触摸中断」标志。True = 期间有真实触摸事件。"""
        if self._flag:
            self._flag = 0
            return True
        return False

    def pending_edge(self):
        """只看不取：期间是否发生过触摸中断。

        给「可打断的长任务」用（比如唤醒监听录音）：中途想知道孩子有没有伸手，
        但**不能把边沿吃掉**，否则任务返回后外层再 take_edge() 就漏掉这次点按了。
        """
        return self._flag != 0

    def int_low(self):
        """当前 INT 电平是否为低（配了 EnTouch 后按住期间会周期性拉低）。"""
        if self.int is None:
            return False
        try:
            return self.int.value() == 0
        except Exception:
            return False

    def clear_edge(self):
        self._flag = 0

    # ── I2C 读取 ──────────────────────────────────────────────
    def _rd(self, reg, n):
        try:
            self.i2c.writeto(CST816_ADDR, bytes([reg]))
            return self.i2c.readfrom(CST816_ADDR, n)
        except Exception:
            return None

    def scan(self):
        """读当前触摸状态。

        返回 {"touched","x","y","gesture","points","ok"}；
        ok=False 表示这一帧【不可信】（I2C 没读通 或 读到脏数据）。
        关掉自动休眠后 ok=False 已是极少数情况。
        """
        pts_b = self._rd(REG_TOUCH_NUM, 1)
        xy = self._rd(REG_XH, 4)
        if pts_b is None or xy is None:
            return {"touched": False, "x": self._last["x"], "y": self._last["y"],
                    "gesture": 0, "points": 0, "ok": False}

        points = pts_b[0]
        x = ((xy[0] & 0x0F) << 8) | xy[1]
        y = ((xy[2] & 0x0F) << 8) | xy[3]

        # 合法性校验：过滤 points=64 这类脏数据与越界坐标
        if points > MAX_POINTS or x > MAX_XY or y > MAX_XY:
            return {"touched": False, "x": self._last["x"], "y": self._last["y"],
                    "gesture": 0, "points": 0, "ok": False}

        g = self._rd(REG_GESTURE, 1)
        gesture = g[0] if g else 0
        self._last = {"touched": points > 0, "x": x, "y": y,
                      "gesture": gesture, "points": points, "ok": True}
        return self._last

    def touching(self):
        """当前手指是否在屏上。关掉自动休眠后这是【可信】的，长按判定就靠它。

        读不通时（极少）退回上一帧的 touched，避免一次偶发失败就误判成松手。
        """
        s = self.scan()
        if s["ok"]:
            return s["points"] > 0
        return self._last["touched"] and self.int_low()

    def is_touched(self):
        s = self.scan()
        return s["ok"] and s["points"] > 0

    def read_point(self):
        """返回 (x, y, points)；不可信帧返回 points=0。"""
        s = self.scan()
        return s["x"], s["y"], (s["points"] if s["ok"] else 0)

    def gesture(self):
        return self.scan()["gesture"]

    def is_tapped(self):
        return self.is_touched()
