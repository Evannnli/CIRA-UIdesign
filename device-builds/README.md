# CIRA 实机装机版本（固件二进制）

本目录保存**每次不同实机装机版本**的固件二进制，与 `PROJECT_CONTEXT.md` /
`VERSIONS.md` 里的版本号一一对应。每个版本含 3 个文件：

- `cira-lvgl-firmware-<日期>.bin` —— 应用固件（lv_micropython + 自建 ST77916 C 驱动）
- `cira-lvgl-bootloader-<日期>.bin` —— ESP32-S3 bootloader
- `cira-lvgl-partition-table-<日期>.bin` —— 分区表

## 版本：路线 A · LVGL 固件（2026-08-11，build4 = 当前实机版本）

- 对应源码提交：`micropython/`（`cira_lvgl_display.py` / `cira_splash.py` / `cira_st77916` C 模块）
- **build4 关键修复（2026-08-11）**：ST77916 像素传输 `esp_lcd_panel_io_tx_color` 是**异步**的（命令走 polling，颜色数据 `spi_device_queue_trans` 入队即返回、不等 DMA 完成）。旧版在 DMA 还在读源缓冲时就 `heap_caps_free`/覆盖 → 堆损坏 → 延迟的 DMA 完成 ISR 在 `sleep` 期间崩板 → 静默看门狗重启（USB 掉=硬复位）。修复：注册 `on_color_trans_done` ISR 回调给二进制信号量，`blit_dma_safe()`/`fill()` 在释放/覆盖源缓冲前 `wait_dma_done()` 等当前这笔 DMA 真正完成；拷到内部 SRAM 后用 `esp_cache_msync` 清 D$。探针 `tools/minlvgl.py` 现跑通 A→N 全绿 + `DONE`，整屏红填充 + LVGL 渲染 `HI` 均不崩。
- 探针 `tools/lvgl_hello.py`：L0~L3 全绿（L1 红绿蓝各 ~32ms；L2 出 `CIRA · LVGL`+圆环；L3 ~379 FPS）
- 板子开机入口：`main.py` = `micropython/cira_splash.py`（部署为 `:main.py`），显示持久 splash + 旋转环
- 构建来源：lv_micropython（MicroPython + LVGL 9.6.0 官方绑定）+ `USER_C_MODULE` 自写 ST77916 QSPI 驱动，
  可复现构建见 `micropython/lvgl_build/README.md`

### 烧录命令（macOS · 默认无按键，板子跑 LVGL 固件时为 USB-Serial/JTAG 模式）

> 板子当前固件是 USB-Serial/JTAG（下载 PID `0x1001`），esptool 可直连软复位，**无需按 BOOT/RESET**。
> 仅当板子处于 TinyUSB 设备模式（PID `0x4001`，esptool 软复位失效）才退回物理键：
> 按住 BOOT → 短按 RESET → 松开 BOOT，再用 `--before no_reset` 烧录。

```bash
# 方式一：用 flash_args（推荐）
esptool.py --chip esp32s3 -p /dev/cu.usbmodem101 -b 460800 \
  --before default_reset --after hard_reset write_flash @device-builds/flash_args-2026-08-11b.txt
# 方式二：显式三件套
esptool.py --chip esp32s3 -p /dev/cu.usbmodem101 -b 460800 \
  --before default_reset --after hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 8MB \
  0x0     device-builds/cira-lvgl-bootloader-2026-08-11b.bin \
  0x8000  device-builds/cira-lvgl-partition-table-2026-08-11b.bin \
  0x10000 device-builds/cira-lvgl-firmware-2026-08-11b.bin
```

### 路线 A · LVGL 固件（build6 = 修正构建命令版，2026-08-11，待烧录验证）

build6 与 build4 固件**功能等价**（同样的 DMA 修复 ST77916），区别仅在**构建命令修正**：
build5 曾用 `idf.py` 直编 + env 变量传 `USER_C_MODULES`（env 变量进不了 CMake）→ `st77916.c`
漏编 → 黑屏；build6 改用 `idf.py -DUSER_C_MODULES=<.../micropython.cmake>` 显式传入，已确认驱动
编进固件（`st77916_blit_obj` / `st77916_fill_obj` 进 `micropython.elf`）。本地 `tools/qpi_sim.py`
离线验证 QPI 命令流与 ST77916 QSPI 规范一致。

```bash
# build6 烧录（推荐，待硬件验证）
esptool.py --chip esp32s3 -p /dev/cu.usbmodem101 -b 460800 \
  --before default_reset --after hard_reset write_flash @device-builds/flash_args-2026-08-11c.txt
# 或显式三件套
esptool.py --chip esp32s3 -p /dev/cu.usbmodem101 -b 460800 \
  --before default_reset --after hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 8MB \
  0x0     device-builds/cira-lvgl-bootloader-2026-08-11c.bin \
  0x8000  device-builds/cira-lvgl-partition-table-2026-08-11c.bin \
  0x10000 device-builds/cira-lvgl-firmware-2026-08-11c.bin
```

> 一键脚本见 `/tmp/flash_and_verify.sh`（烧录 + 软复位 + 推送运行时源码 + 四色验证）。

> ⚠️ 烧录前务必先整片备份原厂固件（见 `PROJECT_CONTEXT.md` 备份段），否则无法回退。
> 烧录后首次启动若卡 `fs_corrupted`，进下载模式 `erase_region 0x310000 0x4F0000` 重建文件系统。

### 装机后推送运行时源码（固件只含 frozen 的 st77916，其余 .py 走文件系统）

```bash
MPREMOTE=mpremote   # 或 ~/.workbuddy/binaries/python/versions/3.13.12/bin/mpremote
$MPREMOTE connect /dev/cu.usbmodem101 fs cp micropython/cira_pins.py      :cira_pins.py
$MPREMOTE connect /dev/cu.usbmodem101 fs cp micropython/cira_i2c.py       :cira_i2c.py
$MPREMOTE connect /dev/cu.usbmodem101 fs cp micropython/cira_expander.py  :cira_expander.py
$MPREMOTE connect /dev/cu.usbmodem101 fs cp micropython/cira_lvgl_display.py :cira_lvgl_display.py
$MPREMOTE connect /dev/cu.usbmodem101 fs cp micropython/cira_splash.py    :main.py
$MPREMOTE connect /dev/cu.usbmodem101 reset
```
