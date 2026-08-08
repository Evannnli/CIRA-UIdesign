# -*- coding: utf-8 -*-
"""
ES8311 音频 DAC 编解码器 MicroPython 驱动
==========================================
移植自 Espressif esp_codec_dev (esp-adf release/v2.x) device/es8311/es8311.c
官方 Waveshare 1.85C-BOX V2 配置：I2S 从机、16-bit、无 MCLK（BCLK 提供时钟）、PA=GPIO15。

init() 内部完整复刻 esp_codec_dev 的调用链：
    es8311_open()  ->  es8311_set_fs(16bit, I2S, 16k)  ->  es8311_start()
注意：官方 bsp 用 32bit（给 AFE 语音识别框架用），此处用 16bit 以直接匹配服务端 ASR 的 16bit WAV。
"""
from machine import I2C, Pin

ES8311_ADDR = 0x18

# ── 寄存器地址（来自 es8311_reg.h）──
REG00 = 0x00  # reset
REG01 = 0x01  # clk mgr: mclk 源 / 使能
REG02 = 0x02  # clk 分频 / 倍频
REG03 = 0x03  # adc fsmode / osr
REG04 = 0x04  # dac osr
REG05 = 0x05  # adc/dac clk 分频
REG06 = 0x06  # bclk 反相 / 分频
REG07 = 0x07  # tri-state / lrck 分频
REG08 = 0x08  # lrck 分频
REG09 = 0x09  # SDPIN (dac 串行口)
REG0A = 0x0A  # SDPOUT (adc 串行口)
REG0B = 0x0B
REG0C = 0x0C
REG0D = 0x0D
REG0E = 0x0E
REG0F = 0x0F
REG10 = 0x10
REG11 = 0x11
REG12 = 0x12  # 使能 DAC
REG13 = 0x13
REG14 = 0x14  # dmic / 模拟 pga
REG15 = 0x15
REG16 = 0x16  # adc
REG17 = 0x17  # adc volume
REG1B = 0x1B
REG1C = 0x1C
REG31 = 0x31  # dac mute
REG32 = 0x32  # dac volume
REG37 = 0x37  # dac ramprate
REG44 = 0x44  # gpio dac2adc
REG45 = 0x45  # gp control


class ES8311:
    def __init__(self, scl, sda, addr=ES8311_ADDR):
        try:
            self.i2c = I2C(0, scl=Pin(scl), sda=Pin(sda), freq=100_000)
        except Exception:
            self.i2c = I2C(0)
        self.addr = addr

    def _wr(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes([val]))

    def _rd(self, reg):
        return self.i2c.readfrom_mem(self.addr, reg, 1)[0]

    def _rmw(self, reg, mask, val):
        r = self._rd(reg)
        r = (r & ~mask) | (val & mask)
        self._wr(reg, r)

    def init(self, vol=0xC0):
        """复刻 esp_codec_dev: open + set_fs(16bit, I2S, 16k) + start"""
        # ── es8311_open ──
        self._wr(REG44, 0x08)
        self._wr(REG44, 0x08)          # 增强 I2C 抗噪，写两次
        self._wr(REG01, 0x30)
        self._wr(REG02, 0x00)
        self._wr(REG03, 0x10)
        self._wr(REG16, 0x24)          # mic gain scale
        self._wr(REG04, 0x10)
        self._wr(REG05, 0x00)
        self._wr(REG0B, 0x00)
        self._wr(REG0C, 0x00)
        self._wr(REG10, 0x1F)
        self._wr(REG11, 0x7F)
        self._wr(REG00, 0x80)          # reset
        self._wr(REG00, 0x80)          # 从机模式（bit6=0）
        self._wr(REG01, 0xBF)          # use_mclk=false -> bit7=1
        self._rmw(REG06, 0x20, 0x00)   # SCLK 不反相
        self._wr(REG13, 0x10)
        self._wr(REG1B, 0x0A)
        self._wr(REG1C, 0x6A)
        self._wr(REG44, 0x58)          # no_dac_ref=false

        # ── es8311_set_fs: 16bit / I2S normal / 16k ──
        # bits per sample = 16 -> REG09/0A bit2-3
        self._rmw(REG09, 0x0C, 0x0C)
        self._rmw(REG0A, 0x0C, 0x0C)
        # fmt = I2S normal -> REG09/0A bit0-1=0
        self._rmw(REG09, 0x03, 0x00)
        self._rmw(REG0A, 0x03, 0x00)
        # config_sample(16000)，use_mclk=false -> pre_multi=8(datmp=3)
        reg = self._rd(REG02)
        self._wr(REG02, (reg & 0x07) | 0x18)
        self._wr(REG05, 0x00)
        self._rmw(REG03, 0x7F, 0x10)
        self._rmw(REG04, 0x7F, 0x10)
        self._rmw(REG07, 0x3F, 0x00)
        self._wr(REG08, 0xFF)
        self._rmw(REG06, 0x1F, 0x03)

        # ── es8311_start (enable) ──
        self._wr(REG00, 0x80)
        self._wr(REG01, 0xBF)
        self._rmw(REG09, 0x40, 0x00)   # DAC 退出掉电（清 bit6）
        self._rmw(REG0A, 0x40, 0x00)   # ADC 退出掉电
        self._wr(REG17, 0xBF)
        self._wr(REG0E, 0x02)
        self._wr(REG12, 0x00)          # 使能 DAC
        self._wr(REG14, 0x1A)
        self._rmw(REG14, 0x40, 0x00)   # digital mic off
        self._wr(REG0D, 0x01)
        self._wr(REG15, 0x40)
        self._wr(REG37, 0x08)
        self._wr(REG45, 0x00)

        # 音量（0x00=最安静 -95.5dB，0xFF=最大 +32dB；0xC0≈0dB）
        self._wr(REG32, vol)

    def set_volume(self, db):
        """db: -95.5~32，0 为 0dB。0x00 最轻、0xFF 最响。"""
        v = 0xFF if db <= -95.5 else max(0, min(0xFF, int((db + 95.5) * 255 / 127.5)))
        self._wr(REG32, v)

    def mute(self, on=True):
        if on:
            self._rmw(REG31, 0x60, 0x60)
        else:
            self._rmw(REG31, 0x60, 0x00)
