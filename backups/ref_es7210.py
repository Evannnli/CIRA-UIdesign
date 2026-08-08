# -*- coding: utf-8 -*-
"""
ES7210 音频 ADC 编解码器 MicroPython 驱动
==========================================
基于 esphome es7210 组件（真实跑在 Waveshare ESP32-S3-Touch-LCD 等板上的
验证序列）移植。官方 Waveshare 1.85C-BOX V2：I2S 从机、16-bit、
双麦(MIC1+MIC2 经 SDOUT1 输出)、外部 MCLK(由 mclk 模块用 PWM 在 GPIO2 造 4.096MHz)。

注意：MCLK 必须由外部提供且持续输出（见 audio_in.record_wav 里的 enable_mclk），
否则 ES7210 的 ADC 不工作。本驱动只负责 I2C 寄存器配置。

寄存器序列严格对齐 esphome（16k / 4.096MHz MCLK 系数表项）：
    adc_div=0x01, doubler=1, dll=1, osr=0x20, lrck_h=0x01, lrck_l=0x00

⚠️ I2C 健壮性（2026-08-06 补）：ES7210 与 CST816 / ES8311 / RTC / TCA9554 共用
I2C0（GPIO10/11）。软复位 / 频繁推文件后这条总线偶发卡顿，单条 writeto_mem 会
ETIMEDOUT 或被静默吞掉 → 增益/供电寄存器没写进去 → 录音在「30dB 正常」与
「默认高增益爆音 / 低增益静音」之间跳变（实测 peak 在 124 与 32767 间交替）。
故所有写都加重试，关键寄存器（增益/供电/时钟/格式）写后回读校验，必要时总线恢复。
"""
import time
from machine import I2C, Pin

ES7210_ADDR = 0x40

REG00 = 0x00  # reset
REG01 = 0x01  # clock off
REG02 = 0x02  # main clk div
REG03 = 0x03  # master clk src/div
REG04 = 0x04  # lrck div h
REG05 = 0x05  # lrck div l
REG06 = 0x06  # power down
REG07 = 0x07  # osr
REG08 = 0x08  # mode config (master/slave)
REG09 = 0x09  # time control0
REG0A = 0x0A  # time control1
REG11 = 0x11  # sdp interface1 (fmt/bits)
REG12 = 0x12  # sdp interface2 (tdm)
REG20 = 0x20  # adc34 hpf2
REG21 = 0x21  # adc34 hpf1
REG22 = 0x22  # adc12 hpf1
REG23 = 0x23  # adc12 hpf2
REG40 = 0x40  # analog power
REG41 = 0x41  # mic12 bias
REG42 = 0x42  # mic34 bias
REG43 = 0x43  # mic1 gain
REG44 = 0x44  # mic2 gain
REG45 = 0x45  # mic3 gain
REG46 = 0x46  # mic4 gain
REG47 = 0x47  # mic1 power
REG48 = 0x48  # mic2 power
REG49 = 0x49  # mic3 power
REG4A = 0x4A  # mic4 power
REG4B = 0x4B  # mic12 power (bias+ADC+PGA)
REG4C = 0x4C  # mic34 power (bias+ADC+PGA)

MIC1 = 0x01
MIC2 = 0x02
MIC3 = 0x04
MIC4 = 0x08

# 增益寄存器低 4 位的编码：dB = value * 3（esphome: gain/3，0..15 → 0..45dB）
# 30dB(0x0A) 在近距离正常说话时偶发削波（peak 32768 → ASR 收垃圾）；降到 27dB(0x09)
# 留 3dB 余量防爆音，偏轻的录音由服务端 AGC 拉起来。
GAIN_30DB = 0x09  # 27/3 = 9


class ES7210:
    def __init__(self, scl, sda, addr=ES7210_ADDR):
        self._bus_recover(scl, sda)   # 先释放可能被某设备拉低的 SDA（共享总线）
        try:
            self.i2c = I2C(0, scl=Pin(scl), sda=Pin(sda), freq=100_000)
        except Exception:
            self.i2c = I2C(0)
        self.addr = addr
        self.mic_select = MIC1 | MIC2   # 板子是双麦，选 1+2（SDOUT1 输出 L=MIC1,R=MIC2）

    @staticmethod
    def _bus_recover(scl, sda):
        """释放被某设备拉低的 SDA：手动在 SCL 上补 9 个时钟脉冲（I2C 总线恢复）。
        软复位多次后总线易卡死，此步可免硬拔插自愈。"""
        try:
            sda_p = Pin(sda, Pin.OUT, value=1)
            scl_p = Pin(scl, Pin.OUT, value=1)
            time.sleep_ms(2)
            for _ in range(9):
                scl_p.value(0); time.sleep_us(5)
                scl_p.value(1); time.sleep_us(5)
            sda_p.value(0); time.sleep_us(5)
            sda_p.value(1); time.sleep_us(5)
        except Exception:
            pass

    def _wr(self, reg, val, tries=5):
        """带重试的 I2C 写，规避软复位后总线瞬态 ETIMEDOUT（ESP32 I2C 常见）。
        返回是否成功；失败不再抛出，交给上层 / 校验逻辑决定要不要总线恢复。"""
        if isinstance(val, (bytes, bytearray)):
            val = val[0]
        b = bytes([val & 0xFF])
        for _ in range(tries):
            try:
                self.i2c.writeto_mem(self.addr, reg, b)
                return True
            except OSError:
                time.sleep_ms(10)
        return False

    def _rd(self, reg, tries=3):
        for _ in range(tries):
            try:
                return self.i2c.readfrom_mem(self.addr, reg, 1)[0]
            except OSError:
                time.sleep_ms(10)
        return None

    def _rmw(self, reg, mask, val):
        r = self._rd(reg)
        if r is None:
            r = 0
        r = (r & ~mask) | (val & mask)
        self._wr(reg, r)
        return r

    def _wr_verify(self, reg, val, tries=6):
        """写并回读校验：增益/供电这类关键寄存器偶发写不进，回读不符就重试，
        最后手段做一次总线恢复再强写。返回是否一致。"""
        val &= 0xFF
        for _ in range(tries):
            if self._wr(reg, val):
                r = self._rd(reg)
                if r is not None and r == val:
                    return True
            time.sleep_ms(5)
        self._bus_recover()
        self._wr(reg, val)
        return self._rd(reg) == val

    def _mic_select(self, gain=GAIN_30DB):
        """按 esphome configure_mic_gain_ 配置各通道增益+选择。
        注意：此函数会把 REG4B/REG4C 临时设成 0x00，必须在 init() 收尾处
        再写回 0x0F（组电源：偏置+ADC+PGA 全开）。增益用 _wr_verify 确保落进去。"""
        for i in range(4):
            self._rmw(REG43 + i, 0x10, 0x00)
        self._wr(REG4B, 0xFF)
        self._wr(REG4C, 0xFF)
        if self.mic_select & MIC1:
            self._rmw(REG01, 0x0B, 0x00)
            self._wr(REG4B, 0x00)
            self._wr_verify(REG43, 0x10 | (gain & 0x0F))
        if self.mic_select & MIC2:
            self._rmw(REG01, 0x0B, 0x00)
            self._wr(REG4B, 0x00)
            self._wr_verify(REG44, 0x10 | (gain & 0x0F))
        if self.mic_select & MIC3:
            self._rmw(REG01, 0x0B, 0x00)
            self._wr(REG4C, 0x00)
            self._wr_verify(REG45, 0x10 | (gain & 0x0F))
        if self.mic_select & MIC4:
            self._rmw(REG01, 0x0B, 0x00)
            self._wr(REG4C, 0x00)
            self._wr_verify(REG46, 0x10 | (gain & 0x0F))
        # TDM 仅当选中 ≥3 个 mic 才开
        if bin(self.mic_select).count("1") >= 3:
            self._wr(REG12, 0x02)
        else:
            self._wr(REG12, 0x00)

    def init(self):
        """复刻 esphome ES7210::setup()（16k / 16bit / I2S / 从机 / 外部 MCLK）。"""
        # ── 软件复位 ──
        self._wr(REG00, 0xFF)
        time.sleep_ms(10)
        self._wr(REG00, 0x32)

        # ── 时隙 / 初始化延时 ──
        self._wr(REG01, 0x3F)
        self._wr(REG09, 0x30)
        self._wr(REG0A, 0x30)

        # ── 各 ADC 高通滤波 ──
        self._wr(REG23, 0x2A)
        self._wr(REG22, 0x0A)
        self._wr(REG20, 0x0A)
        self._wr(REG21, 0x2A)

        # ── 从机模式（清 bit0）──
        self._rmw(REG08, 0x01, 0x00)

        # ── 模拟电源 ──
        self._wr(REG40, 0xC3)

        # ── MIC 偏置 2.87V（BIT0=使能，0x70 为官方正确值）──
        self._wr(REG41, 0x70)
        self._wr(REG42, 0x70)

        # ── I2S 格式：16-bit / I2S 标准 / 非 TDM ──
        self._rmw(REG11, 0xE0, 0x60)   # bits = 16
        self._rmw(REG11, 0x03, 0x00)   # fmt = I2S normal
        self._wr(REG12, 0x00)

        # ── 采样率 16k（MCLK=4.096MHz，系数表项）──
        # adc_div=0x01, doubler=1<<6, dll=1<<7 → REG02=0xC1
        self._wr(REG02, 0xC1)
        self._wr(REG07, 0x20)
        self._wr(REG04, 0x01)          # ← 关键：LRCK 分频高字节（之前漏写）
        self._wr(REG05, 0x00)          # ← 关键：LRCK 分频低字节（之前漏写）

        # ── 麦克风增益 + 通道选择 ──
        # 注意：此步会把 REG4B/REG4C 临时置 0x00，下面收尾会改回 0x0F
        self._mic_select(GAIN_30DB)

        # ── 逐个 mic 上电 ──
        self._wr(REG47, 0x08)
        self._wr(REG48, 0x08)
        self._wr(REG49, 0x08)
        self._wr(REG4A, 0x08)

        # ── 关 DLL（外部 MCLK + 从机模式，DLL 不需要）──
        self._wr(REG06, 0x04)

        # ── 组电源：MIC 偏置 + ADC + PGA 全开 ← 之前写成 0x00 全关（致命）──
        self._wr(REG4B, 0x0F)
        self._wr(REG4C, 0x0F)

        # ── 使能芯片 ──
        self._wr(REG00, 0x71)
        self._wr(REG00, 0x41)

        # ── 关键寄存器写后回读校验（共享 I2C 总线偶发丢写 → 录音削波/静音）──
        # 时钟决定采样率正确与否；模拟电源/偏置/供电/增益决定电平。
        # 只校验「读回归一」的配置寄存器（REG11 格式位、REG00 控制位读回不一定等于写入）。
        for reg, val in (
            (REG02, 0xC1), (REG04, 0x01), (REG05, 0x00), (REG06, 0x04),
            (REG40, 0xC3), (REG41, 0x70), (REG42, 0x70),
            (REG43, 0x10 | GAIN_30DB), (REG44, 0x10 | GAIN_30DB),
            (REG4B, 0x0F), (REG4C, 0x0F),
        ):
            self._wr_verify(reg, val)

    def set_gain(self, db=30):
        g = max(0, min(0x0F, int(db / 3)))
        for i in range(4):
            if self.mic_select & (1 << i):
                self._rmw(REG43 + i, 0x0F, g)
