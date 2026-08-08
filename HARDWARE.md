# CIRA 硬件信息文档 · ESP32-S3-Touch-LCD-1.85C-BOX

> **文档版本**：v1.0 ｜ 日期：2026-08-08 ｜ 设备目标：**ESP32-S3-Touch-LCD-1.85C-BOX（带音箱 + 外配电池版）**
> **配套**：`MODULE_INTERFACES.md`（模块接口冻结契约）· `HANDOFF.md`（开发交付规格）· `PROJECT_CONTEXT.md`（项目传承）
> **Device Runtime 目标版本**：**`v0.8.0`**（硬件目标基线，本文件锁定的设备；Web 仿真器仍为 `v0.7`，二者是孪生关系：仿真器验证逻辑，固件烧真机）
>
> ⚠️ **本文件可质疑**：所有"待确认/存疑"项见 §11。后续若出现反复 bug，优先回本节核对设备信息，必要时请 Evan 判断（切勿凭直觉替换型号）。

---

## 0. 来源（全部来自 Waveshare 官方）

| 来源 | URL |
|------|-----|
| 产品主页面 | https://www.waveshare.net/wiki/ESP32-S3-Touch-LCD-1.85C |
| Arduino 开发环境 | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/Development-Environment-Setup-Arduino |
| ESP-IDF 开发环境 | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/Development-Environment-Setup-ESPIDF |
| 相关资料（原理图/示例仓库） | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/Resources-And-Documents |
| 小智 AI 应用教程 | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/ESP32-AI-Tutorials |
| 固件烧录与擦除 | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/Firmware-Flashing |
| 产品 FAQ | https://docs.waveshare.net/ESP32-S3-Touch-LCD-1.85C/FAQ |
| **官方示例源码仓库（引脚/驱动权威来源）** | https://github.com/waveshareteam/ESP32-S3-Touch-LCD-1.85C |

> 关键依据：LCD 驱动 IC、各 GPIO 引脚、I2C 地址、I2S 引脚均取自上述**官方示例仓库源码**（`Display_ST77916.*` / `Touch_CST816.*` / `03_audio_out_no_tf.ino`），非凭手册文字猜测。

---

## 1. 设备型号确认（请你先读 §11-1）

- **确切型号**：`ESP32-S3-Touch-LCD-1.85C-BOX`（SKU 30684 / BOX-EN 30685）。
- **"BOX" 含义**：在基础版上**增加 4Ω5W 音箱 + 外配电池结构**。核心板（MCU/PSRAM/屏幕/触摸）与基础版一致，BOX 仅多出喇叭接口实配音箱与电池仓。
- **硬件版本**：你已**明确标识实体板为 V2**（2026-08-08 确认）。该板 V1 已于 2026-01-30 停产，之后出厂为 V2；BOX 固件仍分 V1/V2 两版。本文件**按 V2 编写**，V2 专属项标注「V2」，V1 差异（§10）仅作历史参考，不再作为移植假设。
- 若日后换板为 V1，§10 的差异项会整体生效（音频栈重配），届时回此处核对。

---

## 2. 核心规格总表

| 项 | 规格 | 备注 |
|----|------|------|
| MCU | ESP32-S3R8（Xtensa LX7 双核，最高 240MHz） |  |
| SRAM | 512KB + ROM 384KB |  |
| **PSRAM** | **8MB**（Octal，需 enable） | 星云粒子帧缓冲关键 |
| **Flash** | **16MB** |  |
| 无线 | 2.4GHz Wi-Fi 802.11 b/g/n + Bluetooth 5 (LE) | 板载天线，可切 IPEX 外天线 |
| 屏幕 | 1.85" **圆形 LCD**，360×360，262K 色（RGB565） | **与 Web 原型分辨率 1:1 一致** |
| 显示驱动 | **ST77916**（Waveshare BSP 驱动 `esp_lcd_st77916`） | 见 §3 / §11-2 |
| 触摸 | **CST816T**（I2C），单点 + 手势 | 见 §4 |
| 音频 DAC | **ES8311**（V2，I2C 0x18） | V1 为 PCM5101A |
| 音频 ADC | **ES7210**（V2，双麦带回消） | V1 无 |
| 功放 | **NS4150B**（V2） | V1 为 NS8002 |
| 喇叭 | 4Ω 5W（**仅 BOX 有**） |  |
| 电池 | MX1.25 2-pin，3.7V 锂电，可充放电 + RTC 电池 |  |
| 电源管理 | MP1605GTF-Z（3.3V/2A） | USB-C 5V 输入 |
| GPIO 扩展 | TCA9554PWR（I2C 0x20） | LCD 复位/触摸复位等走扩展器 |
| RTC | PCF85063（I2C 0x51） |  |
| IMU | QMI8658（加速度/陀螺仪，I2C） |  |
| 按键 | RESET、BOOT |  |
| 其它 | Micro SD（SDIO）、UART、I2C 扩展排座 |  |

---

## 3. 屏幕接口协议（LCD · ST77916）

- **接口**：**QSPI（4 数据线 SPI）**，非 RGB 并行、非 8 线 QSPI。官方驱动 `esp_lcd_st77916` 支持 SPI 与 RGB 两种模式，本板用 **SPI/QSPI 模式**。
- **分辨率**：360×360（圆形，实际渲染区为圆内切）。
- **色深**：RGB565（16bit/像素），与 Web 原型一致。
- **SPI 时钟**：最高 80MHz（`ESP_PANEL_LCD_SPI_CLK_HZ=80M`）。
- **背光**：GPIO5，LED_PWM 通道 1，频率 20kHz，分辨率 10bit，占空比 0–100（对应亮度）。**熄屏/SLEEP 即把占空比调 0**（或配合 GPIO 关断）。

### 3.1 LCD 引脚映射（V2，取自 `Display_ST77916.h`）

| 信号 | ESP32 GPIO | 说明 |
|------|-----------|------|
| SCK (SPI clock) | **GPIO40** | `ESP_PANEL_LCD_SPI_IO_SCK` |
| DATA0 (MOSI) | **GPIO46** | `ESP_PANEL_LCD_SPI_IO_DATA0` |
| DATA1 | **GPIO45** | `ESP_PANEL_LCD_SPI_IO_DATA1` |
| DATA2 | **GPIO42** | `ESP_PANEL_LCD_SPI_IO_DATA2` |
| DATA3 | **GPIO41** | `ESP_PANEL_LCD_SPI_IO_DATA3` |
| CS | **GPIO21** | `ESP_PANEL_LCD_SPI_IO_CS` |
| TE（撕裂效应） | **GPIO18** | `ESP_PANEL_LCD_SPI_IO_TE` |
| RST（复位） | **EXIO2（TCA9554 扩展脚，-1 非直连）** | `EXAMPLE_LCD_PIN_NUM_RST=-1` → 经扩展器 |
| 背光 | **GPIO5** | `LCD_Backlight_PIN=5`，PWM |
| SPI Host | SPI2_HOST | mode 0 |
| DC | -1（QSPI 用 data 线发命令，无独立 DC） | `dc_gpio_num=-1` |

> ⚠️ **RST 走扩展器**：LCD 复位不是直连 ESP32 GPIO，而是 TCA9554 的 EXIO2。固件若直接 `gpio_reset` 会失败——必须经由 TCA9554 I2C 写 EXIO2。

---

## 4. 触摸接口协议（Touch · CST816T）

- **控制器**：CST816T（资料页给的是 CST816S 手册，同系列）。
- **总线 / 地址**：I2C，**从机地址 `0x15`**（`CST816_ADDR=0x15`），速率 400kHz。
- **中断**：**GPIO4**（`CST816_INT_PIN=4`），下降沿触发（`FALLING`）。
- **复位**：**EXIO1（TCA9554 扩展脚，-1 非直连）**（`CST816_RST_PIN=-1`）。
- **能力**：**单点触摸**（MAX_POINTS=1，见 §11-5）；支持手势：上/下/左/右滑、单击(0x05)、双击(0x0B)、长按(0x0C)。
- **I2C 总线引脚**：SCL=GPIO10，SDA=GPIO11（与 ES8311 等共用 I2C_NUM_0 总线）。
- **唤醒/SLEEP 退出**：触摸中断 GPIO4 即唤醒源之一（另一为语音唤醒词）。

> 长按进"设置"页：建议用**软件计时**（按下开始计时，≥1.2s 进设置），比依赖 CST816 LONG_PRESS 手势更稳。

---

## 5. 音频接口协议（Audio · ES8311 + ES7210 + NS4150B）

- **Codec（DAC/ADC 一体）**：ES8311（I2C 0x18 = `ES8311_ADDRRES_0`，I2C_NUM_0），负责喇叭输出 + 麦克风输入路由。
- **ADC（V2）**：ES7210，双模拟麦 + 回声消除（AEC），故支持"播放中打断"。
- **功放使能**：**GPIO15**（`PA_CTRL`，高电平使能），播放前 `digitalWrite(15,HIGH)`。
- **喇叭**：4Ω 5W（BOX 专属）。
- **I2S（I2S_NUM_0）引脚（V2，取自 `03_audio_out_no_tf.ino`）**：

| 信号 | ESP32 GPIO | 说明 |
|------|-----------|------|
| MCLK | **GPIO2** | `I2S_MCK_PIN`（V2 改 GPIO2 为 MCLK） |
| BCK（位时钟） | **GPIO48** | `I2S_BCK_PIN` |
| LRCK（帧/字时钟） | **GPIO38** | `I2S_LRCK_PIN` |
| DOUT（发往喇叭） | **GPIO47** | `I2S_DOUT_PIN` |
| DIN（来自麦） | **GPIO39** | `I2S_DIN_PIN` |

- **采样**：示例用 16kHz / 16bit（语音场景）；音乐播放可升至 44.1kHz。
- **V1 差异**：V1 用 PCM5101A（纯 DAC）+ NS8002 + MEMS 数字单麦、**无 ES7210、无回消**，且 I2S 引脚不同（V1 无 GPIO2=MCLK 约定）。**若你的板是 V1，整个音频栈需重配（见 §10）。**

---

## 6. I2C 设备地址映射

| 地址 | 设备 | 依据 |
|------|------|------|
| `0x15` | CST816T 触摸 | 代码 `CST816_ADDR=0x15` |
| `0x18` | ES8311 Codec | 代码 `ES8311_ADDRRES_0`（**未**列入 FAQ 三地址） |
| `0x20` | TCA9554PWR GPIO 扩展器 | FAQ I2C 地址列表推断 |
| `0x51` | PCF85063 RTC | FAQ I2C 地址列表推断 |
| （QMI8658 IMU） | 加速度/陀螺仪 | 示例引用，地址未在本次抓取确认 → 见 §11-4 |

> FAQ 明文："I2C 板载设备占用地址 `0x15, 0x20, 0x51`"。0x15/0x20/0x51 与 CST816/TCA9554/PCF85063 对应；ES8311(0x18) 未在其中，疑为 FAQ 仅列部分或 ES8311 在独立 I2C 实例。

---

## 7. 其它 GPIO / 接口

| 接口 | 引脚 | 说明 |
|------|------|------|
| I2C 总线 | SCL=GPIO10, SDA=GPIO11 | 触摸/Codec/扩展器/RTC/IMU 共用 |
| UART | TX=GPIO43, RX=GPIO44 | 可映射普通 GPIO |
| USB | DN=GPIO19, DP=GPIO20 | 作普通 IO 需每次烧录前进下载模式 |
| 电池电压 ADC | GPIO8（V2 示例 06_AnalogRead） | 分压后 `analogRead(8)`，电压 = 读数×3 |
| 按键 | RESET、BOOT | BOOT 用于下载模式 |
| Micro SD | SDIO（CLK/CMD/D0…） | 示例用 `SD_MMC.setPins(...)` |

---

## 8. 开发环境

### 8.1 Arduino（版本要求）
| 板版本 | esp32 板包 | LVGL | 音频库 | 其它 |
|--------|-----------|------|--------|------|
| V1 | 3.0.2 – 3.1.1 | 8.3.10（离线） | ESP32-audioI2S 2.0.0 | — |
| V2 | 3.2.0 | 9.3.0（离线） | ESP32-audioI2S 2.0.0 | ES7210、ES8311 库（离线） |

- **分区方案**：
  - 含语音识别模型 → `ESP SR 16M (3MB APP / 7MB SPIFFS / 2.9MB MODEL)`
  - 不含模型 → `16M Flash (3MB APP / 9.9MB FATFS)`
- **注意**：LVGL v8 驱动不兼容 v9，必须按表用固定版本。

### 8.2 ESP-IDF
- **要求**：ESP-IDF **≥ V5.5.1**（示例 V5.5.2）；VS Code ESP-IDF 扩展 ≥ 2.0 自动识别。
- **示例工程**：`ESP32-S3-Touch-LCD-1.85C-Test`（V1）/ `ESP32-S3-Touch-LCD-1.85C_V2-Test`（V2）。
- **构建/烧录**：本机 macOS，尚未确认装 ESP-IDF；届时先安装再 `idf.py build / flash`。

---

## 9. 固件烧录（Flash）

- **工具**：乐鑫 Flash Download Tool（或 `esptool` / ESP-IDF `idf.py flash`）。
- **参数**：BAUD = 1152000；烧录地址 **`0x00`**；bin 位于示例仓库 `Firmware/` 目录。
- **进入下载模式**：**长按 BOOT → 按 RESET → 松开 RESET → 松开 BOOT**。若一直"等待上电同步"，重复此序列。
- **macOS 驱动**：需装 CH34XSER_MAC 驱动（FAQ：MAC 烧录失败先装驱动）。
- **恢复出厂**：烧录出厂 bin 即可。

---

## 10. V1 ↔ V2 硬件差异（关键 · 影响移植）

| 项 | V1 | V2（本文件默认） |
|----|----|----------------|
| 音频 DAC | PCM5101APWR | **ES8311** |
| 功放 | NS8002 | **NS4150B** |
| 音频 ADC | 无 | **ES7210** |
| 麦克风 | MEMS 数字单麦 | **模拟双麦 + 回消** |
| GPIO2 | NC/其它 | **I2S_MCLK** |
| GPIO10/11 | 其它 | **I2C SCL/SDA** |
| GPIO15 | 其它 | **PA_CTRL** |
| 出厂时间 | 2026-01-30 前 | 2026-01-30 后 |

> **结论**：若你的板是 V1，本文档 §3/§5 的音频引脚、Codec 型号、I2S 配置需整体替换为 V1 列。

---

## 11. 待确认 / 存疑清单（🚨 请你判断）

> 原则：出现反复 bug 时，优先回此处核对；任何型号/引脚拿不准，停下问 Evan，不要凭直觉替换。

1. **【已确认 V2 · 2026-08-08】你的板是 HW V2。**
   - Evan 明确标识实体板为 V2（外壳/PCB 标签）。故 §3/§5 的 ES8311+ES7210 音频栈、I2S 引脚（GPIO2/15/38/39/47/48）、GPIO10/11=I2C 均为生效配置。
   - V1 差异（§10）仅作历史参考；若日后换 V1 板，再整体切换。
   - 影响回顾：音频方案（ES8311+ES7210 vs PCM5101A）、I2S 引脚、GPIO2/10/11/15 功能——现已按 V2 锁定，错配风险消除。

2. **ST77916 是不是屏幕驱动 IC？**
   - 置信度高：官方示例仓库直接用 `esp_lcd_st77916` 组件，且文件 `Display_ST77916.*` 明确。
   - 但 ST77916 **不是 Sitronix 公开标准型号号**，疑为 Waveshare 定制/BSP 别名。→ 移植时**直接用官方 `esp_lcd_st77916` 驱动组件**，切勿自行换成 GC9A01/ST7789（⚠️ 直觉会猜 GC9A01，那是错的，已在此踩坑预警）。
   - 仍建议 Evan 在屏驱丝印/原理图上核对真实型号。

3. **LCD 复位走 TCA9554 EXIO2、触摸复位走 EXIO1**
   - 代码 `EXAMPLE_LCD_PIN_NUM_RST=-1` / `CST816_RST_PIN=-1` 表明走扩展器。
   - 待确认：**EXIO1/EXIO2 对应 TCA9554 的哪个物理 pin**（扩展器 8 个 IO 的编号映射），以便固件正确操作。

4. **I2C 地址映射推断**
   - 0x15=CST816（代码证实）、0x20=TCA9554、0x51=PCF85063 为推断；ES8311=0x18 未列入 FAQ 三地址。
   - 待确认：TCA9554/PCF85063 实际地址；QMI8658 IMU 的 I2C 地址（本次未抓取确认）。

5. **CST816 仅单点触摸**
   - 代码 `CST816_LCD_TOUCH_MAX_POINTS=1`。→ UI 交互必须限定单点；长按进设置用软件计时。

6. **唤醒退出 SLEEP 的硬件源**
   - 触摸中断 GPIO4（CST816 INT）+ 语音唤醒词（ESP-SR，V2 双麦回消已验证，小智固件支持 BOX V2）。
   - 待模块 1/2（唤醒引擎）接入后实机验证 ESP-SR 在你的板上升唤醒率。

7. **电池电压 ADC = GPIO8**
   - 取自 V2 示例 06_AnalogRead；待确认与你的板一致。

---

## 12. AI 参考固件（重要参考 · 非本项目代码）

- **小智 AI（xiaozhi-esp32）v2.4.2 官方支持 `ESP32-S3-Touch-LCD-1.85C-BOX`**（固件分 V1/V2）。
- 这是**已在该硬件上跑通的端侧 AI 固件**（唤醒词 + ASR + LLM + TTS 一体），可作为模块 1/2（CIRA Core / Language System）的**硬件 I/O 路径参考**——尤其验证 ES8311/ES7210 I2S 音频链路、ST77916 显示、CST816 触摸在本板可用。
- 仓库：https://github.com/waveshareteam/ESP32-AIChats/tree/master/xiaozhi-esp32
- 注意：小智是**另一套架构**（单体固件），本项目是**模块化**（模块1/2 由你团队维护）。仅借其验证硬件通路，不照搬其架构。
- **你此前已烧录过小智固件，现可能已被后续烧录覆盖——这不影响本项目**：小智只是硬件通路验证基准（known-good），非本运行时。仅当某硬件链路（显示/触摸/音频）怀疑有问题时，才需重烧官方小智版本作回灌验证；当前 v0.8.0 不依赖它。

---

## 13. 与模块接口的映射（详见 `MODULE_INTERFACES.md §9`）

| Device Runtime 输入 | 硬件落点 |
|---------------------|----------|
| 状态 `idle/listening/thinking/speaking/settings/sleep/offline` | 星云渲染 → ST77916 帧缓冲；`sleep` → 背光 GPIO5 占空比 0 + 停渲染 |
| 情绪 `emotion` | 星云形态参数（lifeform.js）→ 帧缓冲 |
| 音频 `AudioHandle` | ES8311 I2S 播放（GPIO47 出 / GPIO39 入），PA GPIO15 使能 |
| 唤醒（触摸/语音） | 触摸 INT GPIO4 / ESP-SR；本地应答不进大模型 |
| 亮度 1–400nit | 背光 PWM GPIO5（占空比映射） |

---

## 14. 版本与状态

- **Device Runtime 目标版本：`v0.8.0`**（硬件目标基线，对应本文件锁定的 ESP32-S3-Touch-LCD-1.85C-BOX / **已确认 V2**）。
- Web 仿真器：`v0.7`（桌面浏览器验证孪生）。
- 本文档与 `MODULE_INTERFACES.md` / `PROJECT_CONTEXT.md` 同步维护；硬件信息变更须同步三处。
