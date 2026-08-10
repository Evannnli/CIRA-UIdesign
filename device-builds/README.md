# CIRA 实机装机版本（固件二进制）

本目录保存**每次不同实机装机版本**的固件二进制，与 `PROJECT_CONTEXT.md` /
`VERSIONS.md` 里的版本号一一对应。每个版本含 3 个文件：

- `cira-lvgl-firmware-<日期>.bin` —— 应用固件（lv_micropython + 自建 ST77916 C 驱动）
- `cira-lvgl-bootloader-<日期>.bin` —— ESP32-S3 bootloader
- `cira-lvgl-partition-table-<日期>.bin` —— 分区表

## 版本：路线 A · LVGL 固件（2026-08-11）

- 对应源码提交：`micropython/`（`cira_lvgl_display.py` / `cira_splash.py` / `cira_st77916` C 模块）
- 探针 `tools/lvgl_hello.py`：L0~L3 全绿（L1 红绿蓝各 ~32ms；L2 出 `CIRA · LVGL`+圆环；L3 ~379 FPS）
- 板子开机入口：`main.py` = `micropython/cira_splash.py`（部署为 `:main.py`），显示持久 splash + 旋转环
- 构建来源：lv_micropython（MicroPython + LVGL 9.6.0 官方绑定）+ `USER_C_MODULE` 自写 ST77916 QSPI 驱动，
  可复现构建见 `micropython/lvgl_build/README.md`

### 烧录命令（macOS，板子进 ROM 下载模式：按住 BOOT → 短按 RESET → 松开 BOOT）

```bash
esptool.py --chip esp32s3 -p /dev/cu.usbmodem101 --before no_reset --after hard_reset \
  write_flash --flash_mode dio --flash_freq 80m --flash_size 8MB \
  0x0     device-builds/cira-lvgl-bootloader-2026-08-11.bin \
  0x8000  device-builds/cira-lvgl-partition-table-2026-08-11.bin \
  0x10000 device-builds/cira-lvgl-firmware-2026-08-11.bin
```

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
