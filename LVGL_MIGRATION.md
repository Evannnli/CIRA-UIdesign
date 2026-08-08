# CIRA Device Runtime · LVGL 迁移计划（v0.9 方向）

> 最后更新：2026-08-09 ｜ 决策：UI/星云顺滑度问题改用 **LVGL（同硬件 ESP32-S3-Touch-LCD-1.85C-BOX V2）**。
> 实现方式：**lv_micropython**（MicroPython + LVGL 官方绑定）——保持 Python，复用现有音频/WS/触摸/主循环，仅替换"显示 + UI 渲染层"。
>
> ⚠ **2026-08-09 夜 重要更正**：经检索确认，**官方/第三方都没有现成的 lv_micropython 预编译固件可直接下载**——MicroPython 官网只提供标准固件（不含 LVGL），第三方带 LVGL 的固件（如果云三合一）屏驱是 ST7789 硬编码、不适配我们的 ST77916 圆屏。因此"刷 lv_micropython 固件"必须先 **ESP-IDF 自行编译**（门槛较高）。据此修订 §4 为「两条路线」，请先读 §4 再决定。

---

## 1. 为什么选 lv_micropython（而不是用 C 重写整个固件）

Evan 的原话是"扒一套成熟的下来稍作改造"。LVGL 是嵌入式 GUI 的工业标准（顺滑 30~60fps、原生手势/控件/过渡动画、圆形屏支持）。
`lv_micropython` 是 MicroPython 的官方 LVGL 绑定构建——意味着 UI 仍用 **Python** 写，现有模块几乎原样复用：

| 模块 | 处置 |
|------|------|
| `cira_audio` / `cira_codec` / `cira_audio_in` | **保留**（ES8311/ES7210 音频管线） |
| `cira_ws` / `ws_native` | **保留**（桥接层 + 原生 WS） |
| `cira_touch` | **保留**（CST816 触摸，仅加一个 LVGL read_cb 适配） |
| `cira_main` | **保留核心编排**，仅把"显示调用"换 LVGL |
| `cira_emotions` / `cira_wake` / `cira_i2c` / `cira_expander` | **保留** |
| `cira_display.py` | **替换** 为 `cira_display_lvgl.py`（ST77916 ↔ LVGL flush_cb） |
| `cira_lifeform.py` | **重写** 为 LVGL canvas / 图元星云（LVGL 自己做 30~60fps 合成 + 运动模糊） |
| `cira_control_center.py` | **重写** 为 LVGL widgets（lv_list / lv_slider / lv_btn），原生手势与过渡，彻底消灭"一帧一帧" |

---

## 2. 唯一硬风险（必须先 spike 验证）

ST77916 是 **360×360 圆屏 QSPI 非标驱动**，标准 lv_micropython 不含。LVGL 要把渲染结果送到屏上，必须提供一个 `flush_cb(disp, area, color_p)`，把 `area` 这块矩形区域的 RGB565 像素推到面板。

**研究后纠正（2026-08-10）**：ST77916 驱动是 **C 写的 ESP-IDF 组件**（`esp_lcd_st77916`，走硬件 QSPI/LCD_CAM），板子固件里的 `st77916` 是一个**包了这层 C 驱动的 MicroPython C 扩展模块**——**不是能直接丢进去的 `.py` 文件**。所以「加个 frozen py 模块」的设想不成立。

已落实的做法（见 `micropython/lvgl_build/`）：写一个**自包含 C 扩展模块 `cira_st77916`**，只用 ESP-IDF 自带的 `esp_lcd` + 本仓库已验证的 181 条初始化序列（`st77916_init.py`），自己实现 `init/blit/on/off/fill/set_nit`，经 `USER_C_MODULES` 编进 lv_micropython。flush_cb 调 `st77916.blit(buf, x0,y0,w,h)`。

- **方案 A（已落地代码，用户 2026-08-10 选定全力执行）**：本机装 ESP-IDF → 编 lv_micropython（含 cira_st77916）→ 烧录。需要本机编译链，完整步骤见 `micropython/lvgl_build/README.md`。
- **方案 B（轻量验证，v0.8.8 已实施）**：不编译 LVGL，继续用现有小智固件的 Python 上层（取消星云限帧 + 控制中心脏区刷新）。零成本，但 Nebula 仍是 Python 算、顺滑度上限有限，作为路线 A 太重时的兜底。

**先验证**：刷 lv_micropython → 跑 `tools/lvgl_hello.py` → 确认 (1) LVGL 能 `import` 并跑起 timer；(2) 圆屏能点亮（先用 dummy flush 证明 LVGL 在跑，再接 ST77916）。这一步不过，后面都是空谈。

> ⚠ **关于"刷固件"的现实**：本仓库的探针（`tools/lvgl_hello.py`）是**假设板上已有一份含 LVGL 的固件**。这份固件必须自己用 ESP-IDF 编译（见 §4 路线 A）或找到适配 ST77916 的第三方固件——这是本迁移最大的前置门槛，请先评估是否走路线 A。

---

## 3. 分阶段（状态：2026-08-09）

- **阶段 0（spike，用户本机）**：刷 lv_micropython（含 cira_st77916），跑 `tools/lvgl_hello.py`，确认 LVGL 跑通 + 圆屏点亮。**Evan 已 2026-08-10 选定全力方案 A，构建物料已就绪（cira_st77916 C 模块 + README），待本机执行编译/烧录。**
- **阶段 1（代码已写）**：`micropython/cira_lvgl_display.py` —— ST77916 ↔ LVGL flush_cb（方案 A：frozen st77916 真实 blit；降级 dummy）。与探针同款 v9 API。
- **阶段 2（代码已写 + Mac 数学已验证）**：`micropython/cira_lvgl_lifeform.py` —— 复用 `cira_lifeform` 全部数学/配色，渲染进 RGB565 缓冲，由调用方注入 `commit` 钩子推到 LVGL canvas。`tools/test_lvgl_lf_smoke.py` 六态渲染通过。
- **阶段 3（代码已写）**：`micropython/cira_lvgl_control_center.py` —— **canvas 方案**（非原生 widgets，原因见 §7），复用 `cira_control_center` 已验证像素绘制 + 状态机，仅换 LVGL canvas 表面。
- **阶段 4（代码已写，入口并存）**：`micropython/cira_main_lvgl.py` —— LVGL 运行时入口（与 `cira_main.py` 并存，作可回退兄弟版本）；主循环每帧 `lv.timer_handler()`。

> 全部 LVGL 模块 **未经真机运行**，依赖阶段0探针确认 LVGL 确切 API（v8/v9）与 ST77916 flush 后才可信。探针一通过即刷。

---

## 4. 方案 A 实施（用户 2026-08-10 选定，全力执行）

> 核心洞察不变：当前 LVGL 方案里**星云仍是 Python 算的**，LVGL 主要救「控制中心顺滑度 / UI 过渡」，直接改善星云「雷达图闪烁」有限（瓶颈在 Python 数学）。但用户已决定全力走 A，拿到真正 LVGL 运行时。

### 主干（完整、可复制命令见 `micropython/lvgl_build/README.md`）

1. **装 ESP-IDF**（Mac，约 1.5GB）：版本必须匹配 lv_micropython 要求（克隆后看 `ports/esp32/README.md`），`install.sh esp32s3` + `. ./export.sh`。
2. **取源码**：`git clone --recursive https://github.com/lvgl/lv_micropython.git && cd lv_micropython && git submodule update --init --recursive lib/lv_bindings && make -C mpy-cross`。
3. **接 cira_st77916**：`export CIRA_ST77916=/abs/cira-prototype/micropython/lvgl_build/cira_st77916`，构建时 `USER_C_MODULES=$CIRA_ST77916` 自动纳入（见 `cira_st77916/micropython.mk`）。本模块**自包含**，只用 ESP-IDF 自带 `esp_lcd` + 已验证的 181 条初始化序列，不依赖外部 `esp_lcd_st77916` 组件。
4. **编译 + 烧录**：`make -C ports/esp32 BOARD=GENERIC_S3 USER_C_MODULES=$CIRA_ST77916 LV_CFLAGS="-DLV_COLOR_DEPTH=16 -DLV_COLOR_16_SWAP=0" deploy`（烧前先 `read_flash` 整片备份原厂固件）。
5. **推 CIRA 的 Python 文件**：`cira_pins/cira_expander/cira_lvgl_display/cira_lvgl_lifeform/cira_lvgl_control_center` 推上板；`cira_main_lvgl.py` 推成 `:main.py`（先 `fs rm` 防静默失败）。
6. **跑探针**：`mpremote connect /dev/cu.usbmodem101 run tools/lvgl_hello.py` → 圆屏出 `CIRA · LVGL` 即全链路通。
7. **反馈现象给我** → 若编译/运行报错（最常见：颜色字节序、`MP_DEFINE_CONST_OBJ_TYPE` 宏名、`esp_lcd` 头缺失），据此改 `cira_st77916/st77916.c` 重编。

### 路线 B（兜底，v0.8.8 已实施，零编译）
若路线 A 编译太重或卡住，可退回 v0.8.8 的纯 Python 轻量顺滑化（取消星云限帧 + 控制中心脏区刷新，`mpremote` 直接推，见 §10）。功能完整、可随时回退。

> 现有 MicroPython 固件功能完整（音频/WS/唤醒已验证），`main_xiaozhi.py` 已备份，迁移可随时回退。

---

## 5. 回退与风险

- 若 lv_micropython 在此板 PSRAM/内存吃紧 → 退而用 **C/ESP-IDF + LVGL**（工作量更大但可控，仍是同一 LVGL API）。
- 现有 MicroPython 固件功能完整（音频/WS/唤醒已验证），可随时回退，迁移零风险。
- 真机 PSRAM 冷启动缓存一致性坑（v0.8.x 已用"预热 3 帧切 viper"解决）在 LVGL 路径下需重新评估（LVGL 用自己的缓冲管理，可能不走 st77916 的 viper blit）。

---

## 6. 当前固件状态（迁移基线）

- **稳定基线 = v0.8.7**（星云柔光软斑 + 控制中心重写对齐 HTML 原型），音频/WS/唤醒链路已验证可用。
- 已知缺陷（推动本次迁移）：星云 ~4.5fps 纯 Python 像素运算 → 像雷达图闪烁；控制中心全屏 `fill_rect` 重绘无过渡 → 一帧一帧。根因均为"纯 MicroPython 无 GPU/合成器"。
- **路线 B 实验版 = v0.8.8**（2026-08-09 已实施，零编译）：星云取消限帧(`_interval=0`)+控制中心拖动局部刷新。改动在 `cira_lifeform.py`/`cira_main.py`/`cira_control_center.py`，Mac 桩 `tools/test_route_b.py` 通过（星云每帧 blit、局部刷新 fill_rect 97→17 次）。**待 Evan 本机 `mpremote` 推送验证真机顺滑度**。若够顺 → 项目提前收尾，无需路线 A。

---

## 7. ⚠ LVGL 中文困境（阶段 3 关键发现）

LVGL **默认字体只含 ASCII**，本板中文靠 `subtitle_font` 点阵（12px 自绘位图）。
若用 LVGL 原生 widgets（`lv_list`/`lv_slider`/`lv_label`），中文标签无处渲染。

两条路：
- **(A) canvas 方案（本轮采用，低风险、观感不变）**：控制中心整体仍用 `subtitle_font` 像素绘制，但画进 LVGL canvas 缓冲，由 LVGL 平滑合成 + 过渡。
  交互/顺滑度问题解决（覆盖「一帧一帧」），中文零改动。代价：不是"原生 widget"，
  但视觉与 v0.8.7 完全一致，Evan 已认可。
- **(B) 真·原生 widgets（后续升级）**：用 `lv_font_conv`（Node 工具）把 `subtitle_font` 的
  CHARSET/GLYPHS 转成 LVGL 字体（`lv_font_t`），注册为默认字体后所有 widget 直接显示中文。
  这是更"扒成熟系统"的做法，但需构建步骤 + 验证字体加载，留作 v1.0。

> 结论：先走 (A) 把顺滑度跑通（最快见效、风险最低）；(B) 作为字体增强跟随。

---

## 8. 待硬件验证清单（阶段 0 探针通过后立即核对）

Evan 本机跑 `tools/lvgl_hello.py` 后，按现象修这些点：
1. **LVGL 版本**：探针打印 `version: x.y.z`。若 v8 → 本仓库 `cira_lvgl_*` 的 display/canvas API 需按 v8 改写（文件内已留注释）。
2. **ST77916 flush**：圆屏出 `CIRA · LVGL` = 方案 A 成功；黑屏无报错 = flush 的 `color_p` 地址转换问题（已改用 `uctypes.bytearray_at`，若仍黑屏查 RGB565 字节序 / 屏方向 `madctl`）；`import st77916` 失败 = cira_st77916 模块没编进固件（`USER_C_MODULES` 路径/构建报错）。
3. **canvas 缓冲**：`lv.canvas.set_buffer(buf, 360,360, RGB565)` + `invalidate()` 在目标固件是否可用（v9 确认；v8 用 `lv_canvas_set_buffer`）。
4. **圆屏裁切**：LVGL 方缓冲 → 硬件圆窗遮罩即可；若要 LVGL 内做圆角，用 `lv.obj.set_style_radius(180)` 近似。
5. **效能**：星云渲染间隔 `_interval`（默认 70ms≈14fps）；算力吃紧就调大到 100~150ms，或降 `scale`。

---

## 9. 本沙盒已完成（无需硬件）

- 四个 LVGL 模块编写 + `py_compile` 语法通过。
- 星云数学移植 `tools/test_lvgl_lf_smoke.py` 六态渲染 Mac 桩通过（LVGL 无关部分已验证）。
- LVGL 迁移文档（本文件）与运行时入口（`cira_main_lvgl.py`）就绪。
- **下一步动作在 Evan 本机**：跑阶段0探针 → 反馈现象 → 据此校正 API → 刷 `cira_main_lvgl.py`。

---

## 10. 路线 B 实施记录（v0.8.8，2026-08-09）

**决策**：Evan 选「先走 B」——零编译、当天验证现有固件能否够顺，再决定是否投入路线 A（LVGL 编译）。

**改动（均 MicroPython 上层，不碰硬件驱动）**：
1. `cira_lifeform.py`：`self._interval` 由 `220`（~4.5fps 限帧）改为 `0`（取消限帧，每帧渲染）。根治星云「雷达图光点闪烁」——位置连续移动而非每 220ms 跳变。注释说明若真机太卡可回调 `33`/`40`。
2. `cira_main.py`：后台动画线程 `sleep_ms(40)` 改为 `sleep_ms(16)`，把帧率上限从 ~25fps 放宽到 ~60fps（实际由每帧渲染耗时决定）。
3. `cira_control_center.py`：新增 `_clear_rect`（底色覆盖矩形）+ `_redraw_sub_dynamic`（子视图拖动时只重绘「大数值区 + 滑块区」，不动标题/提示）；子视图拖动分支由整屏 `_redraw` 改为局部刷新。**根治控制中心拖动「整屏闪」**。

**沙盒验证（Mac 桩 `tools/test_route_b.py`，无需硬件）**：
- 星云：构造后连续 `tick(0/50/100...)`，`_interval==0` 成立，每帧都 `blit`，六态切换无异常。
- 控制中心：整屏 `redraw` 触发 `fill_rect` **97 次**；局部 `_redraw_sub_dynamic` 仅 **17 次**（≈18%）。调用次数≈SPI 交易次数，局部刷新交易少一个数量级 → 拖动更顺。

**已知局限（路线 B 无法根除，若仍不够顺则走路线 A）**：
- 控制中心文字仍是「逐像素 `fill_rect` 字模」（每次 `_draw_glyph` 每像素一次 SPI 写）。局部刷新减少了重绘范围，但单次文字绘制的像素级调用仍在。根治需「字模缓冲 → 一次 `blit`」（改动较大，是路线 B 第二步，或在 LVGL 路线 A 用原生字体解决）。
- 星云仍是 Python 数学，取消限帧后帧率受渲染耗时上限（ESP32-S3 裸跑预计 20~30fps，非 60fps）。真·60fps 需 LVGL 原生图元（路线 A 进阶）。

**Evan 本机验证步骤（推送 v0.8.8）**：
```
# 0) 先释放串口：Thonny 里 Run ▸ Disconnect(Cmd+Shift+D) 或退出 Thonny，否则连不上
# 1) 推送两个被 import 的模块
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_lifeform.py :cira_lifeform.py
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_control_center.py :cira_control_center.py
# 2) 更新开机固件（板子开机跑的是 :main.py，不是 :cira_main.py）
#    ⚠ mpremote 覆盖已存在的 :main.py 会静默失败 → 必须先 rm 再 cp（见 MEMORY 第16行坑）
mpremote connect /dev/cu.usbmodem101 fs rm :main.py
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_main.py :main.py
# 3) 重启生效
mpremote connect /dev/cu.usbmodem101 reset
```
> 验证推送是否真生效（防静默失败）：`mpremote connect /dev/cu.usbmodem101 fs cat :main.py | head -5` 应看到 v0.8.8 的注释/代码；或 `fs cat :cira_lifeform.py | grep _interval` 应看到 `self._interval = 0`。
观察：星云是否连续呼吸不闪、控制中心拖动是否局部刷不整屏闪。若够顺 → 收尾；若仍卡 → 反馈，我接路线 A 或做字模缓冲 blit 第二步。
