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

两种接法：

- **A. 构建侧**：在本机 `lv_micropython` 构建里把 `st77916` 加为 frozen/用户模块 → flush_cb 直接调 `st77916.blit(buf, x0,y0,w,h)`。最干净，但需要本机 ESP-IDF 构建链。
- **B. 纯 Python 侧**：用 SPI 直接写 ST77916 的 `set_window`+`write`（不依赖 frozen 模块），在 Python 里实现 flush_cb。无需改构建，但 flush 性能需实测。

**先验证**：刷 lv_micropython → 跑 `tools/lvgl_hello.py` → 确认 (1) LVGL 能 `import` 并跑起 timer；(2) 圆屏能点亮（先用 dummy flush 证明 LVGL 在跑，再接 ST77916）。这一步不过，后面都是空谈。

> ⚠ **关于"刷固件"的现实**：本仓库的探针（`tools/lvgl_hello.py`）是**假设板上已有一份含 LVGL 的固件**。这份固件必须自己用 ESP-IDF 编译（见 §4 路线 A）或找到适配 ST77916 的第三方固件——这是本迁移最大的前置门槛，请先评估是否走路线 A。

---

## 3. 分阶段（状态：2026-08-09）

- **阶段 0（spike，用户本机）**：刷 lv_micropython，跑 `tools/lvgl_hello.py`，确认 LVGL 跑通 + 圆屏点亮。→ 定 A/B 方案。**⏳ 待 Evan 本机跑探针并反馈现象。**
- **阶段 1（代码已写）**：`micropython/cira_lvgl_display.py` —— ST77916 ↔ LVGL flush_cb（方案 A：frozen st77916 真实 blit；降级 dummy）。与探针同款 v9 API。
- **阶段 2（代码已写 + Mac 数学已验证）**：`micropython/cira_lvgl_lifeform.py` —— 复用 `cira_lifeform` 全部数学/配色，渲染进 RGB565 缓冲，由调用方注入 `commit` 钩子推到 LVGL canvas。`tools/test_lvgl_lf_smoke.py` 六态渲染通过。
- **阶段 3（代码已写）**：`micropython/cira_lvgl_control_center.py` —— **canvas 方案**（非原生 widgets，原因见 §7），复用 `cira_control_center` 已验证像素绘制 + 状态机，仅换 LVGL canvas 表面。
- **阶段 4（代码已写，入口并存）**：`micropython/cira_main_lvgl.py` —— LVGL 运行时入口（与 `cira_main.py` 并存，作可回退兄弟版本）；主循环每帧 `lv.timer_handler()`。

> 全部 LVGL 模块 **未经真机运行**，依赖阶段0探针确认 LVGL 确切 API（v8/v9）与 ST77916 flush 后才可信。探针一通过即刷。

---

## 4. 两条路线与具体本机步骤（先读再决定）

核心洞察：**当前 LVGL 方案里星云仍是 Python 算的**，LVGL 只负责「把 canvas 缓冲顺滑合成到屏」。所以：
- LVGL 化对「控制中心一帧一帧 / UI 过渡」改善明显；
- 对「星云雷达图闪烁」改善有限（瓶颈在 Python 数学，与下方路线 B 同一瓶颈）。
真正让星云也 GPU 加速，需把星云改成 LVGL 原生图元（更复杂，非当前 `cira_lvgl_*` 方案）。

因此给出两条路，**强烈建议先走路线 B 验证（零成本、当天出结论）**：

### 路线 A：编译 lv_micropython（真·LVGL 固件）——门槛高
适合：路线 B 仍不够顺，或你想用 LVGL 原生控件/字体。

1. **装 ESP-IDF**（Mac）：按 Espressif 官方文档装（约 1.5GB），`get_idf` / 运行 `install.sh` + `. ./export.sh` 激活环境。
2. **取源码**：`git clone --recursive https://github.com/lvgl/lv_micropython.git && cd lv_micropython`
3. **进端口**：`cd ports/esp32`
4. **把 ST77916 加为 frozen module（方案 A 关键）**：从本仓库 `cira-prototype/backups/`（或板子备份）取 `st77916.py`，放进 `modules/st77916/`，在板级 `manifest.py`（GENERIC_S3）注册；并在 `mpconfigboard.h` 定义屏参（360×360、QSPI 引脚，参考 `backups/st77916_init.py`）。**这步不做 → LVGL 跑起来屏是黑的。**
5. **编译**：`make BOARD=GENERIC_S3`（octal-SPIRAM 板用 `BOARD=GENERIC_S3/spiram_oct`）。产出 `build-GENERIC_S3/firmware.bin`。首次编译 10~30 分钟。
6. **备份原固件**：`mpremote connect /dev/cu.usbmodem101 fs cp :main.py :main_cira_backup.py`
7. **擦除 + 烧录**：
   `esptool.py --chip esp32s3 --port /dev/cu.usbmodem101 --baud 460800 erase_flash`
   `esptool.py --chip esp32s3 --port /dev/cu.usbmodem101 --baud 460800 write_flash -z 0 build-GENERIC_S3/firmware.bin`
8. **跑探针**：`mpremote connect /dev/cu.usbmodem101 run tools/lvgl_hello.py` → 看现象（§8 清单）。
9. **反馈现象给我** → 校正 LVGL 版本/flush → 刷 `cira_main_lvgl.py`。

> 门槛：ESP-IDF 安装 + 编译耗时、ST77916 frozen 接入需处理屏参/引脚，可能踩坑。若无编译经验，难度不低。

### 路线 B：现有固件轻量顺滑化（零编译，强烈建议先试）✅ 已实施 v0.8.8（改动见 §10）
现有小智 MicroPython 固件**已含 ST77916 frozen（硬件 QSPI 加速 blit）**，我们只是上层 Python。改动全在 Python 层，可 `mpremote` 直接推送，**零风险、当天出结果**。

1. **星云取消限帧**：编辑 `micropython/cira_lifeform.py`，把 `_interval`（当前 220ms≈4.5fps）调到 `40~50`（≈20~25fps）或 `0`（每帧）。看 ESP32-S3 裸跑星云能到多少 fps、是否还「闪烁」。
2. **控制中心脏区刷新**：改 `cira_control_center.py`，避免整屏 `fill_rect`，只重绘变化区域（滑块拖动/数值变化时局部重绘）。这直接消灭「一帧一帧」。
3. **推送验证**：`mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_lifeform.py :cira_lifeform.py`（同理推 control_center），然后 `mpremote connect /dev/cu.usbmodem101 reset`（或断电重启）。
4. **观察**：若星云 + 控制中心在现有固件上就「够顺」→ **不必编译 LVGL**，直接收尾 v0.8.x，省下路线 A 的大门槛。

### 决策建议
- **先 B**：零成本、此刻就能验证瓶颈到底在哪。若 B 够顺 → 项目提前收尾，无需 LVGL。
- **B 不够** → 再投入 A（真 LVGL，用 C 合成 + 后续把星云也改 LVGL 图元做 GPU 加速）。

> 无论走哪条，现有 MicroPython 固件功能完整（音频/WS/唤醒已验证），`main_xiaozhi.py` 已备份，迁移零风险、可随时回退。

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
2. **ST77916 flush**：圆屏出 `CIRA · LVGL` = 方案 A 成功；黑屏无报错 = `bytes(color_p, size)` 地址转换需调（试 `memoryview`/直接传 `color_p`）；`import st77916` 失败 = 走方案 B（纯 Python SPI flush，需另写）。
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
# 确保 Thonny 已断开释放串口（Cmd+Shift+D 或退出）
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_lifeform.py :cira_lifeform.py
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_main.py      :cira_main.py
mpremote connect /dev/cu.usbmodem101 fs cp micropython/cira_control_center.py :cira_control_center.py
mpremote connect /dev/cu.usbmodem101 reset
```
观察：星云是否连续呼吸不闪、控制中心拖动是否局部刷不整屏闪。若够顺 → 收尾；若仍卡 → 反馈，我接路线 A 或做字模缓冲 blit 第二步。
