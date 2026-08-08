# cira_pins.py — 微雪 ESP32-S3-Touch-LCD-1.85C-BOX V2 引脚与音频参数
# 来源: 板子内 config.py (权威)，对照 waveshare 官方 wiki / bsp_board.c
SAMPLE_RATE = 16000          # 16kHz 固定（与服务端 ASR/TTS 一致）
I2S_BITS = 16
VOLUME_DB = -25.0            # ES8311 音量（约 -95.5 最轻 ~ 0 最大）

# I2C 共享总线（ES8311 / CST816 / RTC 都在 GPIO10/11, I2C0）
I2C_SCL = 10
I2C_SDA = 11

# ES8311 播放（I2S1）
ES8311_I2S_ID = 1
ES8311_BCK = 48             # V2: I2S_BCK = GPIO48
ES8311_WS  = 38             # V2: I2S_LRCK = GPIO38
ES8311_SDO = 47             # V2: I2S_DIN = GPIO47 (ESP32 -> ES8311, I2S.TX 的 sd)
ES8311_SDI = 39             # V2: MIC_SD = GPIO39 (ES7210 -> ESP32, I2S.RX)
ES8311_MCLK = 2             # V2: I2S_MCLK = GPIO2（PWM 4.096MHz）
ES8311_ADDR = 0x18
ES8311_PA_CTRL = 15         # V2: 功放使能 PA_CTRL（拉高才出声！）

# 触摸 CST816（I2C0）
TOUCH_ADDR = 0x15
TOUCH_INT = 4
TOUCH_RST = 1              # V2: RST 走 GPIO1（原厂 config.TOUCH_RST），驱动内做复位脉冲

# ── 屏幕 ST77916 圆形 TFT（QSPI，360×360）──────────────────
# 来源：ref_config.py（waveshare 官方 wiki 引脚差异表核对）。
# ⚠️ ST77916 在 1.85C-BOX 上是 QSPI（4 数据线、无独立 DC 脚），
#    由固件 frozen 模块 st77916.ST77916 用硬件 QSPI 驱动（自带 _blit_kernel）。
#    LCD_RST 实际走 TCA9554 EXIO2（I2C 0x20），故开机须先 cira_expander.init()
#    把所有 EXIO 设成输出高，才能释放 LCD 复位（frozen 驱动的 rst= 仅占位）。
LCD_W = 360
LCD_H = 360
LCD_CS = 21
LCD_PCLK = 40
LCD_D0 = 46
LCD_D1 = 45
LCD_D2 = 42
LCD_D3 = 41
LCD_RST = 3               # 占位；真复位走 TCA9554 EXIO2
LCD_BL = 5                # 背光（frozen 驱动内 PWM 调光 set_nit）
LCD_MADCTL = 0x00         # 方向/镜像；脸横过来改 0x60/0xA0/0xC0
LCD_INVERT = False        # 颜色发白/左右反了改 True（开 INVON）
