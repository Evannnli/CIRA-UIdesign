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
