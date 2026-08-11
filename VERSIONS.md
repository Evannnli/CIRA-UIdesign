# CIRA 版本索引

CIRA 仓库（`CIRA-UIdesign`）管理两类产物，请按类归档：

1. **原型版本** —— Web 原型（设计参考，给人/模型看交互与视觉，不在板子跑）。
2. **实机装机版本** —— 烧进 ESP32-S3 的固件 + 运行时源码（真机跑的）。

---

## 一、原型版本（Web Prototype · 设计参考）

源码即仓库根目录的 `index.html` + `assets/` + `app.js` / `core.js` / `lifeform.js` /
`modules.js` / `language.js` / `styles.css`。这是 CIRA 视觉/交互的「真值来源」，
Device Runtime 的星云数学、控制中心布局都从这里对齐。

| 版本 | 说明 | 位置 |
|------|------|------|
| v0.7 | 当前 Web 原型基线（圆屏 UI、星云柔光、控制中心） | 仓库根：`index.html` 等 |
| 后续 | 原型迭代直接在根目录改，重大变更在此表加一行 | — |

> 原型不单独打 tag；重大里程碑在 `PROJECT_CONTEXT.md` 顶部状态行标注。

---

## 二、实机装机版本（Device Runtime · 真机固件）

固件二进制见 `device-builds/`（每个版本 3 文件：firmware + bootloader + partition-table）。
运行时源码（`.py`）见 `micropython/`。

| 版本 | 日期 | 固件 | 板子入口 | 状态 | 备注 |
|------|------|------|----------|------|------|
| v0.8.7 | 2026-04-06 出厂 | 原厂 Xiaozhi 固件（非 CIRA 自研） | 原厂 `main.py` | 基线/回退点 | 整片备份在 `~/xiaozhi_backup.bin`（16MB，**本地不入库**） |
| 路线 A · LVGL（初版） | 2026-08-11 | `device-builds/cira-lvgl-firmware-2026-08-11.bin` | `:main.py` = `micropython/cira_splash.py` | 已烧录+探针全绿+开机 splash | lv_micropython + 自建 ST77916 QSPI C 驱动；**已知 DMA 异步早释放崩板（已修于 build4）** |
| **路线 A · LVGL（build4·当前）** | **2026-08-11** | `device-builds/cira-lvgl-firmware-2026-08-11b.bin` | `:main.py` = `micropython/cira_splash.py` | **上一已验证实机版本·稳定不崩** | 修 DMA 异步事务+过早释放/覆盖源缓冲→堆损坏静默重启；探针 `tools/minlvgl.py` A→N 全绿 + DONE |
| 路线 A · LVGL（build6·修正构建命令） | 2026-08-11 | `device-builds/cira-lvgl-firmware-2026-08-11c.bin` | `:main.py` = `micropython/cira_splash.py` | 已构建+归档，**待无按键烧录+四色验证** | 同 build4 的 DMA 修复 st77916；**构建命令修正**：`idf.py -DUSER_C_MODULES=<.../micropython.cmake>` 显式传入（build5 误用 env 变量→`st77916.c` 漏编→黑屏，已定位根因）。本地 `tools/qpi_sim.py` 离线验证 QPI 命令流与 ST77916 QSPI 规范一致 |

### 装机版本管理约定
- 每次重新编译/重烧，都在 `device-builds/` 加一组带日期的 `.bin`，并在本表加一行。
- 固件只 frozen `st77916`；其余 `cira_*.py` 走文件系统，**装机须同步推对应源码版本**（见 `device-builds/README.md`）。
- 切换实机版本前，先 `esptool read_flash 0x0 0x1000000 ~/backup_<日期>.bin` 整片备份。

---

## 三、本次提交包含（2026-08-11 路线 A · build4 稳定性修复）

- **修 DMA 异步事务导致的静默崩板**（`micropython/lvgl_build/cira_st77916/st77916.c`）：
  `esp_lcd_panel_io_tx_color` 颜色数据入队即返回、不等 DMA 完成；旧版提前 `free`/覆盖源
  缓冲 → 堆损坏 → 延迟 ISR 崩板 → 看门狗静默重启。新增 `on_color_trans_done` ISR 信号量 +
  `wait_dma_done()` 同步，`blit_dma_safe()` 拷内部 SRAM 后 `esp_cache_msync` 清 D$ 再发。
- `micropython.cmake` 加 `esp_mm/include` 以取到 `esp_cache.h`。
- `st77916_init_data.h` 补 `0x3A 0x55`（COLMOD 65K RGB565），修通电黑屏。
- `cira_lvgl_display.py` flush 兼容 `lv.display_flush_ready` / `disp.flush_ready()` 两种 API 名。
- `device-builds/` 归档 build4 三件套（`*-2026-08-11b.bin`）+ `flash_args-2026-08-11b.txt`，
  烧录命令改为**无按键**（USB-Serial/JTAG 模式 `--before default_reset`）。
- `PROJECT_CONTEXT.md` / `VERSIONS.md` / 记忆同步更新。
