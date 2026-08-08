# -*- coding: utf-8 -*-
"""
CIRA 设备端配置（ESP32-S3 · MicroPython）
==========================================

当前默认 = 微雪 ESP32-S3-Touch-LCD-1.85C-BOX（带音响 + 电池版，Evan 2026-08-03 换购）

⚠️ 引脚以板子官方 wiki / 官方例程为准！下方 LCD/I2S 引脚已对照
   waveshare 官方仓库 ESP32-S3-Touch-LCD-1.85C 的 01_lvgl_example 与 bsp_board.c 核对。
   音频（ES8311/ES7210 的 I2S 引脚）和 LCD（QSPI 引脚）均已实测验证可用。

─── 官方 wiki 确认的完整参数 ───
  · 主控：ESP32-S3R8 (Xtensa LX7 双核) · 8MB PSRAM · 16MB Flash
  · 屏幕：1.85" 圆形 TFT LCD · 360×360 · 262K 色 · ST77916 驱动(QSPI) · CST816 电容触摸(I2C)
  · 麦克风：双 MEMS 麦克风 + ES7210 回声消除
  · 音频：ES8311 编解码器 + 4Ω 5W 腔体音箱（"带音响版"）
  · 无线：Wi-Fi 2.4G + BLE 5 · 板载天线 · Type-C
  · RTC：PCF85063（I2C，可掉电走 RTC 电池保持时间）
  · 扩展：Micro SD 卡槽 · TCA9554 GPIO 扩展 · RESET/BOOT 按键
  · 电池：MX1.25 3.7V 锂电接口（充放电管理）
  · ❌ 无六轴 IMU（做不到摇一摇；只有 1.85B / 1.83 版本才带）
"""

# ── 网络 ───────────────────────────────────────────────
# ⚠️ Wi-Fi 不再写死在这里！板子启动自动读 net_config.json 连网；
#    连不上会自己开热点 CIRA-Setup，手机连上浏览器开 192.168.4.1 填新网络。
#    换 Wi-Fi 环境 = 开机长按 BOOT 键 5 秒，或断网后自动进配网，全程无需 PC。
#    下面 WIFI_SSID/PASS 仅作首次调试的兜底默认值，正常不应修改。
WIFI_SSID = "你的WiFi名"
WIFI_PASS = "你的WiFi密码"

# 服务端地址：板子配网时填（电脑运行 `python engine/server.py` 后终端打印的局域网地址）。
# 配网成功后存在 net_config.json 里，运行时覆盖此项。
SERVER_URL = "http://192.168.1.100:8787"

# ── 音频参数（与服务端 ASR / TTS 必须一致）─────────────────
SAMPLE_RATE = 16000          # 16kHz，固定
RECORD_SECONDS = 4           # 一次录多长（秒）。短一点延迟低、省内存。
I2S_BITS = 16                # 16-bit PCM

# ── 休眠与语音唤醒 ───────────────────────────────────────
# 待机无任何交互超过这么久 → 熄屏休眠（省电大头是背光）。休眠时耳朵仍然醒着。
IDLE_SLEEP_MS = 10000        # 10 秒
# 休眠期的唤醒词监听：录一小段 → 本地能量门限 → /api/asr（不进大模型）→ 关键词匹配
WAKE_VOICE = True            # 关掉则只能点按唤醒
WAKE_WINDOW_SEC = 1.5        # 每段监听录多长（秒）；太短会把"你好CIRA"切断
WAKE_VAD_LEVEL = 200         # 平均绝对幅度门限，低于它视为没人说话，直接不联网
                             # （常开功放底噪实测 ≈40，正常说话 ≈500~3000）
# 注：亮屏待机期【不】做语音监听——那 10 秒里录音会占住 CPU 让触摸变迟钝，
#     而且马上就要熄屏了。熄屏之后才把耳朵打开。

# ── 屏幕类型 ─────────────────────────────────────────────
# "round"  = 圆形 TFT LCD（微雪 1.85C-BOX，ST77916 驱动，360×360，已点亮）
# "oled"   = 0.96" SSD1306 OLED（I2C），最便宜
# "none"   = 暂时跳过屏幕，只测 WiFi/音频
DISPLAY_TYPE = "round"

# ── 扬声器路径 ──────────────────────────────────────────
# "es8311"   = 板载 ES8311 编解码器 → 4Ω 5W 腔体音箱（1.85C-BOX 默认，无需焊接）
# "external" = 外接 I2S 功放芯片（如 MAX98357A），需填 AMP_* 引脚
SPEAKER_PATH = "es8311"

# ── 微雪 1.85C-BOX V2 引脚（2026-01-30 后出货，ES8311+ES7210+双麦）──
# 来源：https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C （官方 wiki 引脚差异表）
#
# ⚠️ V1→V2 引脚变化很大！特别是：
#   GPIO10/11 从无功能 → I2C(SCL/SDA)
#   GPIO15     从 MIC_SCK → 功放使能(PA_CTRL)，必须拉高才能出声
#   GPIO2      从 MIC_WS  → I2S_MCLK
#   音频芯片    PCM5101A  → ES8311（支持回声消除）
#   麦克风     单MEMS    → 双MEMS + ES7210

# 圆形 TFT LCD（ST77916 驱动，QSPI 接口）—— V1/V2 相同
# ⚠️ ST77916 在 1.85C-BOX 上是 QSPI（4 数据线、无独立 DC 脚），MicroPython 无现成驱动，
#    由 st77916.py 用纯 GPIO 位模拟（见该文件头部协议说明）。
#    引脚来源：waveshare 官方 01_lvgl_example/Display_ST77916.h（实测点亮验证）。
# ⚠️ LCD_RST 实际走 TCA9554 扩展芯片的 EXIO2（I2C 0x20），不由 GPIO3 直控——
#    故本驱动用 TCA9554 复位 LCD；config.LCD_RST 仅作占位，驱动内 use_tca=True 时忽略它。
LCD_CS   = 21
LCD_PCLK = 40
LCD_D0   = 46
LCD_D1   = 45
LCD_D2   = 42
LCD_D3   = 41
LCD_RST  = 3   # 占位；真复位走 TCA9554 EXIO2
LCD_BL   = 5
LCD_W = 360                # ← 1.85C-BOX 实际分辨率 360×360
LCD_H = 360
LCD_MADCTL = 0x00          # ST77916 MADCTL 方向/镜像；若脸横过来/镜像了改 0x60/0xA0/0xC0
LCD_INVERT = False         # 颜色发白或左右相反时改 True（开 INVON）

# 触摸屏 CST816（I2C，可选；7-bit 地址 0x15）
TOUCH_SCL = 10             # V2: GPIO10 = I2C SCL
TOUCH_SDA = 11             # V2: GPIO11 = I2C SDA
TOUCH_RST = 1
TOUCH_INT = 4

# RTC 时钟 PCF85063（I2C，7-bit 地址 0x51）
RTC_SCL = 10               # 与触摸共用 I2C 总线
RTC_SDA = 11

# 音频编解码 ES8311（I2S 输出 → 4Ω 5W 腔体音箱）
# V2 引脚来自官方 wiki 引脚差异表 + Waveshare 官方 ESP-IDF 示例（bsp_board.c 确认用 I2S1）
ES8311_I2S_ID = 1          # ⚠️ 官方示例用 I2S_NUM_1（不是 I2S0！）
ES8311_BCK = 48            # V2: I2S_BCK = GPIO48
ES8311_WS  = 38            # V2: I2S_LRCK = GPIO38
ES8311_SDO = 47            # V2: I2S_DIN = GPIO47（播放：ESP32 数据 → ES8311，I2S.TX 的 sd 脚）
ES8311_SDI = 39            # V2: MIC_SD = GPIO39（录音：ES7210 → ESP32，I2S.RX 的 sd 脚）
ES8311_MCLK = 2            # V2: I2S_MCLK = GPIO2
# ⚠️⚠️ MCLK 必须驱动！实测：不给 MCLK 时 ES7210 读出恒定全 0（4 种位宽/声道组合都是 0），
#      给 4.096MHz 立刻出连续音频波形。官方 bsp 的 use_mclk=false 只是说 codec 驱动不去改
#      MCLK 分频寄存器，I2S 外设照样在 GPIO2 输出 MCLK——别被这个标志误导。
#      MicroPython legacy I2S 无 mck= 参数，故用 PWM 产生（见 mclk.py）。
ES8311_I2C_SCL = 10        # ES8311 通过 I2C 配置（与触摸/RTC 共用总线）
ES8311_I2C_SDA = 11
ES8311_PA_CTRL = 15        # V2: 功放使能 PA_CTRL（⚠️ 播放前必须设 HIGH 才能出声！）

# 麦克风 ES7210（I2S RX，双麦回声消除）
# V2 新增芯片，与 ES8311 共用 I2S 总线的 BCK/WS，仅数据线分开
ES7210_I2S_ID = 1          # ⚠️ 官方示例用 I2S_NUM_1（录音与播放共用 I2S1）
ES7210_BCK = 48            # 共用 BCK
ES7210_WS  = 38            # 共用 LRCK/WS
ES7210_SD  = 39            # V2: MIC_SD = GPIO39（ES7210 数据 → ESP32，I2S.RX 的 sd 脚）
ES7210_MCLK = 2            # 共用 MCLK（不驱动）
ES7210_I2C_SCL = 10
ES7210_I2C_SDA = 11

# ── 自搭版引脚（仅 SPEAKER_PATH="external" 时需要）────────────
AMP_SCK  = 26
AMP_WS   = 25
AMP_DIN  = 22
AMP_I2S_ID = 1

OLED_SCL = 9
OLED_SDA = 8
OLED_W   = 128
OLED_H   = 64

MIC_SCK  = 14
MIC_WS   = 15
MIC_SD   = 13

# 说话键（可选）：可外接一个按钮到 GPIO0；长按录音、松手发送
BUTTON_PIN = 0

# 默认音量（dB，ES8311：约 -95.5 最轻 ~ 0 最大，0 即满音量）。触摸滑杆在 [-60, 0] 间调节。
# 注：codec 只在启动 init 一次（反复 init 会爆音）；play_begin 每轮开播前会显式
#     set_volume(VOLUME_DB)，所以改这里下一轮播放即生效。
VOLUME_DB = -25.0

"""
═══ 当前激活配置：微雪 ESP32-S3-Touch-LCD-1.85C-BOX（带音响+电池）═══
  - DISPLAY_TYPE = "round"
  - SPEAKER_PATH = "es8311"（4Ω 5W 腔体音箱，无需焊接）
  - 屏幕：1.85" 圆形 TFT LCD · 360×360 · ST77916 驱动 · 262K 色
  - 麦克风：双 MEMS + ES7210 回声消除（板载）
  - 音频编解码：ES8311（板载）
  - 触摸：CST816（板载，预留交互扩展）
  - RTC：PCF85063（板载，可驱动"早安/晚安"等时间感知交互）
  - ❌ 无 IMU，不支持摇一摇

═══ 备选：自搭最低成本（ESP32-S3-DevKitC ¥35 + 零件 ≈ ¥100）═══
  - DISPLAY_TYPE = "oled"
  - SPEAKER_PATH = "external"
  - 引脚用 MIC_*/AMP_*/OLED_* 的默认值，照着接杜邦线即可。
"""
