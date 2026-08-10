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
| **路线 A · LVGL** | **2026-08-11** | `device-builds/cira-lvgl-firmware-2026-08-11.bin` | `:main.py` = `micropython/cira_splash.py` | **已烧录+探针全绿+开机 splash** | lv_micropython + 自建 ST77916 QSPI C 驱动；探针 L0~L3 全绿 |

### 装机版本管理约定
- 每次重新编译/重烧，都在 `device-builds/` 加一组带日期的 `.bin`，并在本表加一行。
- 固件只 frozen `st77916`；其余 `cira_*.py` 走文件系统，**装机须同步推对应源码版本**（见 `device-builds/README.md`）。
- 切换实机版本前，先 `esptool read_flash 0x0 0x1000000 ~/backup_<日期>.bin` 整片备份。

---

## 三、本次提交包含（2026-08-11 路线 A 验证）

- 修通 LVGL 9.6.0 三处运行时 API 坑（`cira_lvgl_display.py`）：颜色格式命名空间 /
  `set_draw_buffers` 双缓冲 / flush `color_p` 是 `lv.Pointer`。
- 新增 `micropython/cira_splash.py`（开机 splash 入口，部署为 `:main.py`），解决「通电黑屏」。
- `tools/lvgl_hello.py` 分级自省探针（L0~L3）。
- `device-builds/` 路线 A 固件三件套 + 烧录/装机说明。
- `PROJECT_CONTEXT.md` / 记忆同步更新。
