# CIRA 项目传承文档（PROJECT_CONTEXT）

> **最后更新**：2026-08-12（晚） · **对应定版**：`git tag nebula-1.0`
> 本文件随代码走，换电脑/换模型/换协作者都能满血接手。改动重大里程碑后必须更新此处并 commit。

---

## 一、项目是什么

**CIRA** = 面向儿童的 AI 陪伴生命体，视觉载体是一个"会呼吸、会被吸引、有情绪"的**暖色星云**。
核心体验：孩子戳它/对它说话，星云有"生命感"回应；待机时喊它名字，它在手机底部以半透明悬浮生命体出现。

当前两条产品线：
- **星云交互（安卓 App 首要）**：全屏自适应星云主界面 + 待机悬浮唤醒。✅ **v1.0 已定稿**（本回合）。
- **硬件嵌入式（ESP32-S3 圆屏，暂停）**：因 Mac USB CDC 驱动崩溃反复，自 2026-08-12 起暂停 2 天，未废弃。

---

## 二、核心哲学 / 产品定义

1. **"生命感"优先**：交互的"活"比功能重要。引力汇聚、呼吸、情绪 morph 都是为"它像活的"。
2. **暖色体积光场基调不可动**：橙/粉/紫/暖白，无青蓝绿（用户强偏好，见 NEBULA_V1_SPEC §1）。
3. **状态是同一套动效词汇的变体**：待机/聆听/思考/回应/唤醒/休眠 用统一的呼吸-旋转-收束-声波语言，构成一个系列。
4. **CIRA 的"心情"由 Core 权威**：接模型后情绪(emotion/ignite)以 Core 为准，App 不自己编（防脱节）。

---

## 三、技术分工与关键决策（理由已验证，勿走弯路）

| 决策 | 结论 | 理由 |
|---|---|---|
| 首要平台 | **安卓（小米15）** | 用户手机；iOS 第三方 App 无法真悬浮（系统限制） |
| 悬浮+唤醒 | **必须原生** Capacitor（前台 Service + SYSTEM_ALERT_WINDOW + Porcupine/Vosk + Silero VAD） | Web/PWA 做不到"悬浮于所有应用" |
| 桌面 Tauri | 降级为副产物（已出 CIRA.app + dmg） | 非首要目标 |
| 模型侧 status 归属 | **App 自管** listening/thinking/speaking/wake/idle | status 是调用生命周期副产品，Core 不参与 listening/thinking（零冻结、最干净） |
| 模型侧 emotion/ignite | **Core 权威**，随 `/v1/respond` 的 `display_state` 返回 | 回复内容属性，App 据此驱动配色点亮 |
| 硬件调试 | 暂停，等 Windows 笔记本或 USB-TTL 适配器 | Mac 原生 USB CDC 驱动 panic 累计 4 次 |

---

## 四、当前进度（里程碑）

- ✅ **星云交互 v1.0 定稿**（2026-08-12）：触碰"万有引力式汇聚"手感验收通过；6 种状态动效重做；唤醒 VAD 流转（说一句才进思考、不说静静等）。
  - 源：`android-proto/cira-android.html` + `android-proto/lifeform.js`
  - 规格：`android-proto/NEBULA_V1_SPEC.md`（参数全冻结）
- 🟡 **模型集成前端已接通（2026-08-12 晚）**：`android-proto/cira-android.html` 占位逻辑已替换为真实桥接调用 —— `transcribe`(16k PCM)/`respond`(取 display_state.emotion 驱动星云)/`speak`(base64 播放)/`wake_ack`(唤醒音频)/`health`(启动自检) 全通；含双降级（BASE 为空=离线占位；桥不可达=文字输入/系统 TTS）。附 `android-proto/mock_bridge.js`（零依赖本地桥，自测全绿）供联调。
  - **待对侧给真实地址**：用户已实现桥接服务，`BRIDGE.BASE` 填真实 `http://<IP>:<port>` 即可在小米15 实机联调（端点/字段需与 `docs/CIRA_APP_INTEGRATION_REQUIREMENTS.md` 对齐；若有出入告诉我改）。
- ⏸️ **硬件**：ST77916 黑屏根因已定位（QPI→标准 SPI 8-bit），修复已 commit 未 push；Mac 崩溃阻断验证。

---

## 五、关键技术决策细节（避免重踩）

- **引力模型演进结论**（已验证定稿）：不可用硬半径 cutoff（进圈即死）→ 无硬边界软化井；不可"到点=目标位移归零"（星飘走）→ 绝对点钉死；不可匀速缓动 → 加速度积分实现远慢近快。详见 NEBULA_V1_SPEC §2。
- **Mac USB CDC 崩溃**：`/dev/cu.usbmodem101` 在 macOS 26.x 内核 `usb.cdc.acm` 有 NULL 解引用 bug，被 DTR/RTS 复位信令触发。避坑：烧录 `--before no_reset`、避免 `mpremote reset`、换好线直插 USB-A。
- **构建铁律**：`USER_C_MODULES` 必须 `-DUSER_C_MODULES=<path>/micropython.cmake` 显式传给 `idf.py`（非 env 变量），否则 st77916.c 被静默丢弃→黑屏。
- **代理坑**：git/cargo 全局代理 57213 失效；cargo 用 `~/.cargo/config.toml` 强制 7897 + `GIT_CONFIG_GLOBAL=/dev/null`。

---

## 六、下一步

1. ✅ **桥接服务已就绪**：对侧按 `docs/CIRA_APP_INTEGRATION_REQUIREMENTS.md` 实现。前端调用已接好，等用户给真实 `http://<IP>:<port>` 填进 `BRIDGE.BASE` 即在小米15 实测。
2. **（进行中）模型端到端联调**：填真实地址后在手机实测 `transcribe→respond→speak` 全链路（麦克风权限需 https 或 Capacitor 安全上下文；纯 http 局域网下浏览器麦克风会被拦，走 `wakeMore` 文字降级）。验证延迟/兜底后封 Capacitor APK。
3. **封 Capacitor**：前端（本原型）+ 原生模块（唤醒词/悬浮窗/VAD/ASR/TTS/Core-LS 调用）。
4. **硬件恢复**（可选）：Windows 笔记本或 USB-TTL 适配器到位后，续烧录验证。

---

## 七、协作约定

- **仓库**：`cira-prototype/`，remote = `Evannnli/CIRA-UIdesign`（main，用户指定唯一远端）。
- **提交**：每次里程碑自动 commit（并尽量 push）；敏感 token 只在对话里给、不落盘、不写 `.git/config`。
- **push**：`git -c http.proxy= -c https.proxy= push`（当前代理 57213 失效，需用户给新 token 才能推）。
- **记忆**：长期笔记在 `.workbuddy/memory/MEMORY.md`；本文件为项目级传承。
- **决策人**：Evan（用户）。

---

*变更记录：2026-08-12 新增本项目传承文档；冻结星云交互 v1.0（NEBULA_V1_SPEC.md + git tag nebula-1.0）；集成需求 status 归属改为 App 自管（采纳用户建议）。*
