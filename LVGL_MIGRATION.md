# CIRA Device Runtime · LVGL 迁移计划（v0.9 方向）

> 最后更新：2026-08-09 ｜ 决策：UI/星云顺滑度问题改用 **LVGL（同硬件 ESP32-S3-Touch-LCD-1.85C-BOX V2）**。
> 实现方式：**lv_micropython**（MicroPython + LVGL 官方绑定）——保持 Python，复用现有音频/WS/触摸/主循环，仅替换"显示 + UI 渲染层"。

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

---

## 3. 分阶段（状态：2026-08-09）

- **阶段 0（spike，用户本机）**：刷 lv_micropython，跑 `tools/lvgl_hello.py`，确认 LVGL 跑通 + 圆屏点亮。→ 定 A/B 方案。**⏳ 待 Evan 本机跑探针并反馈现象。**
- **阶段 1（代码已写）**：`micropython/cira_lvgl_display.py` —— ST77916 ↔ LVGL flush_cb（方案 A：frozen st77916 真实 blit；降级 dummy）。与探针同款 v9 API。
- **阶段 2（代码已写 + Mac 数学已验证）**：`micropython/cira_lvgl_lifeform.py` —— 复用 `cira_lifeform` 全部数学/配色，渲染进 RGB565 缓冲，由调用方注入 `commit` 钩子推到 LVGL canvas。`tools/test_lvgl_lf_smoke.py` 六态渲染通过。
- **阶段 3（代码已写）**：`micropython/cira_lvgl_control_center.py` —— **canvas 方案**（非原生 widgets，原因见 §7），复用 `cira_control_center` 已验证像素绘制 + 状态机，仅换 LVGL canvas 表面。
- **阶段 4（代码已写，入口并存）**：`micropython/cira_main_lvgl.py` —— LVGL 运行时入口（与 `cira_main.py` 并存，作可回退兄弟版本）；主循环每帧 `lv.timer_handler()`。

> 全部 LVGL 模块 **未经真机运行**，依赖阶段0探针确认 LVGL 确切 API（v8/v9）与 ST77916 flush 后才可信。探针一通过即刷。

---

## 4. 构建 / 烧录（用户本机，沙盒无工具链）

- 优先用 lv_micropython 的 **ESP32-S3 通用预构建**（若有）；否则本机 `make BOARD=...` 构建带 st77916 的版本。
- 备份当前 `main.py` 为 `main_cira_backup.py`，原厂固件已备份为 `main_xiaozhi.py`。
- 烧录后用 `mpremote run tools/lvgl_hello.py` 跑探针。

---

## 5. 回退与风险

- 若 lv_micropython 在此板 PSRAM/内存吃紧 → 退而用 **C/ESP-IDF + LVGL**（工作量更大但可控，仍是同一 LVGL API）。
- 现有 MicroPython 固件功能完整（音频/WS/唤醒已验证），可随时回退，迁移零风险。
- 真机 PSRAM 冷启动缓存一致性坑（v0.8.x 已用"预热 3 帧切 viper"解决）在 LVGL 路径下需重新评估（LVGL 用自己的缓冲管理，可能不走 st77916 的 viper blit）。

---

## 6. 当前固件状态（迁移基线）

- 当前板载固件 = v0.8.7（星云柔光软斑 + 控制中心重写对齐 HTML 原型），音频/WS/唤醒链路已验证可用。
- 已知缺陷（推动本次迁移）：星云 ~4.5fps 纯 Python 像素运算 → 像雷达图闪烁；控制中心全屏 `fill_rect` 重绘无过渡 → 一帧一帧。根因均为"纯 MicroPython 无 GPU/合成器"。

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
